import uuid
import json
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, Text, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Workspace(Base):
    __tablename__ = "workspaces"

    # ── Existing columns (never modified) ─────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    tracked_tickers: Mapped[str] = mapped_column(Text, default="[]")   # JSON array
    tracked_sectors: Mapped[str] = mapped_column(Text, default="[]")
    tracked_themes: Mapped[str] = mapped_column(Text, default="[]")
    thesis: Mapped[str] = mapped_column(Text, default="")              # latest synthesis text
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="active")
    icon: Mapped[str] = mapped_column(String(10), default="📊")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # ── Phase 1: Living Thesis columns (all nullable — additive migration) ───
    # FK to the most recent ThesisVersion for this workspace
    current_thesis_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("thesis_versions.id", ondelete="SET NULL", use_alter=True, name="fk_workspace_current_thesis_version"),
        nullable=True, default=None
    )
    # Total thesis versions created — enables cheap "has this been researched?" checks
    thesis_version_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Lifecycle stage of the current thesis
    thesis_lifecycle_stage: Mapped[str] = mapped_column(
        String(30), nullable=False, default="forming"
    )
    # Multi-factor conviction score (separate from raw pipeline confidence)
    conviction_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Denormalized signal from the current thesis — avoids a join on workspace list renders
    thesis_signal: Mapped[str] = mapped_column(String(20), nullable=False, default="neutral")

    def tickers_list(self) -> list[str]:
        try:
            return json.loads(self.tracked_tickers or "[]")
        except Exception:
            return []

    def themes_list(self) -> list[str]:
        try:
            return json.loads(self.tracked_themes or "[]")
        except Exception:
            return []

    def to_dict(self) -> dict:
        return {
            # Existing fields — never removed or renamed
            "id": str(self.id),
            "title": self.title,
            "description": self.description,
            "tracked_tickers": self.tickers_list(),
            "tracked_sectors": json.loads(self.tracked_sectors or "[]"),
            "tracked_themes": self.themes_list(),
            "thesis": self.thesis,
            "confidence": self.confidence,
            "status": self.status,
            "icon": self.icon,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            # Phase 1: Living Thesis fields
            "current_thesis_version_id": str(self.current_thesis_version_id) if self.current_thesis_version_id else None,
            "thesis_version_count": self.thesis_version_count,
            "thesis_lifecycle_stage": self.thesis_lifecycle_stage,
            "conviction_score": self.conviction_score,
            "thesis_signal": self.thesis_signal,
        }


class WorkspaceResearch(Base):
    __tablename__ = "workspace_research"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str] = mapped_column(String(50), default="general")
    tickers: Mapped[str] = mapped_column(Text, default="[]")   # JSON
    result: Mapped[str] = mapped_column(Text, default="{}")    # Full analysis JSON
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def result_dict(self) -> dict:
        try:
            return json.loads(self.result or "{}")
        except Exception:
            return {}

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "workspace_id": str(self.workspace_id),
            "query": self.query,
            "intent": self.intent,
            "tickers": json.loads(self.tickers or "[]"),
            "confidence": self.confidence,
            "result": self.result_dict(),
            "created_at": self.created_at.isoformat(),
        }
