"""
Maximal Marginal Relevance reranking — diversifies the final top-k so
several near-duplicate chunks (boilerplate legal language repeated across
a 10-K's sections, for instance) don't crowd out one genuinely different,
relevant chunk.

Relevance term: each candidate's incoming `score` (already produced by
hybrid.py's RRF fusion, or a VectorStore's cosine score for pure-semantic
callers) is used directly as the relevance signal, rather than
recomputing cosine-to-query — RRF-fused rank scores and raw cosine scores
aren't on the same scale as a fresh cosine computation would be, and the
fused score already *is* the query-relevance judgment for this candidate
set. Redundancy term: cosine similarity between candidate vectors — skipped
(treated as no penalty) for any candidate missing a vector, e.g. a BM25-only
match whose chunk isn't embedded yet.
"""
from app.documents.retrieval.vector_store import ScoredChunk
from app.documents.retrieval.similarity import cosine_similarity as _cosine


def mmr_rerank(
    candidates: list[ScoredChunk], top_k: int, lambda_mult: float = 0.5
) -> list[ScoredChunk]:
    if not candidates:
        return []

    # Relevance normalized to [0, 1] so it's comparable to the [-1, 1]-ish
    # redundancy term under one lambda weighting.
    max_score = max(c.score for c in candidates) or 1.0
    remaining = list(candidates)
    selected: list[ScoredChunk] = []

    while remaining and len(selected) < top_k:
        best_idx, best_value = 0, float("-inf")
        for i, candidate in enumerate(remaining):
            relevance = candidate.score / max_score
            redundancy = max((_cosine(candidate.vector, s.vector) for s in selected), default=0.0)
            mmr_value = lambda_mult * relevance - (1 - lambda_mult) * redundancy
            if mmr_value > best_value:
                best_idx, best_value = i, mmr_value
        selected.append(remaining.pop(best_idx))

    return selected
