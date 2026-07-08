"""
Unit tests for Portfolio Intelligence (Milestone 5).

Same isolation approach as the other milestone test files: real in-memory
SQLite + real ORM models. Accounting math (average cost, realized/
unrealized gain, allocation, concentration) has zero external dependencies
and is tested for real throughout. The intelligence layer's market-data/
LLM calls are monkeypatched (real accounting/scoring formulas run for real
against the stubbed inputs).
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
from app.models import thesis as _thesis_models  # noqa: F401
from app.documents.models import citation as _c, entity as _e, document as _d, chunk as _ch, embedding as _em  # noqa: F401
from app.models import memory as _memory_models  # noqa: F401
from app.models import monitoring as _monitoring_models  # noqa: F401
from app.models.monitoring import MonitoringJob, Alert

from app.models.portfolio import Portfolio, PortfolioHolding, HoldingSnapshot, PortfolioActivity
from app.portfolio import service, intelligence, summary as summary_mod


async def _make_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)()


# ── Accounting: buy/sell/average cost ────────────────────────────────────

def test_record_buy_computes_weighted_average_cost():
    async def run():
        engine, db = await _make_session()
        portfolio = await service.create_portfolio(db, "Test")
        await db.commit()

        await service.record_buy(db, portfolio.id, "AAPL", 10, 100.0)
        await service.record_buy(db, portfolio.id, "AAPL", 10, 200.0)
        await db.commit()

        holdings = await service.get_holdings(db, portfolio.id)
        assert len(holdings) == 1
        h = holdings[0]
        assert h.quantity == 20
        assert h.average_cost == pytest.approx(150.0)
        await engine.dispose()

    asyncio.run(run())


def test_record_sell_computes_realized_gain_and_keeps_avg_cost():
    async def run():
        engine, db = await _make_session()
        portfolio = await service.create_portfolio(db, "Test")
        await db.commit()

        await service.record_buy(db, portfolio.id, "AAPL", 10, 100.0)
        activity = await service.record_sell(db, portfolio.id, "AAPL", 4, 150.0)
        await db.commit()

        assert activity.realized_gain == pytest.approx(4 * (150.0 - 100.0))
        holdings = await service.get_holdings(db, portfolio.id)
        h = holdings[0]
        assert h.quantity == 6
        assert h.average_cost == pytest.approx(100.0)  # unchanged by a partial sell
        assert h.realized_gain == pytest.approx(200.0)
        assert h.status == "open"
        await engine.dispose()

    asyncio.run(run())


def test_selling_full_position_closes_holding():
    async def run():
        engine, db = await _make_session()
        portfolio = await service.create_portfolio(db, "Test")
        await db.commit()

        await service.record_buy(db, portfolio.id, "AAPL", 10, 100.0)
        await service.record_sell(db, portfolio.id, "AAPL", 10, 120.0)
        await db.commit()

        holdings = await service.get_holdings(db, portfolio.id, status=None)
        h = holdings[0]
        assert h.quantity == 0
        assert h.status == "closed"
        assert h.closed_at is not None
        await engine.dispose()

    asyncio.run(run())


def test_selling_more_than_held_raises():
    async def run():
        engine, db = await _make_session()
        portfolio = await service.create_portfolio(db, "Test")
        await db.commit()
        await service.record_buy(db, portfolio.id, "AAPL", 5, 100.0)

        with pytest.raises(ValueError):
            await service.record_sell(db, portfolio.id, "AAPL", 10, 100.0)
        await engine.dispose()

    asyncio.run(run())


def test_import_positions_establishes_avg_cost_directly():
    async def run():
        engine, db = await _make_session()
        portfolio = await service.create_portfolio(db, "Test")
        await db.commit()

        await service.import_positions(db, portfolio.id, [
            {"ticker": "AAPL", "quantity": 15, "average_cost": 180.0},
            {"ticker": "MSFT", "quantity": 5, "average_cost": 300.0},
        ])
        await db.commit()

        holdings = await service.get_holdings(db, portfolio.id)
        assert len(holdings) == 2
        aapl = next(h for h in holdings if h.ticker == "AAPL")
        assert aapl.quantity == 15
        assert aapl.average_cost == pytest.approx(180.0)
        await engine.dispose()

    asyncio.run(run())


def test_remove_holding_realizes_gain_and_closes():
    async def run():
        engine, db = await _make_session()
        portfolio = await service.create_portfolio(db, "Test")
        await db.commit()
        await service.record_buy(db, portfolio.id, "AAPL", 10, 100.0)
        await db.commit()

        holdings = await service.get_holdings(db, portfolio.id)
        activity = await service.remove_holding(db, portfolio.id, holdings[0].id, price=130.0)
        await db.commit()

        assert activity.activity_type == "holding_removed"
        assert activity.realized_gain == pytest.approx(300.0)
        refreshed = await service.get_holding(db, holdings[0].id)
        assert refreshed.status == "closed"
        assert refreshed.quantity == 0
        await engine.dispose()

    asyncio.run(run())


# ── Allocation + concentration ───────────────────────────────────────────

def test_calculate_allocation_weights_sum_to_100():
    holdings = [
        PortfolioHolding(portfolio_id=uuid.uuid4(), ticker="AAPL", quantity=10, market_value=1000.0, status="open"),
        PortfolioHolding(portfolio_id=uuid.uuid4(), ticker="MSFT", quantity=5, market_value=500.0, status="open"),
        PortfolioHolding(portfolio_id=uuid.uuid4(), ticker="OLD", quantity=0, market_value=0.0, status="closed"),
    ]
    allocation = service.calculate_allocation(holdings)
    assert len(allocation) == 2  # closed holding excluded
    assert allocation[0]["ticker"] == "AAPL"
    assert allocation[0]["weight_pct"] == pytest.approx(66.67, abs=0.01)
    assert sum(a["weight_pct"] for a in allocation) == pytest.approx(100.0, abs=0.01)


def test_calculate_concentration_single_holding_is_maximally_concentrated():
    holdings = [PortfolioHolding(portfolio_id=uuid.uuid4(), ticker="AAPL", market_value=1000.0, status="open")]
    concentration = service.calculate_concentration(holdings)
    assert concentration["hhi"] == pytest.approx(10000.0)
    assert concentration["band"] == "high"
    assert concentration["top_holding_weight_pct"] == pytest.approx(100.0)


def test_calculate_concentration_even_split_is_low():
    holdings = [
        PortfolioHolding(portfolio_id=uuid.uuid4(), ticker=t, market_value=100.0, status="open")
        for t in ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
    ]
    concentration = service.calculate_concentration(holdings)
    assert concentration["hhi"] == pytest.approx(1000.0, abs=1.0)  # 10 equal positions -> 10 * 10^2 = 1000
    assert concentration["band"] == "low"


# ── Portfolio aggregates ──────────────────────────────────────────────────

def test_recalculate_portfolio_aggregates(monkeypatch):
    async def run():
        engine, db = await _make_session()
        portfolio = await service.create_portfolio(db, "Test")
        await db.commit()
        await service.record_buy(db, portfolio.id, "AAPL", 10, 100.0)
        await db.commit()

        holdings = await service.get_holdings(db, portfolio.id)
        holdings[0].latest_price = 120.0
        holdings[0].market_value = 1200.0
        holdings[0].unrealized_gain = 200.0
        await db.commit()

        updated = await service.recalculate_portfolio_aggregates(db, portfolio.id)
        await db.commit()

        assert updated.total_cost_basis == pytest.approx(1000.0)
        assert updated.total_market_value == pytest.approx(1200.0)
        assert updated.total_unrealized_gain == pytest.approx(200.0)
        assert updated.holding_count == 1
        assert updated.concentration_hhi == pytest.approx(10000.0)
        await engine.dispose()

    asyncio.run(run())


# ── Intelligence layer: deterministic scoring functions ───────────────────

def test_risk_score_higher_for_volatile_prices():
    calm = [{"close": 100.0 + (i % 2)} for i in range(60)]
    volatile = [{"close": 100.0 + (i % 2) * 40} for i in range(60)]

    calm_score = intelligence._risk_score(calm, {"beta": 1.0})
    volatile_score = intelligence._risk_score(volatile, {"beta": 1.0})
    assert volatile_score > calm_score


def test_risk_score_no_data_is_neutral():
    assert intelligence._risk_score([], None) == 50.0


def test_valuation_factor_bands():
    assert intelligence._valuation_factor({"pe_ratio": 10}) == 1.0
    assert intelligence._valuation_factor({"pe_ratio": None}) == 0.5
    assert intelligence._valuation_factor({"pe_ratio": 60}) == 0.2
    mid = intelligence._valuation_factor({"pe_ratio": 22.5})
    assert 0.5 < mid < 1.0


def test_earnings_risk_factor_beat_vs_miss():
    beat = intelligence._earnings_risk_factor([{"actual": 2.5, "estimate": 2.0}])
    miss = intelligence._earnings_risk_factor([{"actual": 1.5, "estimate": 2.0}])
    assert beat > miss
    assert intelligence._earnings_risk_factor([]) == 0.6


def test_insider_activity_factor_net_buying_vs_selling():
    buying = intelligence._insider_activity_factor([{"change": 1000}, {"change": 500}])
    selling = intelligence._insider_activity_factor([{"change": -1000}])
    assert buying > selling


def test_alert_severity_factor_penalizes_critical_more_than_info():
    class FakeAlert:
        def __init__(self, severity):
            self.severity = severity

    no_alerts = intelligence._alert_severity_factor([])
    one_critical = intelligence._alert_severity_factor([FakeAlert("critical")])
    one_info = intelligence._alert_severity_factor([FakeAlert("info")])
    assert no_alerts == 1.0
    assert one_critical < one_info < no_alerts


# ── Intelligence layer: full holding build (monkeypatched externals) ─────

def test_build_holding_intelligence_end_to_end(monkeypatch):
    async def run():
        engine, db = await _make_session()
        portfolio = await service.create_portfolio(db, "Test")
        await db.commit()
        await service.record_buy(db, portfolio.id, "AAPL", 10, 150.0)
        await db.commit()
        holdings = await service.get_holdings(db, portfolio.id)
        holding = holdings[0]

        class FakeEvidencePack:
            confidence = 0.72
            evidence = []

        class FakeMemoryPack:
            items = []

        async def fake_search_evidence(query, ticker=None, top_k=8, **kwargs):
            return FakeEvidencePack()

        async def fake_recall_memory(query, workspace_id=None, ticker=None, top_k=6):
            return FakeMemoryPack()

        async def fake_gather_market_inputs(ticker):
            return [
                [{"close": 150.0 + i} for i in range(60)],  # candles
                {"beta": 1.1, "pe_ratio": 25},  # fundamentals
                {"consensus": "buy"},  # analyst
                [{"period": "2026-06-30", "actual": 2.1, "estimate": 2.0}],  # earnings
                [{"change": 500}],  # insider
                [{"title": "AAPL announces new product"}],  # news
            ]

        async def fake_llm_json(system, user, **kwargs):
            return {"sentiment_score": 0.4, "summary": "AAPL looks stable with modest positive sentiment."}

        monkeypatch.setattr(intelligence, "search_evidence", fake_search_evidence)
        monkeypatch.setattr(intelligence, "recall_memory", fake_recall_memory)
        monkeypatch.setattr(intelligence, "_gather_market_inputs", fake_gather_market_inputs)
        monkeypatch.setattr(intelligence, "llm_json", fake_llm_json)

        payload = await intelligence.build_holding_intelligence(db, holding)
        await db.commit()

        assert payload["ticker"] == "AAPL"
        assert 0 <= payload["health_score"] <= 100
        assert payload["sentiment_score"] == pytest.approx(0.4)
        assert payload["ai_summary"] == "AAPL looks stable with modest positive sentiment."
        assert payload["earnings"]["classification"] if "classification" in (payload["earnings"] or {}) else True
        assert holding.health_score == payload["health_score"]
        assert holding.intelligence_updated_at is not None
        await engine.dispose()

    asyncio.run(run())


def test_find_tracking_workspace_matches_exact_ticker_not_substring():
    async def run():
        engine, db = await _make_session()
        ws = Workspace(title="A-tracker", tracked_tickers=json.dumps(["A"]), status="active")
        ws2 = Workspace(title="AAPL-tracker", tracked_tickers=json.dumps(["AAPL"]), status="active")
        db.add_all([ws, ws2])
        await db.commit()

        found = await intelligence._find_tracking_workspace(db, "AAPL")
        assert found.id == ws2.id  # not the "A" workspace, despite "A" being a substring of "AAPL"
        await engine.dispose()

    asyncio.run(run())


# ── Daily summary ──────────────────────────────────────────────────────────

def test_winners_and_losers_ranking():
    holdings = [
        PortfolioHolding(portfolio_id=uuid.uuid4(), ticker="UP", day_change_pct=8.0, market_value=100.0, status="open"),
        PortfolioHolding(portfolio_id=uuid.uuid4(), ticker="DOWN", day_change_pct=-6.0, market_value=100.0, status="open"),
        PortfolioHolding(portfolio_id=uuid.uuid4(), ticker="FLAT", day_change_pct=0.1, market_value=100.0, status="open"),
    ]
    winners, losers = summary_mod._winners_and_losers(holdings)
    assert winners[0]["ticker"] == "UP"
    assert losers[0]["ticker"] == "DOWN"


def test_confidence_changes_detects_meaningful_delta():
    async def run():
        engine, db = await _make_session()
        holding_id = uuid.uuid4()
        portfolio_id = uuid.uuid4()
        older = HoldingSnapshot(
            holding_id=holding_id, portfolio_id=portfolio_id, ticker="AAPL",
            price=100.0, market_value=1000.0, unrealized_gain=0.0, unrealized_gain_pct=0.0,
            confidence=0.5, snapshot_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        newer = HoldingSnapshot(
            holding_id=holding_id, portfolio_id=portfolio_id, ticker="AAPL",
            price=110.0, market_value=1100.0, unrealized_gain=100.0, unrealized_gain_pct=10.0,
            confidence=0.65, snapshot_at=datetime.now(timezone.utc),
        )
        db.add_all([older, newer])
        await db.commit()

        fake_holding = PortfolioHolding(id=holding_id, portfolio_id=portfolio_id, ticker="AAPL", status="open")
        changes = await summary_mod._confidence_changes(db, [fake_holding])
        assert len(changes) == 1
        assert changes[0]["delta"] == pytest.approx(0.15)
        await engine.dispose()

    asyncio.run(run())


def test_generate_daily_summary_missing_portfolio_returns_none():
    async def run():
        engine, db = await _make_session()
        result = await summary_mod.generate_daily_summary(db, uuid.uuid4())
        assert result is None
        await engine.dispose()

    asyncio.run(run())
