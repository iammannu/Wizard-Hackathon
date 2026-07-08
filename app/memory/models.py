"""
AI Memory domain models — Milestone 3.

Pydantic, matching app/documents/evidence/models.py's convention: these
objects cross the extraction -> consolidation -> retrieval -> agent/API
boundary, so they need typed validation and JSON serialization, unlike the
SQLAlchemy rows in app/models/memory.py which never leave the DB layer
directly (retriever.py converts rows -> MemoryItem before returning).

Raw embedding vectors are deliberately NOT a field here, same reasoning as
Evidence: they're an internal detail of consolidator.py/retriever.py, not
something a consumer of MemoryPack needs.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field

from app.models.memory import MEMORY_TYPES  # noqa: F401  (re-exported for callers that only import this module)


class MemorySourceCitation(BaseModel):
    """Where a memory item's belief came from — a research session and,
    when the memory was grounded in retrieved document evidence, the exact
    Evidence Engine citation_id (app/documents/evidence/models.py's
    Citation) so provenance chains all the way to a primary source."""

    research_id: Optional[uuid.UUID] = None
    workspace_id: Optional[uuid.UUID] = None
    evidence_citation_id: Optional[str] = None
    query: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MemoryCandidate(BaseModel):
    """One fact/belief/decision/question/note proposed by
    app/memory/extractor.py from a completed research session, before
    app/memory/consolidator.py decides whether it's new, reinforces an
    existing item, or contradicts one."""

    memory_type: str  # one of app.models.memory.MEMORY_TYPES
    content: str
    confidence: float
    tickers: list[str] = Field(default_factory=list)
    citations: list[MemorySourceCitation] = Field(default_factory=list)
    # Populated only when memory_type == "investment_decision"
    decision_signal: Optional[str] = None


class MemoryItem(BaseModel):
    """A persisted memory row (WorkspaceMemory or CompanyMemory), DB-model-
    agnostic — what app/memory/retriever.py returns to callers."""

    id: uuid.UUID
    scope: str  # "workspace" | "company"
    scope_key: str  # workspace_id (as str) for "workspace" scope, ticker for "company" scope
    memory_type: str
    content: str
    confidence: float
    status: str
    similarity: float = 0.0  # cosine similarity to the recall query; 0.0 when not from a semantic search
    reinforcement_count: int = 1
    contradiction_count: int = 0
    source_citations: list[dict] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class MemoryPack(BaseModel):
    """Result of a recall() call — what app.agents.base.recall_memory() and
    the read-only memory router return."""

    query: str
    items: list[MemoryItem]
    workspace_id: Optional[str] = None
    ticker: Optional[str] = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
