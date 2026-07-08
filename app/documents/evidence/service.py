"""
Evidence Pack orchestration — the full Milestone 2 pipeline:

  Hybrid Search -> MMR -> Evidence Extraction -> Evidence Scoring ->
  Deduplication -> Conflict Detection -> Claim Builder -> Citation Builder
  -> Evidence Pack

This is what app/documents/retrieval/service.py's search() now delegates to
(replacing the old hydrate + pack_context tail of the Milestone 1 pipeline),
and what app.agents.base.search_evidence() ultimately returns.
"""
import uuid
from typing import Optional

from app.core.config import get_settings
from app.documents.embeddings.provider import get_embedding_provider
from app.documents.retrieval.hybrid import hybrid_candidates
from app.documents.retrieval.mmr import mmr_rerank
from app.documents.retrieval.context_packer import pack_context
from app.documents.evidence.models import Evidence, EvidencePack, RetrievalMetadata
from app.documents.evidence.extractor import extract_evidence
from app.documents.evidence.scorer import score_evidence
from app.documents.evidence.dedup import deduplicate
from app.documents.evidence.conflict import detect_conflicts
from app.documents.evidence.claims import build_claims

settings = get_settings()


async def build_evidence_pack(
    db,
    query: str,
    ticker: Optional[str] = None,
    doc_type: Optional[str] = None,
    provider_source: Optional[str] = None,
    document_ids: Optional[list[uuid.UUID]] = None,
    top_k: Optional[int] = None,
    use_mmr: bool = True,
    mmr_lambda: float = 0.5,
    max_context_tokens: Optional[int] = None,
) -> EvidencePack:
    top_k = min(top_k or settings.retrieval_top_k_default, settings.evidence_max_returned)

    provider = get_embedding_provider()
    query_vector = await provider.embed_query(query)

    candidates = await hybrid_candidates(
        db, query, query_vector, ticker=ticker, doc_type=doc_type,
        provider_source=provider_source, document_ids=document_ids,
    )

    # Pull a larger pool than the final target so dedup/min-confidence
    # filtering has room to remove items without starving the final count.
    mmr_pool_size = min(len(candidates), max(top_k * 3, settings.evidence_max_returned))
    ranked_candidates = mmr_rerank(candidates, top_k=mmr_pool_size, lambda_mult=mmr_lambda) if use_mmr else candidates[:mmr_pool_size]

    evidence_list, vectors = await extract_evidence(db, ranked_candidates)
    evidence_list = score_evidence(evidence_list, vectors, query, query_vector)

    before_confidence_filter = len(evidence_list)
    evidence_list = [e for e in evidence_list if e.score.overall >= settings.evidence_min_confidence]
    vectors = {e.id: vectors[e.id] for e in evidence_list if e.id in vectors}

    evidence_list, vectors, duplicates_removed = deduplicate(evidence_list, vectors, threshold=settings.evidence_dedupe_threshold)

    # Final cap, highest-scoring first.
    evidence_list = sorted(evidence_list, key=lambda e: e.score.overall, reverse=True)[:top_k]
    vectors = {e.id: vectors[e.id] for e in evidence_list if e.id in vectors}

    conflict_summary = await detect_conflicts(evidence_list, vectors, threshold=settings.evidence_conflict_threshold)
    claims = await build_claims(evidence_list, vectors, threshold=settings.evidence_conflict_threshold, max_claims=settings.evidence_max_claims)

    # Citations/claims/confidence are computed from the full evidence set
    # (below) before any context-budget truncation, since trimming evidence
    # text for the raw `evidence` field shouldn't retroactively weaken
    # already-synthesized claims or drop their citations.
    citations_by_id = {e.citation.citation_id: e.citation for e in evidence_list}
    confidence = _pack_confidence(evidence_list, conflict_summary)

    packed_evidence = pack_context(evidence_list, max_tokens=max_context_tokens) if max_context_tokens else evidence_list

    metadata = RetrievalMetadata(
        query=query, ticker=ticker, doc_type=doc_type, provider_source=provider_source,
        top_k=top_k, use_mmr=use_mmr, mmr_lambda=mmr_lambda, hybrid_candidate_count=len(candidates),
    )
    retrieval_stats = {
        "candidates_considered": len(candidates),
        "after_mmr": len(ranked_candidates),
        "before_confidence_filter": before_confidence_filter,
        "duplicates_removed": duplicates_removed,
        "final_evidence_count": len(evidence_list),
    }

    return EvidencePack(
        query=query,
        evidence=packed_evidence,
        claims=claims,
        citations=list(citations_by_id.values()),
        confidence=confidence,
        metadata=metadata,
        retrieval_stats=retrieval_stats,
        conflict_summary=conflict_summary,
    )


def _pack_confidence(evidence_list: list[Evidence], conflict_summary: dict) -> float:
    if not evidence_list:
        return 0.0
    base = sum(e.score.overall for e in evidence_list) / len(evidence_list)
    penalty = min(0.3, 0.05 * conflict_summary.get("contradicts_count", 0))
    return max(0.0, min(base - penalty, 1.0))
