"""
DocumentEntity — entities extracted from ingested documents, feeding the
Knowledge Graph.

Why it exists:
  app/agents/graph.py already builds a knowledge graph from web-evidence
  text at query time. DocumentEntity is the persistent, accumulating
  counterpart: entities extracted once at ingestion time, from primary
  sources, that survive across research runs and grow richer as more
  documents are ingested ("the graph should evolve as documents
  accumulate" — this table is that accumulation).

How it integrates (milestone 3):
  Extraction happens once per document version, not once per research
  query — cheap, since it runs at ingestion time, not on every request.
  app/agents/graph.py is extended to merge these persistent entities into
  its per-query graph output rather than becoming a second graph engine.

mention_count + confidence let a future consolidation pass merge duplicate
surface forms of the same entity (e.g. "Apple" vs "Apple Inc.") without
needing that logic on day one — the raw signal is captured now either way.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, Integer, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class DocumentEntity(Base):
    __tablename__ = "document_entities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True
    )

    entity_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # "company" | "product" | "executive" | "technology" | "competitor" |
    # "supplier" | "customer" | "country" | "macro_event"

    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "chunk_id": str(self.chunk_id) if self.chunk_id else None,
            "entity_name": self.entity_name,
            "entity_type": self.entity_type,
            "confidence": self.confidence,
            "mention_count": self.mention_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
