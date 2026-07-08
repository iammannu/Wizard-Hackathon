"""
VectorStore — the abstraction that lets Pinecone, pgvector, FAISS, and Chroma
be swapped for the active similarity-search backend without touching
anything in app/documents/retrieval/hybrid.py, mmr.py, or service.py — they
only ever call similarity_search() through this interface.

Selected via Settings.vector_store_provider ("sqlite" is the active default;
faiss/chroma/pinecone/pgvector are fully implemented but lazy-import their
SDK, so the app runs fine without those packages installed unless selected).
"""
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import get_settings

settings = get_settings()


@dataclass
class ScoredChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    score: float  # cosine similarity, higher = better
    vector: list[float] = field(default_factory=list)  # carried through for MMR's redundancy term


class VectorStore(ABC):
    @abstractmethod
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
        """Top-k chunks by cosine similarity to query_vector, filtered by
        whatever metadata is provided."""


def get_vector_store(name: Optional[str] = None) -> VectorStore:
    key = (name or settings.vector_store_provider).strip().lower()

    if key == "sqlite":
        from app.documents.retrieval.sqlite_store import SQLiteVectorStore

        return SQLiteVectorStore()
    if key == "faiss":
        from app.documents.retrieval.faiss_store import FAISSVectorStore

        return FAISSVectorStore()
    if key == "chroma":
        from app.documents.retrieval.chroma_store import ChromaVectorStore

        return ChromaVectorStore()
    if key == "pinecone":
        from app.documents.retrieval.pinecone_store import PineconeVectorStore

        return PineconeVectorStore()
    if key == "pgvector":
        from app.documents.retrieval.pgvector_store import PgVectorStore

        return PgVectorStore()

    raise ValueError(
        f"Unknown vector_store_provider '{key}'. Valid options: "
        f"sqlite, faiss, chroma, pinecone, pgvector"
    )
