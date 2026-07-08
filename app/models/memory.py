"""
AI Memory persistence models — Milestone 3.

Four tables, each serving a distinct scope in the memory hierarchy:

  ConversationMemory — one append-only row per completed research session
                       (the raw extraction record, before consolidation).
  WorkspaceMemory    — the atomic, semantically-searchable memory unit,
                       scoped to a workspace. What consolidator.py dedupes/
                       reinforces and what retriever.py searches by default.
  CompanyMemory      — the same atomic shape as WorkspaceMemory but scoped
                       to a ticker instead of a workspace, so knowledge
                       learned in one workspace ("AAPL depends heavily on
                       Foxconn") is available to every other workspace that
                       later researches AAPL.
  ThesisMemory       — the Phase 2 promotion target predicted by
                       app/models/thesis.py's ThesisClaim.memory_id: once a
                       claim reaches status="confirmed" or "refuted", it's
                       promoted here as a durable belief/decision record.

Design decisions (matching app/models/thesis.py's established conventions):
  - JSON fields stored as Text for SQLite portability, with json.loads/dumps
    accessor methods and a to_dict() for API serialization.
  - No SQLAlchemy relationship() — joins done explicitly in queries, async-
    session-safe.
  - Timestamps are timezone-aware UTC.
  - Embedding vectors stored as a JSON Text column (same denormalized-cache
    pattern as DocumentChunk.embedding in app/documents/models/chunk.py),
    not a separate embeddings table — memory volume per workspace/company is
    orders of magnitude smaller than document chunks, so a dedicated table +
    join isn't justified yet.

Future integration points:
  - Milestone 5 (Portfolio Intelligence): CompanyMemory is what a Holding's
    "why do we own this" panel reads from directly.
  - Milestone 6 (Prediction Tracking): ThesisMemory rows of type
    "investment_decision" are the natural seed for PredictionRecord rows.
"""
import uuid
import json
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, Text, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

# Shared across all three memory-item tables (Workspace/Company/Thesis) —
# kept as a plain tuple, not a DB-level CHECK constraint, so SQLite migrations
# stay additive-only if a new type is ever needed.
MEMORY_TYPES = (
    "fact", "belief", "investment_decision",
    "open_question", "resolved_question", "user_note",
)


# ---------------------------------------------------------------------------
# ConversationMemory
# ---------------------------------------------------------------------------

class ConversationMemory(Base):
    """
    One row per completed research session — the raw output of
    app/memory/extractor.py before consolidator.py dedupes/reinforces it into
    WorkspaceMemory. Append-only audit trail: never updated after insert, so
    "what did we learn from this specific conversation" is always answerable
    even after later sessions supersede its conclusions.
    """
    __tablename__ = "conversation_memories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    research_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("workspace_research.id", ondelete="SET NULL"), nullable=True
    )

    query: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Raw extracted candidates for this session — JSON list of
    # {memory_type, content, confidence, tickers, source_citations}, the
    # exact shape app/memory/extractor.py produces, before any consolidation
    # decision (new/reinforce/contradict) is applied.
    extracted_items: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def extracted_items_list(self) -> list:
        try:
            return json.loads(self.extracted_items or "[]")
        except Exception:
            return []

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "workspace_id": str(self.workspace_id),
            "research_id": str(self.research_id) if self.research_id else None,
            "query": self.query,
            "summary": self.summary,
            "extracted_items": self.extracted_items_list(),
            "item_count": self.item_count,
            "created_at": self.created_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# WorkspaceMemory
# ---------------------------------------------------------------------------

class WorkspaceMemory(Base):
    """
    The atomic, semantically-searchable memory unit, scoped to one workspace.

    A new research session's extracted items are consolidated against these
    rows (app/memory/consolidator.py): a near-duplicate reinforces the
    existing row (reinforcement_count++, confidence recalculated) rather than
    creating a new one; a same-topic-but-opposing item is recorded as a
    contradiction and lowers confidence instead of silently overwriting.
    """
    __tablename__ = "workspace_memories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )

    memory_type: Mapped[str] = mapped_column(String(30), nullable=False)  # one of MEMORY_TYPES
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tickers: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON array

    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )  # "active" | "resolved" | "superseded" | "retracted"

    source_citations: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list of citation dicts

    # Semantic retrieval — same embedding provider/model as the Evidence Engine
    embedding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON float array
    embedding_model: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)

    # Longitudinal tracking, mirrors ThesisClaim's appearance-tracking fields
    first_research_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    last_research_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    reinforcement_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    contradiction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def tickers_list(self) -> list:
        try:
            return json.loads(self.tickers or "[]")
        except Exception:
            return []

    def citations_list(self) -> list:
        try:
            return json.loads(self.source_citations or "[]")
        except Exception:
            return []

    def embedding_vector(self) -> Optional[list]:
        if not self.embedding:
            return None
        try:
            return json.loads(self.embedding)
        except Exception:
            return None

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "workspace_id": str(self.workspace_id),
            "memory_type": self.memory_type,
            "content": self.content,
            "tickers": self.tickers_list(),
            "confidence": self.confidence,
            "status": self.status,
            "source_citations": self.citations_list(),
            "reinforcement_count": self.reinforcement_count,
            "contradiction_count": self.contradiction_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# CompanyMemory
# ---------------------------------------------------------------------------

class CompanyMemory(Base):
    """
    Cross-workspace durable knowledge about a single company, keyed by
    ticker rather than workspace_id. Populated by
    app/memory/consolidator.py rolling up WorkspaceMemory items that clear
    Settings.memory_company_promotion_min_confidence — this is what makes
    "we already knew this about AAPL" survive across unrelated workspaces
    instead of being siloed per-workspace.
    """
    __tablename__ = "company_memories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    memory_type: Mapped[str] = mapped_column(String(30), nullable=False)  # one of MEMORY_TYPES
    content: Mapped[str] = mapped_column(Text, nullable=False)

    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    source_citations: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    source_workspace_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list — every workspace that contributed to this belief

    embedding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)

    reinforcement_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    contradiction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    last_confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def citations_list(self) -> list:
        try:
            return json.loads(self.source_citations or "[]")
        except Exception:
            return []

    def source_workspaces_list(self) -> list:
        try:
            return json.loads(self.source_workspace_ids or "[]")
        except Exception:
            return []

    def embedding_vector(self) -> Optional[list]:
        if not self.embedding:
            return None
        try:
            return json.loads(self.embedding)
        except Exception:
            return None

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "ticker": self.ticker,
            "memory_type": self.memory_type,
            "content": self.content,
            "confidence": self.confidence,
            "status": self.status,
            "source_citations": self.citations_list(),
            "source_workspace_ids": self.source_workspaces_list(),
            "reinforcement_count": self.reinforcement_count,
            "contradiction_count": self.contradiction_count,
            "first_seen_at": self.first_seen_at.isoformat(),
            "last_confirmed_at": self.last_confirmed_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# ThesisMemory
# ---------------------------------------------------------------------------

class ThesisMemory(Base):
    """
    Promotion target for ThesisClaim.memory_id (app/models/thesis.py).

    Created when a claim reaches status="confirmed" (durable belief) or
    "refuted" (contradiction worth remembering, so the same dead-end isn't
    re-litigated next session), or when a thesis version represents a
    concrete investment decision (signal + recommendation pair worth
    recalling verbatim later, independent of the atomic-claim mechanism).
    """
    __tablename__ = "thesis_memories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    thesis_claim_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("thesis_claims.id", ondelete="SET NULL"), nullable=True
    )
    thesis_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("thesis_versions.id", ondelete="SET NULL"), nullable=True
    )

    memory_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # "confirmed_belief" | "refuted_belief" | "investment_decision"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Populated only for memory_type="investment_decision"
    decision_signal: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    conviction_at_decision: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    source_citations: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def citations_list(self) -> list:
        try:
            return json.loads(self.source_citations or "[]")
        except Exception:
            return []

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "workspace_id": str(self.workspace_id),
            "thesis_claim_id": str(self.thesis_claim_id) if self.thesis_claim_id else None,
            "thesis_version_id": str(self.thesis_version_id) if self.thesis_version_id else None,
            "memory_type": self.memory_type,
            "content": self.content,
            "reasoning": self.reasoning,
            "decision_signal": self.decision_signal,
            "conviction_at_decision": self.conviction_at_decision,
            "confidence": self.confidence,
            "source_citations": self.citations_list(),
            "created_at": self.created_at.isoformat(),
        }
