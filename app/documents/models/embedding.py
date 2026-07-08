"""
DocumentEmbedding — persisted vector for one (chunk, provider, model) triple.

Why a real table instead of just DocumentChunk's embedding/embedding_model/
embedding_dim columns:
  Those three columns are a single flat slot — they can't hold "this chunk
  embedded by OpenAI *and* also by a local model" and they lose history the
  moment you switch providers/models. A table keyed by
  (chunk_id, provider, model) supports both multiple simultaneous embeddings
  per chunk and safe provider migration. DocumentChunk's three columns are
  kept as a denormalized cache of the *currently active* embedding (whichever
  (provider, model) app.core.config.Settings.embedding_provider currently
  points at) so SQLiteVectorStore's brute-force scan stays a single-table,
  join-free read — see app/documents/retrieval/sqlite_store.py.

content_hash is carried alongside the vector (not just looked up via the
chunk) so a chunk's row can be dedup-checked/reused even if it moves to a
different chunk_id in a later document version (identical boilerplate text
recurring across versions/documents, same dedup guarantee DocumentChunk's
own docstring already promises for content_hash).
"""
import uuid
import json
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class DocumentEmbedding(Base):
    __tablename__ = "document_embeddings"
    __table_args__ = (
        UniqueConstraint("chunk_id", "provider", "model", name="uq_document_embeddings_chunk_provider_model"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    provider: Mapped[str] = mapped_column(String(30), nullable=False)  # "openai" | "voyage" | "local"
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)

    vector: Mapped[str] = mapped_column(Text, nullable=False)  # JSON float array
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def vector_array(self) -> list[float]:
        try:
            return json.loads(self.vector)
        except Exception:
            return []

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "chunk_id": str(self.chunk_id),
            "document_id": str(self.document_id),
            "provider": self.provider,
            "model": self.model,
            "dimension": self.dimension,
            "content_hash": self.content_hash,
            "created_at": self.created_at.isoformat(),
        }
