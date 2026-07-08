"""
SQLiteVectorStore — the active default VectorStore.

Brute-force cosine similarity computed with numpy over document_embeddings,
manually joined to document_chunks/documents for metadata filters (no ORM
relationship(), same convention as app/documents/indexing/). Fine at this
corpus's scale (a handful of SEC filings, low thousands of chunks) —
consistent with the repo's "no infra until you need it" philosophy (see
CLAUDE.md's cache/DB "graduate from this" section). Swap vector_store_provider
to faiss once the candidate set is large enough that a brute-force scan is
the bottleneck.
"""
import uuid
from typing import Optional

import numpy as np
from sqlalchemy import select

from app.documents.models.chunk import DocumentChunk
from app.documents.models.document import Document
from app.documents.models.embedding import DocumentEmbedding
from app.documents.embeddings.provider import get_active_provider_model
from app.documents.retrieval.vector_store import VectorStore, ScoredChunk


class SQLiteVectorStore(VectorStore):
    async def similarity_search(
        self,
        db,
        query_vector: list[float],
        top_k: int = 20,
        ticker: Optional[str] = None,
        doc_type: Optional[str] = None,
        provider_source: Optional[str] = None,
        document_ids: Optional[list[uuid.UUID]] = None,
    ) -> list[ScoredChunk]:
        provider, model = get_active_provider_model()

        query = (
            select(DocumentEmbedding)
            .join(DocumentChunk, DocumentEmbedding.chunk_id == DocumentChunk.id)
            .join(Document, DocumentEmbedding.document_id == Document.id)
            .where(DocumentEmbedding.provider == provider, DocumentEmbedding.model == model)
        )
        if ticker:
            query = query.where(Document.ticker == ticker.upper())
        if doc_type:
            query = query.where(Document.doc_type == doc_type)
        if provider_source:
            query = query.where(Document.provider_source == provider_source)
        if document_ids:
            query = query.where(DocumentEmbedding.document_id.in_(document_ids))

        result = await db.execute(query)
        embeddings = list(result.scalars().all())
        if not embeddings:
            return []

        query_arr = np.array(query_vector, dtype=np.float32)
        query_norm = np.linalg.norm(query_arr) or 1.0

        scored: list[ScoredChunk] = []
        for emb in embeddings:
            vec = emb.vector_array()
            if not vec:
                continue
            vec_arr = np.array(vec, dtype=np.float32)
            vec_norm = np.linalg.norm(vec_arr) or 1.0
            cosine = float(np.dot(query_arr, vec_arr) / (query_norm * vec_norm))
            scored.append(ScoredChunk(chunk_id=emb.chunk_id, document_id=emb.document_id, score=cosine, vector=vec))

        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:top_k]
