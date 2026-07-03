"""
Thesis persistence models for the Living Investment Thesis system.

Three tables — each append-only or grow-only, no destructive writes:

  ThesisVersion      — versioned snapshot of a workspace thesis after each research run.
  ConfidenceSnapshot — pure time-series for charting confidence/conviction evolution.
  ThesisClaim        — atomic claim units extracted from thesis content; tracked across
                       versions to detect which claims persist, strengthen, or get refuted.

Design decisions:
  - All FK columns point to parent tables but are stored without SQLAlchemy ORM relationships
    (relationship() causes eager-load complexity with async sessions). Joins are done in queries.
  - JSON fields are stored as Text for maximum DB portability (SQLite has no native JSON type;
    PostgreSQL json/jsonb can be used via a dialect-specific column when we migrate).
  - Timestamps use timezone-aware UTC throughout; never use naive datetimes.
  - self-referential previous_version_id is nullable because version 1 has no predecessor.

Future integration points:
  - Phase 2 (AI Memory): ThesisClaim.memory_id FK populated when claims are promoted to MemoryEntry
  - Phase 5 (Monitoring): ThesisVersion.lifecycle_stage consumed by alert rules
  - Phase 6 (Alerts): ThesisVersion.is_major_change + change_type trigger notification events
  - Phase 8 (Prediction Tracking): ThesisVersion used as the falsifiable prediction record
"""
import uuid
import json
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, Text, Float, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


# ---------------------------------------------------------------------------
# ThesisVersion
# ---------------------------------------------------------------------------

class ThesisVersion(Base):
    """
    One record per research run that completes for a workspace.

    Version numbers are sequential per workspace (1, 2, 3 …) and managed by
    app/thesis/versioner.py — never set them manually.

    The `diff` column holds a ThesisDiff JSON blob computed by comparator.py,
    describing what changed from the previous version. Null on version 1.
    """
    __tablename__ = "thesis_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    research_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("workspace_research.id", ondelete="SET NULL"), nullable=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # How this version was triggered — forward-compatible with Phase 5 scheduler
    triggered_by: Mapped[str] = mapped_column(
        String(50), nullable=False, default="user_query"
    )  # "user_query" | "scheduled_refresh" | "alert_trigger" | "document_ingestion"
    trigger_query: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Core thesis fields — structured, never a single text blob
    signal: Mapped[str] = mapped_column(String(20), nullable=False, default="neutral")
    recommendation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    conviction_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Structured JSON content — stored as Text for DB portability
    bull_case: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    bear_case: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    key_risks: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    key_assumptions: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    invalidation_conditions: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    known_unknowns: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # Evidence snapshot at the moment this version was created
    evidence_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_coverage: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    evidence_providers: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # Agent signals snapshot — enables per-agent signal drift tracking
    agent_signals: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    active_agents: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # Lifecycle state machine — consumed by Phase 5/6 (monitoring, alerts)
    lifecycle_stage: Mapped[str] = mapped_column(
        String(30), nullable=False, default="forming"
    )  # "forming" | "established" | "evolving" | "challenged" | "invalidated"
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )  # "active" | "superseded" | "archived"

    # Change detection — null on version 1
    previous_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("thesis_versions.id", ondelete="SET NULL"), nullable=True
    )
    diff: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # ThesisDiff JSON
    is_major_change: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    change_type: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True
    )  # "reinforced" | "evolved" | "challenged" | "invalidated"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Accessors — parse stored JSON without hitting the DB again
    # ------------------------------------------------------------------

    def bull_case_dict(self) -> dict:
        try:
            return json.loads(self.bull_case or "{}")
        except Exception:
            return {}

    def bear_case_dict(self) -> dict:
        try:
            return json.loads(self.bear_case or "{}")
        except Exception:
            return {}

    def key_risks_list(self) -> list:
        try:
            return json.loads(self.key_risks or "[]")
        except Exception:
            return []

    def key_assumptions_list(self) -> list:
        try:
            return json.loads(self.key_assumptions or "[]")
        except Exception:
            return []

    def invalidation_conditions_list(self) -> list:
        try:
            return json.loads(self.invalidation_conditions or "[]")
        except Exception:
            return []

    def known_unknowns_list(self) -> list:
        try:
            return json.loads(self.known_unknowns or "[]")
        except Exception:
            return []

    def agent_signals_dict(self) -> dict:
        try:
            return json.loads(self.agent_signals or "{}")
        except Exception:
            return {}

    def active_agents_list(self) -> list:
        try:
            return json.loads(self.active_agents or "[]")
        except Exception:
            return []

    def diff_dict(self) -> Optional[dict]:
        if not self.diff:
            return None
        try:
            return json.loads(self.diff)
        except Exception:
            return None

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "workspace_id": str(self.workspace_id),
            "research_id": str(self.research_id) if self.research_id else None,
            "version_number": self.version_number,
            "triggered_by": self.triggered_by,
            "trigger_query": self.trigger_query,
            "signal": self.signal,
            "recommendation": self.recommendation,
            "explanation": self.explanation,
            "conviction_score": self.conviction_score,
            "confidence": self.confidence,
            "bull_case": self.bull_case_dict(),
            "bear_case": self.bear_case_dict(),
            "key_risks": self.key_risks_list(),
            "key_assumptions": self.key_assumptions_list(),
            "invalidation_conditions": self.invalidation_conditions_list(),
            "known_unknowns": self.known_unknowns_list(),
            "evidence_source_count": self.evidence_source_count,
            "evidence_coverage": self.evidence_coverage,
            "evidence_providers": json.loads(self.evidence_providers or "{}"),
            "agent_signals": self.agent_signals_dict(),
            "active_agents": self.active_agents_list(),
            "lifecycle_stage": self.lifecycle_stage,
            "status": self.status,
            "previous_version_id": str(self.previous_version_id) if self.previous_version_id else None,
            "diff": self.diff_dict(),
            "is_major_change": self.is_major_change,
            "change_type": self.change_type,
            "created_at": self.created_at.isoformat(),
        }

    def to_summary_dict(self) -> dict:
        """Lightweight summary used in version list endpoints."""
        return {
            "id": str(self.id),
            "version_number": self.version_number,
            "signal": self.signal,
            "conviction_score": self.conviction_score,
            "confidence": self.confidence,
            "lifecycle_stage": self.lifecycle_stage,
            "is_major_change": self.is_major_change,
            "change_type": self.change_type,
            "triggered_by": self.triggered_by,
            "trigger_query": self.trigger_query[:120] if self.trigger_query else "",
            "created_at": self.created_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# ConfidenceSnapshot
# ---------------------------------------------------------------------------

class ConfidenceSnapshot(Base):
    """
    Pure time-series record — one row per research run.

    Append-only: rows are never updated. Designed for efficient range queries
    (workspace_id + snapshot_at) to feed confidence evolution charts.

    Stores the full confidence breakdown so the frontend can render multi-metric
    sparklines (raw confidence vs conviction vs evidence boost) without joins.
    """
    __tablename__ = "confidence_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    thesis_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("thesis_versions.id", ondelete="CASCADE"), nullable=False
    )

    # Core metrics
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    conviction_score: Mapped[float] = mapped_column(Float, nullable=False)
    signal: Mapped[str] = mapped_column(String(20), nullable=False)

    # Breakdown components — stored flat for query efficiency
    data_quality: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    signal_agreement: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    evidence_boost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    evidence_sources: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True,
        default=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "workspace_id": str(self.workspace_id),
            "thesis_version_id": str(self.thesis_version_id),
            "confidence": self.confidence,
            "conviction_score": self.conviction_score,
            "signal": self.signal,
            "data_quality": self.data_quality,
            "signal_agreement": self.signal_agreement,
            "evidence_boost": self.evidence_boost,
            "evidence_sources": self.evidence_sources,
            "snapshot_at": self.snapshot_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# ThesisClaim
# ---------------------------------------------------------------------------

class ThesisClaim(Base):
    """
    Atomic claim units extracted from thesis content.

    Each claim is a single, falsifiable statement (bull point, risk, assumption, etc.)
    attributed to a source agent where traceable. Claims are tracked across thesis
    versions: when a claim re-appears, appearance_count increments and
    last_confirmed_version updates. When a claim disappears for 2+ versions it is
    marked 'weakened'; when explicitly contradicted it is marked 'refuted'.

    This is the primary bridge to Phase 2 (AI Memory):
      - Claims with status='confirmed' (3+ versions) → promoted to MemoryEntry
      - Claims with status='refuted' → stored as contradiction memory
      - memory_id FK populated when promotion occurs (Phase 2 adds that table)

    Performance note: workspace_id is denormalized onto this table to avoid
    joining through thesis_versions for the common "all claims for workspace" query.
    """
    __tablename__ = "thesis_claims"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    thesis_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("thesis_versions.id", ondelete="CASCADE"), nullable=False
    )

    # Claim content
    claim_type: Mapped[str] = mapped_column(
        String(40), nullable=False
    )  # "bull_point" | "bear_point" | "risk" | "assumption" | "invalidation_condition" | "known_unknown"
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_agent: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    claim_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)

    # Longitudinal tracking
    first_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_confirmed_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    appearance_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Status lifecycle
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )  # "active" | "strengthened" | "weakened" | "refuted" | "confirmed"

    # Phase 2 hook — null until AI Memory phase
    memory_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "workspace_id": str(self.workspace_id),
            "thesis_version_id": str(self.thesis_version_id),
            "claim_type": self.claim_type,
            "claim_text": self.claim_text,
            "source_agent": self.source_agent,
            "claim_confidence": self.claim_confidence,
            "first_version": self.first_version,
            "last_confirmed_version": self.last_confirmed_version,
            "appearance_count": self.appearance_count,
            "status": self.status,
            "memory_id": str(self.memory_id) if self.memory_id else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
