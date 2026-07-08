"""
Portfolio Intelligence persistence models — Milestone 5.

  Portfolio          a named collection of holdings. Denormalized aggregate
                      fields (mirrors Workspace's denormalized thesis
                      columns) so the list view never joins holdings.
  PortfolioHolding    one open or closed position in a ticker. Quantity/
                      average_cost/realized_gain are derived from the
                      PortfolioActivity ledger (app/portfolio/service.py owns
                      that math) — not free-form editable fields, so gain
                      accounting can't drift from the transaction history.
  HoldingSnapshot     append-only daily time series per holding (mirrors
                      ConfidenceSnapshot's pure-time-series pattern) — feeds
                      performance charts and the daily summary's
                      confidence/evidence-change deltas.
  Watchlist           a named list of tickers with no position attached —
                      same JSON-array-as-Text convention as
                      Workspace.tracked_tickers, not a normalized join table.
  PortfolioActivity   append-only transaction ledger — buy/sell/import/
                      adjustment. The source of truth PortfolioHolding's
                      derived fields are computed from.

No user_id/ownership column on Portfolio, same as Workspace today — this
codebase doesn't yet scope any table by user (see app/routers/auth.py's
get_current_user, used only by /auth/me). Not introduced here to stay
consistent with the existing single-tenant-dev-mode convention rather than
add inconsistent partial multi-tenancy.
"""
import uuid
import json
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, Text, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    base_currency: Mapped[str] = mapped_column(String(10), default="USD")
    status: Mapped[str] = mapped_column(String(20), default="active")  # "active" | "archived"

    # Denormalized aggregates — refreshed by app/portfolio/service.py::recalculate_portfolio_aggregates
    total_cost_basis: Mapped[float] = mapped_column(Float, default=0.0)
    total_market_value: Mapped[float] = mapped_column(Float, default=0.0)
    total_unrealized_gain: Mapped[float] = mapped_column(Float, default=0.0)
    total_realized_gain: Mapped[float] = mapped_column(Float, default=0.0)
    holding_count: Mapped[int] = mapped_column(Integer, default=0)
    concentration_hhi: Mapped[float] = mapped_column(Float, default=0.0)  # 0-10000, traditional HHI scale
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "base_currency": self.base_currency,
            "status": self.status,
            "total_cost_basis": self.total_cost_basis,
            "total_market_value": self.total_market_value,
            "total_unrealized_gain": self.total_unrealized_gain,
            "total_unrealized_gain_pct": round(
                (self.total_unrealized_gain / self.total_cost_basis * 100), 2
            ) if self.total_cost_basis else 0.0,
            "total_realized_gain": self.total_realized_gain,
            "holding_count": self.holding_count,
            "concentration_hhi": self.concentration_hhi,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class PortfolioHolding(Base):
    __tablename__ = "portfolio_holdings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    average_cost: Mapped[float] = mapped_column(Float, default=0.0)
    realized_gain: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="open")  # "open" | "closed"

    # Market-data cache, refreshed by app/portfolio/service.py::refresh_holding_market_data
    latest_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    market_value: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_gain: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_gain_pct: Mapped[float] = mapped_column(Float, default=0.0)
    day_change_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Intelligence-layer cache, refreshed by app/portfolio/intelligence.py::build_holding_intelligence
    health_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sentiment_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    intelligence_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "portfolio_id": str(self.portfolio_id),
            "ticker": self.ticker,
            "quantity": self.quantity,
            "average_cost": self.average_cost,
            "realized_gain": self.realized_gain,
            "status": self.status,
            "latest_price": self.latest_price,
            "market_value": self.market_value,
            "unrealized_gain": self.unrealized_gain,
            "unrealized_gain_pct": self.unrealized_gain_pct,
            "day_change_pct": self.day_change_pct,
            "health_score": self.health_score,
            "risk_score": self.risk_score,
            "sentiment_score": self.sentiment_score,
            "ai_summary": self.ai_summary,
            "intelligence_updated_at": self.intelligence_updated_at.isoformat() if self.intelligence_updated_at else None,
            "opened_at": self.opened_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "updated_at": self.updated_at.isoformat(),
        }


class HoldingSnapshot(Base):
    """Append-only daily time series per holding — never updated after
    insert. portfolio_id is denormalized to avoid joining through
    PortfolioHolding for portfolio-wide range queries, same reasoning as
    ThesisClaim.workspace_id in app/models/thesis.py."""
    __tablename__ = "holding_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    holding_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolio_holdings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)

    price: Mapped[float] = mapped_column(Float, default=0.0)
    market_value: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_gain: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_gain_pct: Mapped[float] = mapped_column(Float, default=0.0)
    health_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True, default=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "holding_id": str(self.holding_id),
            "portfolio_id": str(self.portfolio_id),
            "ticker": self.ticker,
            "price": self.price,
            "market_value": self.market_value,
            "unrealized_gain": self.unrealized_gain,
            "unrealized_gain_pct": self.unrealized_gain_pct,
            "health_score": self.health_score,
            "confidence": self.confidence,
            "snapshot_at": self.snapshot_at.isoformat(),
        }


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    tickers: Mapped[str] = mapped_column(Text, default="[]")  # JSON array, same convention as Workspace.tracked_tickers

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def tickers_list(self) -> list[str]:
        try:
            return json.loads(self.tickers or "[]")
        except Exception:
            return []

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "tickers": self.tickers_list(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class PortfolioActivity(Base):
    """Append-only transaction ledger — the source of truth
    app/portfolio/service.py derives PortfolioHolding.quantity/average_cost/
    realized_gain from. Never mutated after insert."""
    __tablename__ = "portfolio_activity"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    holding_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("portfolio_holdings.id", ondelete="SET NULL"), nullable=True
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)

    activity_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # "buy" | "sell" | "import" | "holding_removed" | "note"
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    realized_gain: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # set for "sell" activities

    description: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[str] = mapped_column(Text, default="{}")

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
            "portfolio_id": str(self.portfolio_id),
            "holding_id": str(self.holding_id) if self.holding_id else None,
            "ticker": self.ticker,
            "activity_type": self.activity_type,
            "quantity": self.quantity,
            "price": self.price,
            "realized_gain": self.realized_gain,
            "description": self.description,
            "data": self.data_dict(),
            "created_at": self.created_at.isoformat(),
        }
