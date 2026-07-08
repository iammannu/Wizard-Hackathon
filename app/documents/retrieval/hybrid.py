"""
Hybrid search — BM25 (lexical) + vector similarity, fused by Reciprocal Rank
Fusion (RRF).

Why RRF over a weighted sum:
  BM25 scores are unbounded and corpus-dependent (a score of 8 means
  something different on a 50-chunk vs. 5000-chunk candidate set); cosine
  similarity is bounded to [-1, 1]. Normalizing both onto one comparable
  scale is exactly the problem RRF avoids — it fuses on rank position
  (score = sum of 1/(k + rank) across methods) instead of raw magnitude, so
  no cross-method calibration is needed. k=60 is the standard RRF constant
  from the original paper (Cormack et al., 2009) — it dampens the influence
  of any single top rank without needing corpus-specific tuning.
"""
import uuid
from typing import Optional

from rank_bm25 import BM25Okapi

from app.documents.indexing import chunk_index
from app.documents.retrieval.vector_store import ScoredChunk, get_vector_store

_RRF_K = 60


def _tokenize(text: str) -> list[str]:
    return text.lower().split()


async def hybrid_candidates(
    db,
    query: str,
    query_vector: list[float],
    ticker: Optional[str] = None,
    doc_type: Optional[str] = None,
    provider_source: Optional[str] = None,
    document_ids: Optional[list[uuid.UUID]] = None,
    candidate_limit: int = 200,
) -> list[ScoredChunk]:
    """Bounded metadata-filtered candidate set, ranked two ways and fused."""
    candidates = await chunk_index.list_candidate_chunks(
        db, ticker=ticker, doc_type=doc_type, provider_source=provider_source,
        document_ids=document_ids, limit=candidate_limit,
    )
    if not candidates:
        return []

    chunk_by_id = {chunk.id: chunk for chunk, _ in candidates}

    # BM25 ranking over the same candidate set's chunk text.
    corpus = [_tokenize(chunk.text) for chunk, _ in candidates]
    bm25 = BM25Okapi(corpus)
    bm25_scores = bm25.get_scores(_tokenize(query))
    bm25_ranked = sorted(
        range(len(candidates)), key=lambda i: bm25_scores[i], reverse=True
    )
    bm25_rank_of = {candidates[i][0].id: rank for rank, i in enumerate(bm25_ranked)}

    # Vector ranking over the same candidate set, scoped via document_ids so
    # the active VectorStore doesn't have to re-derive the metadata filter.
    candidate_ids = [chunk.id for chunk, _ in candidates]
    candidate_doc_ids = list({doc.id for _, doc in candidates})
    vector_store = get_vector_store()
    scored_vectors = await vector_store.similarity_search(
        db, query_vector, top_k=len(candidates), document_ids=candidate_doc_ids or None,
    )
    scored_vectors = [s for s in scored_vectors if s.chunk_id in set(candidate_ids)]
    vector_rank_of = {s.chunk_id: rank for rank, s in enumerate(scored_vectors)}
    vector_by_chunk = {s.chunk_id: s for s in scored_vectors}

    # Reciprocal Rank Fusion across whichever ranking(s) each chunk appears in.
    fused_scores: dict[uuid.UUID, float] = {}
    for chunk_id in chunk_by_id:
        score = 0.0
        if chunk_id in bm25_rank_of:
            score += 1.0 / (_RRF_K + bm25_rank_of[chunk_id])
        if chunk_id in vector_rank_of:
            score += 1.0 / (_RRF_K + vector_rank_of[chunk_id])
        if score > 0:
            fused_scores[chunk_id] = score

    fused_ids = sorted(fused_scores, key=lambda cid: fused_scores[cid], reverse=True)

    results: list[ScoredChunk] = []
    for chunk_id in fused_ids:
        vec = vector_by_chunk.get(chunk_id)
        results.append(
            ScoredChunk(
                chunk_id=chunk_id,
                document_id=chunk_by_id[chunk_id].document_id,
                score=fused_scores[chunk_id],
                vector=vec.vector if vec else [],
            )
        )
    return results
