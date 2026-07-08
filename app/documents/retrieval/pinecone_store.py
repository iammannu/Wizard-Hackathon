"""
PineconeVectorStore — hosted vector DB. document_embeddings remains the
source of truth; this adapter syncs unsynced rows into a Pinecone index by
upserting with (chunk_id) as the vector id and (document_id, ticker,
doc_type, provider_source) as metadata for filtered queries, same "sync
then query" shape as ChromaVectorStore.

Requires `pip install pinecone-client` (lazy-imported) and pinecone_api_key
set in .env — neither is configured today, so this adapter cannot be
integration-tested in this environment; it's written for correctness against
Pinecone's documented v3 client API.
"""
import uuid
from typing import Optional

from sqlalchemy import select

from app.core.config import get_settings
from app.documents.models.document import Document
from app.documents.models.embedding import DocumentEmbedding
from app.documents.embeddings.provider import get_active_provider_model
from app.documents.retrieval.vector_store import VectorStore, ScoredChunk

settings = get_settings()


class PineconeVectorStore(VectorStore):
    def __init__(self):
        try:
            from pinecone import Pinecone
        except ImportError as e:
            raise RuntimeError(
                "pinecone-client is not installed. Run `pip install pinecone-client` "
                "before selecting vector_store_provider=pinecone."
            ) from e

        api_key = settings.pinecone_api_key.strip()
        if not api_key:
            raise RuntimeError(
                "PINECONE_API_KEY is not configured. Set pinecone_api_key in .env "
                "before selecting vector_store_provider=pinecone."
            )
        self._client = Pinecone(api_key=api_key)
        self._index = self._client.Index(settings.pinecone_index_name)

    async def _sync(self, db, provider: str, model: str) -> None:
        result = await db.execute(
            select(DocumentEmbedding, Document.ticker, Document.doc_type, Document.provider_source)
            .join(Document, DocumentEmbedding.document_id == Document.id)
            .where(DocumentEmbedding.provider == provider, DocumentEmbedding.model == model)
        )
        rows = result.all()
        if not rows:
            return

        vectors = [
            (
                str(emb.chunk_id),
                emb.vector_array(),
                {
                    "document_id": str(emb.document_id),
                    "ticker": ticker or "",
                    "doc_type": doc_type or "",
                    "provider_source": provider_source or "",
                },
            )
            for emb, ticker, doc_type, provider_source in rows
        ]
        # Pinecone's client is synchronous; batch upserts of 100 (its documented max).
        for i in range(0, len(vectors), 100):
            self._index.upsert(vectors=vectors[i : i + 100])

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
        await self._sync(db, provider, model)

        filter_dict = {}
        if ticker:
            filter_dict["ticker"] = ticker.upper()
        if doc_type:
            filter_dict["doc_type"] = doc_type
        if provider_source:
            filter_dict["provider_source"] = provider_source

        response = self._index.query(
            vector=query_vector, top_k=top_k, filter=filter_dict or None, include_metadata=True, include_values=True
        )
        return [
            ScoredChunk(
                chunk_id=uuid.UUID(match["id"]),
                document_id=uuid.UUID(match["metadata"]["document_id"]),
                score=float(match["score"]),
                vector=match.get("values", []),
            )
            for match in response.get("matches", [])
        ]
