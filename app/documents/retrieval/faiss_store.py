"""
FAISSVectorStore — local, in-process ANN search. Still no external service
(matches the "no infra until you need it" philosophy), but graduates past
SQLiteVectorStore's O(n) brute-force scan once the chunk corpus is large
enough for that to matter.

document_embeddings (populated by EmbeddingService regardless of which
vector_store_provider is active) stays the source of truth; this adapter
builds an ephemeral faiss.IndexFlatIP per query from the metadata-filtered
candidate set, normalizing vectors so inner product == cosine similarity.
A persistent, incrementally-updated on-disk index (faiss_index_path) is the
natural next step once profiling shows the per-query rebuild is the
bottleneck — not needed at this milestone's corpus scale.

Requires `pip install faiss-cpu` (lazy-imported — not a core dependency).
"""
import uuid
from typing import Optional

from sqlalchemy import select

from app.documents.models.chunk import DocumentChunk
from app.documents.models.document import Document
from app.documents.models.embedding import DocumentEmbedding
from app.documents.embeddings.provider import get_active_provider_model
from app.documents.retrieval.vector_store import VectorStore, ScoredChunk


class FAISSVectorStore(VectorStore):
    def __init__(self):
        try:
            import faiss  # noqa: F401
            import numpy as np  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "faiss-cpu is not installed. Run `pip install faiss-cpu` "
                "before selecting vector_store_provider=faiss."
            ) from e

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
        import faiss
        import numpy as np

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

        vectors = np.array([e.vector_array() for e in embeddings], dtype=np.float32)
        faiss.normalize_L2(vectors)
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)

        query_arr = np.array([query_vector], dtype=np.float32)
        faiss.normalize_L2(query_arr)
        scores, indices = index.search(query_arr, min(top_k, len(embeddings)))

        results: list[ScoredChunk] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            emb = embeddings[idx]
            results.append(
                ScoredChunk(chunk_id=emb.chunk_id, document_id=emb.document_id, score=float(score), vector=emb.vector_array())
            )
        return results
