"""
DocumentChunk — the retrievable unit of a document.

Why it exists:
  Retrieval, embedding, and citation all operate on chunks, not whole
  documents — a 10-K is 100+ pages; an evidence citation needs to point at
  one paragraph, not "somewhere in Apple's 2024 10-K."

Embedding storage (why a JSON TEXT column, not a vector type):
  SQLite has no native vector type. Storing the embedding as a JSON-encoded
  float array in TEXT, with embedding_model/embedding_dim recorded alongside
  it, keeps the column portable and self-describing. The retrieval layer
  never reads this column directly — it goes through
  app/documents/embeddings/embedder.py's store/load functions, so migrating
  to a real pgvector column later touches only that module, not this model
  or anything that calls retrieval.

content_hash is the embedding-dedup key: identical chunk text (boilerplate
legal language repeated across every 10-K, for instance) is embedded once
and never again — see embeddings/embedder.py (milestone 2).
"""
import uuid
import json
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, Text, Integer, Float, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_version_id", "chunk_index", name="uq_document_chunks_version_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Embedding — populated by app/documents/embeddings/embedder.py (milestone 2)
    embedding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON float array
    embedding_model: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    embedding_dim: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def embedding_vector(self) -> Optional[list[float]]:
        if not self.embedding:
            return None
        try:
            return json.loads(self.embedding)
        except Exception:
            return None

    def to_dict(self, include_text: bool = True) -> dict:
        data = {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "document_version_id": str(self.document_version_id),
            "chunk_index": self.chunk_index,
            "section": self.section,
            "page_number": self.page_number,
            "token_count": self.token_count,
            "has_embedding": self.embedding is not None,
            "created_at": self.created_at.isoformat(),
        }
        if include_text:
            data["text"] = self.text
        return data
