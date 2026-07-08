"""
Claim Builder — groups evidence into topic clusters and asks an LLM to
synthesize one claim statement per cluster (the same llm_json pattern
app/agents/*.py already uses for synthesis, now shared via app/core/llm.py).

Clustering, not one claim per evidence item: a claim is a synthesized
statement "supported by evidence," plural per the spec — grouping first
means a claim about, e.g., iPhone revenue growth can cite three chunks that
all bear on it, rather than producing three redundant single-source claims.
Clustering reuses evidence_conflict_threshold as the "same topic" bar
(the same notion conflict detection uses to decide two items are
comparable) rather than introducing a second, undocumented similarity
knob — Milestone 2's config additions were score weights / dedupe
threshold / conflict threshold / confidence & count caps, not a third
threshold.

Confidence is computed programmatically from supporting evidence's
EvidenceScore.overall (mean, penalized if any contradiction exists) rather
than asked of the LLM — LLM-reported confidence numbers are not a
calibrated signal (this codebase's own existing confidence system in
app/agents/supervisor.py already computes confidence from structured
inputs rather than trusting a model's self-rating, for the same reason).
The LLM's only job here is producing the claim text; batched into ONE
llm_json call across all clusters, matching conflict.py's O(1)-call
cost-bounding rationale.
"""
from typing import Optional

from app.core.config import get_settings
from app.core.llm import llm_json
from app.documents.evidence.models import Evidence, Claim
from app.documents.evidence.extractor import EvidenceVectors
from app.documents.retrieval.similarity import cosine_similarity

settings = get_settings()

_SYSTEM_PROMPT = (
    "You are a financial research analyst. For each numbered evidence "
    "group below (one or more passages from SEC filings that address the "
    "same topic), write ONE concise claim statement (1-2 sentences) that "
    "is directly supported by those passages. Do not add facts not present "
    "in the passages. Respond with JSON: "
    '{"claims": [{"index": 0, "text": "..."}, ...]}. '
    "Include exactly one entry per group index, in any order."
)


def _cluster_evidence(evidence_list: list[Evidence], vectors: EvidenceVectors, threshold: float, max_clusters: int) -> list[list[Evidence]]:
    ordered = sorted(evidence_list, key=lambda e: e.score.overall, reverse=True)
    clusters: list[list[Evidence]] = []

    for item in ordered:
        item_vector = vectors.get(item.id, [])
        best_cluster_idx: Optional[int] = None
        best_similarity = 0.0
        for idx, cluster in enumerate(clusters):
            representative_vector = vectors.get(cluster[0].id, [])
            similarity = cosine_similarity(item_vector, representative_vector)
            if similarity >= threshold and similarity > best_similarity:
                best_cluster_idx, best_similarity = idx, similarity

        if best_cluster_idx is not None:
            clusters[best_cluster_idx].append(item)
        elif len(clusters) < max_clusters:
            clusters.append([item])
        else:
            # At the cluster cap — attach to whichever existing cluster is
            # most similar, even below threshold, rather than dropping this
            # evidence from claim generation entirely.
            best_idx = max(
                range(len(clusters)),
                key=lambda i: cosine_similarity(item_vector, vectors.get(clusters[i][0].id, [])),
            )
            clusters[best_idx].append(item)

    return clusters


def _build_clusters_prompt(clusters: list[list[Evidence]]) -> str:
    lines = []
    for i, cluster in enumerate(clusters):
        lines.append(f"Group {i}:")
        for evidence in cluster:
            lines.append(f"- {evidence.text[:600]}")
        lines.append("")
    return "\n".join(lines)


def _claim_confidence(cluster: list[Evidence]) -> float:
    base = sum(e.score.overall for e in cluster) / len(cluster)
    has_contradiction = any(e.conflicts_with for e in cluster)
    penalty = 0.3 if has_contradiction else 0.0
    return max(0.0, min(base - penalty, 1.0))


async def build_claims(
    evidence_list: list[Evidence], vectors: EvidenceVectors, threshold: float = None, max_claims: int = None
) -> list[Claim]:
    if not evidence_list:
        return []

    threshold = settings.evidence_conflict_threshold if threshold is None else threshold
    max_claims = settings.evidence_max_claims if max_claims is None else max_claims

    clusters = _cluster_evidence(evidence_list, vectors, threshold, max_claims)
    response = await llm_json(_SYSTEM_PROMPT, _build_clusters_prompt(clusters))
    claim_texts = {item.get("index"): item.get("text") for item in response.get("claims", [])}

    claims: list[Claim] = []
    for i, cluster in enumerate(clusters):
        text = claim_texts.get(i)
        if not text:
            # llm_json failed or omitted this index (see llm_json's
            # never-raise contract) — fall back to the top evidence
            # sentence rather than silently dropping the claim.
            text = cluster[0].text.split(".")[0].strip() + "."

        contradictions = sorted({eid for e in cluster for eid in e.conflicts_with})
        claims.append(
            Claim(
                text=text,
                supporting_evidence_ids=[e.id for e in cluster],
                citations=[e.citation for e in cluster],
                confidence=_claim_confidence(cluster),
                contradictions=contradictions,
            )
        )

    return claims
