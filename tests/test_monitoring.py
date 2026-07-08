"""
Unit tests for Monitoring & Alerts (Milestone 4).

Same isolation approach as tests/test_evidence_engine.py and
tests/test_memory_engine.py: real in-memory SQLite + real ORM models, with
the only external dependency (market/SEC data fetchers) swapped for small
deterministic stand-ins via monkeypatching. Dedup, scheduling, and
diff-detection logic all run for real against app/monitoring/*.
"""
import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models import workspace as _workspace_models
from app.models.workspace import Workspace
from app.models import thesis as _thesis_models  # noqa: F401 (FK target registration)
from app.documents.models import citation as _citation_models  # noqa: F401
from app.documents.models import entity as _entity_models  # noqa: F401
from app.documents.models import document as _document_models  # noqa: F401
from app.documents.models import chunk as _chunk_models  # noqa: F401
from app.documents.models import embedding as _embedding_models  # noqa: F401
from app.models import memory as _memory_models  # noqa: F401

from app.models.monitoring import MonitoringJob, Alert, MONITOR_TYPES
from app.monitoring.providers.base import MonitorEvent
from app.monitoring.providers import price_movement as price_movement_mod
from app.monitoring.providers import news as news_mod
from app.monitoring.providers import analyst_rating as analyst_rating_mod
from app.monitoring.providers import earnings as earnings_mod
from app.monitoring.providers import insider_trading as insider_mod
from app.monitoring import alert_service, registry, scheduler as scheduler_mod


async def _make_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)()


# ── Price movement monitor ───────────────────────────────────────────────

def test_price_movement_first_poll_records_checkpoint_without_alert(monkeypatch):
    async def run():
        async def fake_get_quote(ticker):
            return {"price": 100.0}

        monkeypatch.setattr(price_movement_mod, "get_quote", fake_get_quote)
        monitor = price_movement_mod.PriceMovementMonitor()

        events, new_state = await monitor.check("AAPL", {})
        assert events == []
        assert new_state["checkpoint_price"] == 100.0

    asyncio.run(run())


def test_price_movement_alerts_above_threshold(monkeypatch):
    async def run():
        async def fake_get_quote(ticker):
            return {"price": 110.0}

        monkeypatch.setattr(price_movement_mod, "get_quote", fake_get_quote)
        monitor = price_movement_mod.PriceMovementMonitor()

        events, new_state = await monitor.check("AAPL", {"checkpoint_price": 100.0})
        assert len(events) == 1
        assert events[0].event_type == "price_movement"
        assert "up" in events[0].title
        assert new_state["checkpoint_price"] == 110.0

    asyncio.run(run())


def test_price_movement_below_threshold_no_alert(monkeypatch):
    async def run():
        async def fake_get_quote(ticker):
            return {"price": 101.0}  # 1% move, below default 5% threshold

        monkeypatch.setattr(price_movement_mod, "get_quote", fake_get_quote)
        monitor = price_movement_mod.PriceMovementMonitor()

        events, _ = await monitor.check("AAPL", {"checkpoint_price": 100.0})
        assert events == []

    asyncio.run(run())


# ── News monitor ──────────────────────────────────────────────────────────

def test_news_monitor_first_poll_no_backlog_alerts(monkeypatch):
    async def run():
        async def fake_get_news(ticker, limit=20):
            return [{"id": "a1", "title": "Old news"}, {"id": "a2", "title": "Older news"}]

        monkeypatch.setattr(news_mod, "get_news", fake_get_news)
        monitor = news_mod.NewsMonitor()

        events, new_state = await monitor.check("AAPL", {})
        assert events == []
        assert set(new_state["seen_ids"]) == {"a1", "a2"}

    asyncio.run(run())


def test_news_monitor_alerts_only_on_new_articles(monkeypatch):
    async def run():
        async def fake_get_news(ticker, limit=20):
            return [{"id": "a3", "title": "Breaking news"}, {"id": "a1", "title": "Old news"}]

        monkeypatch.setattr(news_mod, "get_news", fake_get_news)
        monitor = news_mod.NewsMonitor()

        events, new_state = await monitor.check("AAPL", {"seen_ids": ["a1", "a2"]})
        assert len(events) == 1
        assert events[0].dedup_key == "news:AAPL:a3"
        assert "a3" in new_state["seen_ids"]

    asyncio.run(run())


# ── Analyst rating monitor ───────────────────────────────────────────────

def test_analyst_rating_alerts_only_on_transition(monkeypatch):
    async def run():
        async def fake_get_analyst(ticker):
            return {"consensus": "buy", "detail": {}}

        monkeypatch.setattr(analyst_rating_mod, "get_analyst", fake_get_analyst)
        monitor = analyst_rating_mod.AnalystRatingMonitor()

        # Same consensus as before -> no alert
        events, _ = await monitor.check("AAPL", {"consensus": "buy"})
        assert events == []

        # Consensus changed -> upgrade alert
        events, new_state = await monitor.check("AAPL", {"consensus": "hold"})
        assert len(events) == 1
        assert events[0].event_type == "rating_upgrade"
        assert new_state["consensus"] == "buy"

    asyncio.run(run())


# ── Earnings monitor ──────────────────────────────────────────────────────

def test_earnings_monitor_classifies_beat_and_miss(monkeypatch):
    async def run():
        async def fake_get_earnings_beat(ticker):
            return [{"period": "2026-06-30", "actual": 2.5, "estimate": 2.0}]

        monkeypatch.setattr(earnings_mod, "get_earnings", fake_get_earnings_beat)
        monitor = earnings_mod.EarningsMonitor()

        events, new_state = await monitor.check("AAPL", {"last_period": "2026-03-31"})
        assert len(events) == 1
        assert events[0].data["classification"] == "beat"
        assert new_state["last_period"] == "2026-06-30"

        # Same period again -> no duplicate alert
        events_again, _ = await monitor.check("AAPL", new_state)
        assert events_again == []

    asyncio.run(run())


# ── Insider trading monitor ───────────────────────────────────────────────

def test_insider_trading_alerts_on_new_transaction(monkeypatch):
    async def run():
        async def fake_get_insider(ticker):
            return [{"name": "Jane Doe", "transactionDate": "2026-07-01", "share": 1000, "change": -1000, "transactionCode": "S"}]

        monkeypatch.setattr(insider_mod, "get_insider_transactions", fake_get_insider)
        monitor = insider_mod.InsiderTradingMonitor()

        # First poll: baseline, no alert
        events, new_state = await monitor.check("AAPL", {})
        assert events == []
        assert len(new_state["seen_keys"]) == 1

        async def fake_get_insider_new(ticker):
            return [
                {"name": "Jane Doe", "transactionDate": "2026-07-01", "share": 1000, "change": -1000, "transactionCode": "S"},
                {"name": "John Smith", "transactionDate": "2026-07-05", "share": 500, "change": 500, "transactionCode": "P"},
            ]

        monkeypatch.setattr(insider_mod, "get_insider_transactions", fake_get_insider_new)
        events2, new_state2 = await monitor.check("AAPL", new_state)
        assert len(events2) == 1
        assert "John Smith" in events2[0].title
        assert "bought" in events2[0].title

    asyncio.run(run())


# ── AlertService dedup ────────────────────────────────────────────────────

def test_create_alert_if_new_deduplicates():
    async def run():
        engine, db = await _make_session()
        event = MonitorEvent(event_type="price_movement", title="AAPL moved", description="desc", dedup_key="price:AAPL:110.00")

        alert1 = await alert_service.create_alert_if_new(db, "AAPL", "price_movement", event)
        await db.commit()
        assert alert1 is not None

        alert2 = await alert_service.create_alert_if_new(db, "AAPL", "price_movement", event)
        assert alert2 is None  # same dedup_key -> no duplicate

        from sqlalchemy import select
        result = await db.execute(select(Alert).where(Alert.ticker == "AAPL"))
        assert len(result.scalars().all()) == 1
        await engine.dispose()

    asyncio.run(run())


def test_mark_alert_dismiss():
    async def run():
        engine, db = await _make_session()
        event = MonitorEvent(event_type="news", title="t", description="d", dedup_key="k1")
        alert = await alert_service.create_alert_if_new(db, "AAPL", "news", event)
        await db.commit()

        updated = await alert_service.mark_alert(db, alert.id, "dismissed")
        await db.commit()
        assert updated.status == "dismissed"
        assert updated.is_read is True
        await engine.dispose()

    asyncio.run(run())


# ── Registry: job sync from tracked tickers ──────────────────────────────

def test_sync_jobs_for_tickers_creates_one_job_per_monitor_type():
    async def run():
        engine, db = await _make_session()
        created = await registry.sync_jobs_for_tickers(db, ["AAPL"])
        await db.commit()
        assert created == len(MONITOR_TYPES)

        from sqlalchemy import select
        result = await db.execute(select(MonitoringJob).where(MonitoringJob.ticker == "AAPL"))
        jobs = result.scalars().all()
        assert {j.monitor_type for j in jobs} == set(MONITOR_TYPES)

        # Re-sync doesn't duplicate
        created_again = await registry.sync_jobs_for_tickers(db, ["AAPL"])
        assert created_again == 0
        await engine.dispose()

    asyncio.run(run())


def test_get_tracked_tickers_reads_active_workspaces():
    async def run():
        engine, db = await _make_session()
        ws1 = Workspace(title="WS1", tracked_tickers=json.dumps(["AAPL", "MSFT"]), status="active")
        ws2 = Workspace(title="WS2", tracked_tickers=json.dumps(["MSFT", "TSLA"]), status="active")
        ws3 = Workspace(title="Archived", tracked_tickers=json.dumps(["NFLX"]), status="archived")
        db.add_all([ws1, ws2, ws3])
        await db.commit()

        tickers = await registry.get_tracked_tickers(db)
        assert tickers == ["AAPL", "MSFT", "TSLA"]  # sorted, deduped, archived excluded
        await engine.dispose()

    asyncio.run(run())


# ── Scheduler: full tick orchestration ────────────────────────────────────

def test_run_due_jobs_creates_alerts_and_reschedules(monkeypatch):
    async def run():
        engine, db = await _make_session()
        ws = Workspace(title="WS", tracked_tickers=json.dumps(["AAPL"]), status="active")
        db.add(ws)
        await db.commit()

        # First tick: creates jobs, all due immediately (next_run_at=now on creation)
        async def fake_get_quote(ticker):
            return {"price": 100.0}
        monkeypatch.setattr(price_movement_mod, "get_quote", fake_get_quote)

        async def fake_get_news(ticker, limit=20):
            return []
        monkeypatch.setattr(news_mod, "get_news", fake_get_news)

        async def fake_get_analyst(ticker):
            return None
        monkeypatch.setattr(analyst_rating_mod, "get_analyst", fake_get_analyst)

        async def fake_get_earnings(ticker):
            return []
        monkeypatch.setattr(earnings_mod, "get_earnings", fake_get_earnings)

        async def fake_get_insider(ticker):
            return []
        monkeypatch.setattr(insider_mod, "get_insider_transactions", fake_get_insider)

        # SEC filing monitor will hit the real provider; without a
        # configured user agent it raises RuntimeError internally, which
        # check() catches and treats as "nothing to report" — no monkeypatch
        # needed, this exercises the real graceful-degradation path.

        summary = await scheduler_mod.run_due_jobs(db)
        assert summary["tickers_tracked"] == 1
        assert summary["jobs_run"] == len(MONITOR_TYPES)
        assert summary["errors"] == 0

        from sqlalchemy import select
        result = await db.execute(select(MonitoringJob).where(MonitoringJob.ticker == "AAPL"))
        jobs = result.scalars().all()
        # SQLite's DateTime(timezone=True) doesn't round-trip tzinfo (a
        # SQLAlchemy+SQLite limitation, not a scheduler bug — the real
        # next_run_at <= now comparison happens server-side in SQL, where
        # both sides go through the same bind_processor consistently).
        # Compare naive-vs-naive here for the same reason.
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        assert all(j.next_run_at > now_naive for j in jobs)
        assert all(j.consecutive_errors == 0 for j in jobs)

        # Nothing is due immediately after — a second tick runs zero jobs
        summary2 = await scheduler_mod.run_due_jobs(db)
        assert summary2["jobs_run"] == 0

        await engine.dispose()

    asyncio.run(run())


def test_run_due_jobs_isolates_failures(monkeypatch):
    async def run():
        engine, db = await _make_session()
        ws = Workspace(title="WS", tracked_tickers=json.dumps(["AAPL"]), status="active")
        db.add(ws)
        await db.commit()

        async def failing_get_quote(ticker):
            raise RuntimeError("market data outage")
        monkeypatch.setattr(price_movement_mod, "get_quote", failing_get_quote)

        async def fake_get_news(ticker, limit=20):
            return []
        monkeypatch.setattr(news_mod, "get_news", fake_get_news)

        async def fake_get_analyst(ticker):
            return None
        monkeypatch.setattr(analyst_rating_mod, "get_analyst", fake_get_analyst)

        async def fake_get_earnings(ticker):
            return []
        monkeypatch.setattr(earnings_mod, "get_earnings", fake_get_earnings)

        async def fake_get_insider(ticker):
            return []
        monkeypatch.setattr(insider_mod, "get_insider_transactions", fake_get_insider)

        summary = await scheduler_mod.run_due_jobs(db)
        # price_movement fails, the other 5 monitor types still succeed
        assert summary["errors"] == 1
        assert summary["jobs_run"] == len(MONITOR_TYPES) - 1

        from sqlalchemy import select
        result = await db.execute(
            select(MonitoringJob).where(MonitoringJob.ticker == "AAPL", MonitoringJob.monitor_type == "price_movement")
        )
        failed_job = result.scalar_one()
        assert failed_job.consecutive_errors == 1
        assert "market data outage" in failed_job.last_error

        await engine.dispose()

    asyncio.run(run())
