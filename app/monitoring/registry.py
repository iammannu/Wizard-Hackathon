"""
Monitor registry — maps monitor_type -> Monitor instance, and syncs
MonitoringJob rows from whatever tickers the app currently cares about.

Where tickers come from (pre-Milestone-5): every distinct ticker in an
active Workspace.tracked_tickers. Milestone 5 (Portfolio Intelligence) adds
Holding/Watchlist — sync_jobs_for_tickers() takes a plain ticker list
precisely so that milestone can call it with Holdings' tickers too, without
any change here.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from app.core.config import get_settings
from app.models.workspace import Workspace
from app.models.monitoring import MonitoringJob, MONITOR_TYPES
from app.monitoring.providers.base import Monitor
from app.monitoring.providers.sec_filing import SECFilingMonitor
from app.monitoring.providers.earnings import EarningsMonitor
from app.monitoring.providers.news import NewsMonitor
from app.monitoring.providers.insider_trading import InsiderTradingMonitor
from app.monitoring.providers.price_movement import PriceMovementMonitor
from app.monitoring.providers.analyst_rating import AnalystRatingMonitor

settings = get_settings()

MONITOR_REGISTRY: dict[str, Monitor] = {
    "sec_filing": SECFilingMonitor(),
    "earnings": EarningsMonitor(),
    "news": NewsMonitor(),
    "insider_trading": InsiderTradingMonitor(),
    "price_movement": PriceMovementMonitor(),
    "analyst_rating": AnalystRatingMonitor(),
}

_DEFAULT_INTERVAL_BY_TYPE = {
    "sec_filing": lambda: settings.monitoring_poll_interval_sec_filing,
    "earnings": lambda: settings.monitoring_poll_interval_earnings,
    "news": lambda: settings.monitoring_poll_interval_news,
    "insider_trading": lambda: settings.monitoring_poll_interval_insider_trading,
    "price_movement": lambda: settings.monitoring_poll_interval_price_movement,
    "analyst_rating": lambda: settings.monitoring_poll_interval_analyst_rating,
}


async def get_tracked_tickers(db) -> list[str]:
    """Every distinct ticker tracked by an active workspace."""
    result = await db.execute(select(Workspace.tracked_tickers).where(Workspace.status == "active"))
    tickers: set[str] = set()
    import json
    for (raw,) in result.all():
        try:
            for t in json.loads(raw or "[]"):
                tickers.add(t.upper())
        except Exception:
            continue
    return sorted(tickers)


async def sync_jobs_for_tickers(db, tickers: list[str]) -> int:
    """Upserts one MonitoringJob per (ticker, monitor_type). Returns the
    number of newly created jobs. Existing jobs are left untouched (their
    last_state/next_run_at must survive a resync)."""
    if not tickers:
        return 0

    result = await db.execute(select(MonitoringJob.ticker, MonitoringJob.monitor_type))
    existing = {(t, m) for t, m in result.all()}

    created = 0
    now = datetime.now(timezone.utc)
    for ticker in tickers:
        for monitor_type in MONITOR_TYPES:
            if (ticker, monitor_type) in existing:
                continue
            db.add(MonitoringJob(
                ticker=ticker,
                monitor_type=monitor_type,
                poll_interval_seconds=_DEFAULT_INTERVAL_BY_TYPE[monitor_type](),
                status="active",
                last_state="{}",
                next_run_at=now,
            ))
            created += 1

    if created:
        await db.flush()
    return created
