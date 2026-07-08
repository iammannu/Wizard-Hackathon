"""
Monitoring router — Milestone 4 read-only + manual-trigger surface.

Full Monitoring/Alert API completion (pagination polish, bulk actions) is
Milestone 9's job; this milestone needs enough surface to inspect jobs/
alerts and to manually force a poll tick for verification — same
read-only-first approach Milestones 2/3 took.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.core.database import get_db
from app.models.monitoring import MonitoringJob, Alert
from app.monitoring import alert_service, registry
from app.monitoring.scheduler import run_due_jobs

router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])


@router.get("/alerts")
async def list_alerts(
    ticker: Optional[str] = None,
    monitor_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
):
    async for db in get_db():
        alerts = await alert_service.list_alerts(db, ticker=ticker, monitor_type=monitor_type, status=status, limit=limit)
        return [a.to_dict() for a in alerts]


@router.get("/alerts/{ticker}")
async def list_alerts_for_ticker(ticker: str, limit: int = Query(50, ge=1, le=500)):
    async for db in get_db():
        alerts = await alert_service.list_alerts(db, ticker=ticker, limit=limit)
        return [a.to_dict() for a in alerts]


@router.post("/alerts/{alert_id}/read")
async def mark_alert_read(alert_id: str):
    async for db in get_db():
        alert = await alert_service.mark_alert(db, uuid.UUID(alert_id), "read")
        if alert is None:
            raise HTTPException(404, "Alert not found")
        await db.commit()
        return alert.to_dict()


@router.post("/alerts/{alert_id}/dismiss")
async def dismiss_alert(alert_id: str):
    async for db in get_db():
        alert = await alert_service.mark_alert(db, uuid.UUID(alert_id), "dismissed")
        if alert is None:
            raise HTTPException(404, "Alert not found")
        await db.commit()
        return alert.to_dict()


@router.get("/jobs")
async def list_jobs(ticker: Optional[str] = None, monitor_type: Optional[str] = None):
    async for db in get_db():
        query = select(MonitoringJob)
        if ticker:
            query = query.where(MonitoringJob.ticker == ticker.upper())
        if monitor_type:
            query = query.where(MonitoringJob.monitor_type == monitor_type)
        result = await db.execute(query.order_by(MonitoringJob.ticker))
        return [j.to_dict() for j in result.scalars().all()]


@router.post("/jobs/sync")
async def sync_jobs():
    """Upserts MonitoringJob rows for every currently-tracked ticker."""
    async for db in get_db():
        tickers = await registry.get_tracked_tickers(db)
        created = await registry.sync_jobs_for_tickers(db, tickers)
        await db.commit()
        return {"tickers_tracked": len(tickers), "jobs_created": created}


@router.post("/jobs/run-now")
async def run_now():
    """Forces one full scheduler tick immediately — every due job runs.
    Manual/verification tool; the background scheduler already does this on
    its own interval."""
    async for db in get_db():
        summary = await run_due_jobs(db)
        return summary


@router.post("/jobs/{job_id}/run-now")
async def run_job_now(job_id: str):
    """Forces one specific job to run immediately, ignoring next_run_at —
    useful for testing a single monitor without waiting for its poll
    interval or for every other due job to also run."""
    async for db in get_db():
        result = await db.execute(select(MonitoringJob).where(MonitoringJob.id == uuid.UUID(job_id)))
        job = result.scalar_one_or_none()
        if job is None:
            raise HTTPException(404, "Monitoring job not found")

        job.next_run_at = datetime.now(timezone.utc)
        await db.commit()
        summary = await run_due_jobs(db)
        return summary
