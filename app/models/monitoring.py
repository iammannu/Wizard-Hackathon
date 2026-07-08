"""
Monitoring & Alerts persistence models — Milestone 4.

  MonitoringJob   one row per (ticker, monitor_type) — the scheduler's work
                  queue. Tracks when it last ran, what state it saw last time
                  (so the next run can diff against it), and whether it's
                  currently healthy.
  Alert           one row per detected, deduplicated, meaningful change. The
                  durable record a user (or, from Milestone 5 on, a Holding)
                  reads to answer "what happened while I wasn't looking."

Design decisions (matching app/models/thesis.py's / app/models/memory.py's
established conventions):
  - JSON stored as Text with accessor methods + to_dict().
  - No SQLAlchemy relationship() — joins done explicitly in queries.
  - Alerts are ticker-scoped, not workspace-scoped — same reasoning as
    CompanyMemory (Milestone 3): a filing/price move/rating change is a fact
    about the company, not about any one workspace that happens to track it.
  - dedup_key + (ticker, monitor_type) uniqueness is enforced at the
    application layer (AlertService), not a DB unique constraint — the key
    format varies by monitor_type (accession number, article hash, rating
    transition string, ...) and isn't worth a rigid schema-level constraint
    while only six monitor types exist.

Future integration points:
  - Milestone 5 (Portfolio Intelligence): Holding rows read Alert by ticker
    directly — no new column needed since Alert is already ticker-scoped.
  - Milestone 6 (Prediction Tracking): a MonitoringJob-detected event is a
    natural trigger for re-evaluating an open PredictionRecord.
"""
import uuid
import json
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, DateTime, Text, Float, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

MONITOR_TYPES = (
    "sec_filing", "earnings", "news", "insider_trading", "price_movement", "analyst_rating",
)

ALERT_SEVERITIES = ("info", "warning", "critical")


class MonitoringJob(Base):
    """One (ticker, monitor_type) polling slot. Uniqueness enforced at the
    application layer by app/monitoring/registry.py::sync_jobs_for_tickers,
    which upserts rather than duplicating."""
    __tablename__ = "monitoring_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    monitor_type: Mapped[str] = mapped_column(String(30), nullable=False)  # one of MONITOR_TYPES

    poll_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=1800)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")  # "active" | "paused" | "error"

    # Opaque, monitor-type-specific snapshot of what was last seen — e.g.
    # {"last_accession": "..."} for sec_filing, {"last_price": 190.2} for
    # price_movement. Each provider in app/monitoring/providers/ owns its own
    # shape; the scheduler just passes it through.
    last_state: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    consecutive_errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def last_state_dict(self) -> dict:
        try:
            return json.loads(self.last_state or "{}")
        except Exception:
            return {}

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "ticker": self.ticker,
            "monitor_type": self.monitor_type,
            "poll_interval_seconds": self.poll_interval_seconds,
            "status": self.status,
            "last_state": self.last_state_dict(),
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "next_run_at": self.next_run_at.isoformat(),
            "consecutive_errors": self.consecutive_errors,
            "last_error": self.last_error,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class Alert(Base):
    """One detected, deduplicated, meaningful change for a ticker."""
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    monitor_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # one of MONITOR_TYPES
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "new_filing", "price_spike", "rating_upgrade"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="info")  # one of ALERT_SEVERITIES

    data: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # structured event payload (JSON)
    dedup_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unread")  # "unread" | "read" | "dismissed"
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )

    def data_dict(self) -> dict:
        try:
            return json.loads(self.data or "{}")
        except Exception:
            return {}

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "ticker": self.ticker,
            "monitor_type": self.monitor_type,
            "event_type": self.event_type,
            "title": self.title,
            "description": self.description,
            "severity": self.severity,
            "data": self.data_dict(),
            "dedup_key": self.dedup_key,
            "status": self.status,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat(),
        }
