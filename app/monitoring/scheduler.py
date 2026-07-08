"""
Monitoring scheduler — one in-process background loop, same
asyncio.create_task pattern as app.documents.embeddings.queue.worker_loop
(started/cancelled from app/main.py's startup/shutdown events). No
Celery/cron/Redis broker — a single tick loop checking "which jobs are due"
is enough at this scale and matches the project's "no infra until you need
it" convention.

Each tick:
  1. Sync MonitoringJob rows from currently-tracked tickers (cheap upsert).
  2. Run every due job (next_run_at <= now, status="active") through its
     Monitor.check(), turn resulting MonitorEvents into deduplicated Alerts,
     and reschedule the job.
  3. A new_filing event additionally triggers real ingestion (best-effort —
     failure here doesn't fail the alert, which has already been recorded).

Failure isolation: one job's exception increments its own
consecutive_errors/last_error and reschedules with backoff — it never
aborts the tick for other jobs, same resilience contract as
ingest_ticker()'s per-document try/except.
"""
import asyncio
import logging
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import get_settings
from app.models.monitoring import MonitoringJob
from app.monitoring import registry, alert_service

logger = logging.getLogger(__name__)
settings = get_settings()

_MAX_CONSECUTIVE_ERRORS_BEFORE_LONG_BACKOFF = 3
_ERROR_BACKOFF_MULTIPLIER = 4


async def run_due_jobs(db) -> dict:
    """One scheduler tick. Returns a summary dict (jobs_run, alerts_created,
    errors) — used by tests and the manual /monitoring/jobs/run-now endpoint,
    not just the background loop."""
    tickers = await registry.get_tracked_tickers(db)
    jobs_created = await registry.sync_jobs_for_tickers(db, tickers)
    if jobs_created:
        await db.commit()

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(MonitoringJob).where(MonitoringJob.status == "active", MonitoringJob.next_run_at <= now)
    )
    due_jobs = result.scalars().all()

    jobs_run, alerts_created, errors = 0, 0, 0

    for job in due_jobs:
        monitor = registry.MONITOR_REGISTRY.get(job.monitor_type)
        if monitor is None:
            continue

        try:
            events, new_state = await monitor.check(job.ticker, job.last_state_dict())

            for event in events:
                alert = await alert_service.create_alert_if_new(db, job.ticker, job.monitor_type, event)
                if alert is not None:
                    alerts_created += 1
                    if event.event_type == "new_filing":
                        await _trigger_filing_ingestion(db, job.ticker, event)

            job.last_state = json.dumps(new_state, default=str)
            job.last_run_at = now
            job.next_run_at = now + timedelta(seconds=job.poll_interval_seconds)
            job.consecutive_errors = 0
            job.last_error = None
            job.updated_at = now
            jobs_run += 1
            await db.commit()

        except Exception as e:
            await db.rollback()
            errors += 1
            logger.exception("Monitor check failed for %s/%s", job.ticker, job.monitor_type)
            job.consecutive_errors += 1
            job.last_error = str(e)[:500]
            backoff = job.poll_interval_seconds
            if job.consecutive_errors >= _MAX_CONSECUTIVE_ERRORS_BEFORE_LONG_BACKOFF:
                backoff *= _ERROR_BACKOFF_MULTIPLIER
            job.next_run_at = now + timedelta(seconds=backoff)
            job.updated_at = now
            await db.commit()

    return {"jobs_run": jobs_run, "alerts_created": alerts_created, "errors": errors, "tickers_tracked": len(tickers)}


async def _trigger_filing_ingestion(db, ticker: str, event) -> None:
    """Best-effort bridge into Document Intelligence: a newly-detected
    filing is worth ingesting right away rather than waiting for someone to
    run the manual ingest endpoint. Failure here never rolls back the
    alert — it's already committed by the time this runs."""
    from app.documents.providers.sec_edgar import SECProvider
    from app.documents.services.ingestion_service import ingest_ticker

    doc_type = event.data.get("doc_type")
    if not doc_type:
        return
    try:
        await ingest_ticker(db, SECProvider(), ticker, [doc_type])
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("Auto-ingestion of new %s filing failed for %s", doc_type, ticker)


async def scheduler_loop() -> None:
    """Runs until cancelled — one tick every Settings.monitoring_tick_interval_seconds."""
    from app.core.database import SessionLocal

    logger.info("Monitoring scheduler started")
    while True:
        try:
            async with SessionLocal() as db:
                summary = await run_due_jobs(db)
                if summary["jobs_run"] or summary["errors"]:
                    logger.info(
                        "Monitoring tick: %d jobs run, %d alerts created, %d errors",
                        summary["jobs_run"], summary["alerts_created"], summary["errors"],
                    )
        except asyncio.CancelledError:
            logger.info("Monitoring scheduler stopped")
            raise
        except Exception:
            logger.exception("Monitoring scheduler tick error — continuing")

        await asyncio.sleep(settings.monitoring_tick_interval_seconds)
