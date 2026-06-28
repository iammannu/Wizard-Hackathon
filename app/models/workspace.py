import uuid
import json
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    tracked_tickers: Mapped[str] = mapped_column(Text, default="[]")   # JSON array
    tracked_sectors: Mapped[str] = mapped_column(Text, default="[]")
    tracked_themes: Mapped[str] = mapped_column(Text, default="[]")
    thesis: Mapped[str] = mapped_column(Text, default="")              # latest synthesis
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="active")
    icon: Mapped[str] = mapped_column(String(10), default="📊")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

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
