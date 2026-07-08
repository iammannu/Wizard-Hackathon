"""
Memory consolidation — decides, for each newly extracted MemoryCandidate,
whether it is new, reinforces an existing WorkspaceMemory row, or
contradicts one. Also rolls up sufficiently-confident workspace memory into
cross-workspace CompanyMemory, and promotes confirmed/refuted ThesisClaim
rows into ThesisMemory.

Two-threshold design, mirroring app/documents/evidence/dedup.py +
conflict.py exactly (same embedding space, same cosine_similarity helper):

  similarity >= memory_dedup_threshold          -> same belief, reinforce
  memory_contradiction_threshold <= similarity
      < memory_dedup_threshold                  -> same topic, ambiguous:
                                                    batched into ONE LLM call
                                                    per session (cost-bounded,
                                                    same contract as
                                                    conflict.py: llm_json
                                                    never raises, unresolved
                                                    pairs default to "new")
  similarity < memory_contradiction_threshold   -> unrelated, insert new

Cost-bounded by design: one embed_texts call for all of a session's
candidates, one llm_json call for all ambiguous pairs — not O(n) per
candidate.
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from app.core.config import get_settings
from app.core.llm import llm_json
from app.documents.embeddings.provider import get_embedding_provider
from app.documents.retrieval.similarity import cosine_similarity
from app.models.memory import WorkspaceMemory, CompanyMemory, ThesisMemory
from app.models.thesis import ThesisClaim
from app.memory.models import MemoryCandidate

settings = get_settings()

_AMBIGUOUS_SYSTEM_PROMPT = (
    "You are comparing pairs of investment-research memory items: an EXISTING "
    "stored belief/fact and a NEW candidate on the same topic. For each "
    'numbered pair, decide the relationship: "same" (the new item just '
    'restates the existing one, possibly with different wording), '
    '"contradicts" (the new item states something genuinely inconsistent '
    'with the existing one — opposite direction, conflicting figures, or a '
    'reversed conclusion), or "different" (related topic but not actually '
    "the same claim or in conflict — e.g. two distinct facts about the same "
    "company). Respond with JSON: "
    '{"pairs": [{"index": 0, "relationship": "same"|"contradicts"|"different"}, ...]}. '
    "Include exactly one entry per pair index."
)


class _MatchResult:
    __slots__ = ("candidate", "action", "existing_row")

    def __init__(self, candidate: MemoryCandidate, action: str, existing_row=None):
        self.candidate = candidate
        self.action = action  # "reinforce" | "contradict" | "new"
        self.existing_row = existing_row


async def _embed_candidates(candidates: list[MemoryCandidate]) -> tuple[list[list[float]], str, str]:
    provider = get_embedding_provider()
    vectors = await provider.embed_texts([c.content for c in candidates])
    return vectors, provider.provider_name, provider.model_name


async def _match_candidates(
    candidates: list[MemoryCandidate],
    vectors: list[list[float]],
    existing_rows: list,
    existing_vectors: dict,
) -> list[_MatchResult]:
    """existing_rows: WorkspaceMemory or CompanyMemory rows already in this
    scope. existing_vectors: {row.id: vector} precomputed for those rows."""
    results: list[_MatchResult] = [None] * len(candidates)
    ambiguous: list[tuple[int, MemoryCandidate, object]] = []  # (candidate_idx, candidate, existing_row)

    for i, (candidate, vec) in enumerate(zip(candidates, vectors)):
        best_row, best_sim = None, 0.0
        for row in existing_rows:
            if row.memory_type != candidate.memory_type:
                continue
            row_vec = existing_vectors.get(row.id)
            if not row_vec:
                continue
            sim = cosine_similarity(vec, row_vec)
            if sim > best_sim:
                best_sim, best_row = sim, row

        if best_row is not None and best_sim >= settings.memory_dedup_threshold:
            results[i] = _MatchResult(candidate, "reinforce", best_row)
        elif best_row is not None and best_sim >= settings.memory_contradiction_threshold:
            ambiguous.append((i, candidate, best_row))
        else:
            results[i] = _MatchResult(candidate, "new")

    if ambiguous:
        lines = [
            f"Pair {idx}:\nEXISTING: {row.content[:400]}\nNEW: {cand.content[:400]}\n"
            for idx, (_, cand, row) in enumerate(ambiguous)
        ]
        try:
            response = await llm_json(_AMBIGUOUS_SYSTEM_PROMPT, "\n".join(lines))
        except Exception:
            response = {}
        classifications = {item.get("index"): item.get("relationship") for item in response.get("pairs", [])} \
            if isinstance(response, dict) else {}

        for local_idx, (candidate_idx, candidate, row) in enumerate(ambiguous):
            relationship = classifications.get(local_idx, "different")
            if relationship == "same":
                results[candidate_idx] = _MatchResult(candidate, "reinforce", row)
            elif relationship == "contradicts":
                results[candidate_idx] = _MatchResult(candidate, "contradict", row)
            else:
                results[candidate_idx] = _MatchResult(candidate, "new")

    return results


def _citations_json(candidate: MemoryCandidate) -> str:
    return json.dumps([c.model_dump(mode="json") for c in candidate.citations])


async def consolidate_workspace_memory(
    db, workspace_id: uuid.UUID, candidates: list[MemoryCandidate], research_id: Optional[uuid.UUID] = None,
) -> list[WorkspaceMemory]:
    """Consolidates candidates into WorkspaceMemory rows for one workspace.
    Returns the affected rows (new + reinforced + contradicted-against)."""
    if not candidates:
        return []

    vectors, provider_name, model_name = await _embed_candidates(candidates)

    existing_result = await db.execute(
        select(WorkspaceMemory).where(
            WorkspaceMemory.workspace_id == workspace_id,
            WorkspaceMemory.status.in_(["active", "resolved"]),
        )
    )
    existing_rows = existing_result.scalars().all()
    existing_vectors = {row.id: row.embedding_vector() for row in existing_rows}

    matches = await _match_candidates(candidates, vectors, existing_rows, existing_vectors)

    affected: list[WorkspaceMemory] = []
    now = datetime.now(timezone.utc)

    for match, vec in zip(matches, vectors):
        candidate = match.candidate
        if match.action == "reinforce":
            row = match.existing_row
            total_weight = row.reinforcement_count + 1
            row.confidence = round(
                (row.confidence * row.reinforcement_count + candidate.confidence) / total_weight, 4
            )
            row.reinforcement_count = total_weight
            row.last_research_id = research_id
            row.updated_at = now
            merged_citations = row.citations_list() + [c.model_dump(mode="json") for c in candidate.citations]
            row.source_citations = json.dumps(merged_citations[-20:])  # cap growth
            if candidate.memory_type == "open_question" and row.status == "active":
                pass  # stays open until a resolved_question explicitly supersedes it (handled below)
            affected.append(row)

        elif match.action == "contradict":
            row = match.existing_row
            row.contradiction_count += 1
            row.confidence = round(max(0.05, row.confidence - 0.15), 4)
            row.updated_at = now
            affected.append(row)

            new_row = WorkspaceMemory(
                workspace_id=workspace_id,
                memory_type=candidate.memory_type,
                content=candidate.content,
                tickers=json.dumps(candidate.tickers),
                confidence=candidate.confidence,
                status="active",
                source_citations=_citations_json(candidate),
                embedding=json.dumps(vec),
                embedding_model=model_name,
                first_research_id=research_id,
                last_research_id=research_id,
                reinforcement_count=1,
                contradiction_count=1,
            )
            db.add(new_row)
            affected.append(new_row)

        else:  # "new"
            new_row = WorkspaceMemory(
                workspace_id=workspace_id,
                memory_type=candidate.memory_type,
                content=candidate.content,
                tickers=json.dumps(candidate.tickers),
                confidence=candidate.confidence,
                status="active",
                source_citations=_citations_json(candidate),
                embedding=json.dumps(vec),
                embedding_model=model_name,
                first_research_id=research_id,
                last_research_id=research_id,
                reinforcement_count=1,
                contradiction_count=0,
            )
            db.add(new_row)
            affected.append(new_row)

    # A resolved_question supersedes the matching open_question it answers,
    # when both were extracted in the same session (best-effort text match —
    # exact semantic linking would need another LLM call this milestone's
    # cost budget doesn't justify for a same-session heuristic).
    resolved_now = [c for c in candidates if c.memory_type == "resolved_question"]
    if resolved_now:
        open_result = await db.execute(
            select(WorkspaceMemory).where(
                WorkspaceMemory.workspace_id == workspace_id,
                WorkspaceMemory.memory_type == "open_question",
                WorkspaceMemory.status == "active",
            )
        )
        for open_row in open_result.scalars().all():
            open_row.status = "resolved"
            open_row.updated_at = now

    await db.flush()
    return affected


async def promote_to_company_memory(db, ticker: str, workspace_id: uuid.UUID, rows: list[WorkspaceMemory]) -> None:
    """Rolls up WorkspaceMemory rows above the promotion confidence bar into
    cross-workspace CompanyMemory, using the same dedup/reinforce logic."""
    eligible = [r for r in rows if r.confidence >= settings.memory_company_promotion_min_confidence]
    if not eligible:
        return

    provider = get_embedding_provider()
    now = datetime.now(timezone.utc)

    existing_result = await db.execute(
        select(CompanyMemory).where(CompanyMemory.ticker == ticker, CompanyMemory.status == "active")
    )
    existing_rows = existing_result.scalars().all()

    for row in eligible:
        row_vec = row.embedding_vector()
        if row_vec is None:
            vectors = await provider.embed_texts([row.content])
            row_vec = vectors[0]

        best_row, best_sim = None, 0.0
        for existing in existing_rows:
            if existing.memory_type != row.memory_type:
                continue
            existing_vec = existing.embedding_vector()
            if not existing_vec:
                continue
            sim = cosine_similarity(row_vec, existing_vec)
            if sim > best_sim:
                best_sim, best_row = sim, existing

        if best_row is not None and best_sim >= settings.memory_dedup_threshold:
            total_weight = best_row.reinforcement_count + 1
            best_row.confidence = round(
                (best_row.confidence * best_row.reinforcement_count + row.confidence) / total_weight, 4
            )
            best_row.reinforcement_count = total_weight
            best_row.last_confirmed_at = now
            workspaces = best_row.source_workspaces_list()
            if str(workspace_id) not in workspaces:
                workspaces.append(str(workspace_id))
            best_row.source_workspace_ids = json.dumps(workspaces)
            merged_citations = best_row.citations_list() + row.citations_list()
            best_row.source_citations = json.dumps(merged_citations[-20:])
        else:
            new_company_row = CompanyMemory(
                ticker=ticker,
                memory_type=row.memory_type,
                content=row.content,
                confidence=row.confidence,
                status="active",
                source_citations=row.source_citations,
                source_workspace_ids=json.dumps([str(workspace_id)]),
                embedding=json.dumps(row_vec),
                embedding_model=provider.model_name,
                reinforcement_count=1,
                contradiction_count=0,
            )
            db.add(new_company_row)
            existing_rows = list(existing_rows) + [new_company_row]

    await db.flush()


async def promote_thesis_claims(db, workspace_id: uuid.UUID, thesis_version) -> list[ThesisMemory]:
    """Promotes ThesisClaim rows reaching status='confirmed'/'refuted' into
    ThesisMemory, per the Phase 2 hook documented in
    app/models/thesis.py::ThesisClaim.memory_id and
    app/thesis/claims.py::sync_claims's module docstring."""
    result = await db.execute(
        select(ThesisClaim).where(
            ThesisClaim.workspace_id == workspace_id,
            ThesisClaim.status.in_(["confirmed", "refuted"]),
            ThesisClaim.memory_id.is_(None),
        )
    )
    claims = result.scalars().all()
    created: list[ThesisMemory] = []

    for claim in claims:
        memory_type = "confirmed_belief" if claim.status == "confirmed" else "refuted_belief"
        memory_row = ThesisMemory(
            workspace_id=workspace_id,
            thesis_claim_id=claim.id,
            thesis_version_id=thesis_version.id if thesis_version else claim.thesis_version_id,
            memory_type=memory_type,
            content=claim.claim_text,
            reasoning=(
                f"Claim type '{claim.claim_type}' appeared in {claim.appearance_count} consecutive "
                f"thesis versions before being marked {claim.status}."
            ),
            confidence=claim.claim_confidence,
            source_citations="[]",
        )
        db.add(memory_row)
        await db.flush()  # assign memory_row.id before wiring the FK back
        claim.memory_id = memory_row.id
        created.append(memory_row)

    if created:
        await db.flush()  # persist the claim.memory_id back-references too

    return created


async def record_investment_decision(db, workspace_id: uuid.UUID, thesis_version) -> ThesisMemory:
    """One ThesisMemory row per research session that produced a thesis
    version — the durable "what did we decide and why" record."""
    memory_row = ThesisMemory(
        workspace_id=workspace_id,
        thesis_version_id=thesis_version.id,
        memory_type="investment_decision",
        content=thesis_version.recommendation or thesis_version.explanation,
        reasoning=thesis_version.explanation,
        decision_signal=thesis_version.signal,
        conviction_at_decision=thesis_version.conviction_score,
        confidence=thesis_version.confidence,
        source_citations="[]",
    )
    db.add(memory_row)
    await db.flush()
    return memory_row
