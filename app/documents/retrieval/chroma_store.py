"""
ChromaVectorStore — delegates both storage and metadata filtering to a local
Chroma persistent collection instead of numpy/SQL. document_embeddings is
still the source of truth (EmbeddingService always writes there first); this
adapter lazily syncs unsynced rows into Chroma on each search, so switching
vector_store_provider to "chroma" and back to "sqlite" never loses data —
Chroma is a queryable cache/index over the same authoritative rows.

Requires `pip install chromadb` (lazy-imported — not a core dependency).
"""
import uuid
from typing import Optional

from sqlalchemy import select

from app.core.config import get_settings
from app.documents.models.chunk import DocumentChunk
from app.documents.models.document import Document
from app.documents.models.embedding import DocumentEmbedding
from app.documents.embeddings.provider import get_active_provider_model
from app.documents.retrieval.vector_store import VectorStore, ScoredChunk

settings = get_settings()


class ChromaVectorStore(VectorStore):
    def __init__(self):
        try:
            import chromadb
        except ImportError as e:
            raise RuntimeError(
                "chromadb is not installed. Run `pip install chromadb` "
                "before selecting vector_store_provider=chroma."
            ) from e
        self._client = chromadb.PersistentClient(path=settings.chroma_persist_dir)

    def _collection(self, provider: str, model: str):
        name = f"chunks_{provider}_{model}".replace("-", "_").replace(".", "_")
        return self._client.get_or_create_collection(name=name)

    async def _sync(self, db, collection, provider: str, model: str) -> None:
        """Upsert any document_embeddings rows this collection doesn't have
        yet. Chroma upsert is id-keyed and idempotent, so re-syncing already
        present rows is a harmless no-op, not a growing duplicate set."""
        result = await db.execute(
            select(DocumentEmbedding, Document.ticker, Document.doc_type, Document.provider_source)
            .join(Document, DocumentEmbedding.document_id == Document.id)
            .where(DocumentEmbedding.provider == provider, DocumentEmbedding.model == model)
        )
        rows = result.all()
        if not rows:
            return

        ids, embeddings, metadatas = [], [], []
        for emb, ticker, doc_type, provider_source in rows:
            ids.append(str(emb.chunk_id))
            embeddings.append(emb.vector_array())
            metadatas.append(
                {
                    "document_id": str(emb.document_id),
                    "ticker": ticker or "",
                    "doc_type": doc_type or "",
                    "provider_source": provider_source or "",
                }
            )
        collection.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas)

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
        collection = self._collection(provider, model)
        await self._sync(db, collection, provider, model)

        where_clauses = []
        if ticker:
            where_clauses.append({"ticker": ticker.upper()})
        if doc_type:
            where_clauses.append({"doc_type": doc_type})
        if provider_source:
            where_clauses.append({"provider_source": provider_source})
        where = {"$and": where_clauses} if len(where_clauses) > 1 else (where_clauses[0] if where_clauses else None)

        result = collection.query(
            query_embeddings=[query_vector], n_results=top_k, where=where, include=["distances", "embeddings", "metadatas"]
        )
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        embeddings = result.get("embeddings", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]

        scored: list[ScoredChunk] = []
        for chunk_id_str, distance, vector, metadata in zip(ids, distances, embeddings, metadatas):
            # Chroma's default space is L2 distance; convert to a
            # similarity-style score (higher = better) for a consistent
            # ScoredChunk.score contract across all VectorStore adapters.
            score = 1.0 / (1.0 + distance)
            scored.append(
                ScoredChunk(
                    chunk_id=uuid.UUID(chunk_id_str),
                    document_id=uuid.UUID(metadata["document_id"]),
                    score=score,
                    vector=list(vector),
                )
            )
        return scored
