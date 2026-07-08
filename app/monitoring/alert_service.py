"""
AlertService — deduplication + persistence for MonitorEvent -> Alert, and
the read-side query surface app/routers/monitoring.py uses.

Dedup strategy: an Alert is only created if no existing Alert with the same
(ticker, monitor_type, dedup_key) exists. Deliberately not a DB unique
constraint (see app/models/monitoring.py's module docstring) — checked here
so the scheduler can call this once per event without worrying about
race-free upserts across a single-process, single-scheduler-loop system.
"""
import json
from typing import Optional

from sqlalchemy import select, update

from app.models.monitoring import Alert
from app.monitoring.providers.base import MonitorEvent


async def create_alert_if_new(db, ticker: str, monitor_type: str, event: MonitorEvent) -> Optional[Alert]:
    existing = await db.execute(
        select(Alert).where(
            Alert.ticker == ticker,
            Alert.monitor_type == monitor_type,
            Alert.dedup_key == event.dedup_key,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return None

    alert = Alert(
        ticker=ticker,
        monitor_type=monitor_type,
        event_type=event.event_type,
        title=event.title,
        description=event.description,
        severity=event.severity,
        data=json.dumps(event.data, default=str),
        dedup_key=event.dedup_key,
        status="unread",
        is_read=False,
    )
    db.add(alert)
    await db.flush()
    return alert


async def list_alerts(
    db, ticker: Optional[str] = None, monitor_type: Optional[str] = None,
    status: Optional[str] = None, limit: int = 100,
) -> list[Alert]:
    query = select(Alert)
    if ticker:
        query = query.where(Alert.ticker == ticker.upper())
    if monitor_type:
        query = query.where(Alert.monitor_type == monitor_type)
    if status:
        query = query.where(Alert.status == status)
    query = query.order_by(Alert.created_at.desc()).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


async def mark_alert(db, alert_id, status: str) -> Optional[Alert]:
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if alert is None:
        return None
    alert.status = status
    alert.is_read = status in ("read", "dismissed")
    await db.flush()
    return alert
