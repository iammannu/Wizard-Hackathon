"""
Daily Portfolio Summary — biggest winners/losers, new alerts, thesis
changes, confidence changes, evidence changes, and macro events shared
across holdings, all derived from existing systems (no new data source).

Cost control: per-holding intelligence (the one LLM call in
app/portfolio/intelligence.py) only re-runs for holdings whose cached
intelligence is missing or older than the lookback window — a summary
generated twice in the same window doesn't double the LLM spend. The
cross-portfolio "macro events" section is a second, separate LLM call, but
only ONE regardless of portfolio size (same one-call-per-unit-of-work
discipline as Evidence Engine's conflict/claim detection).
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import get_settings
from app.core.llm import llm_json
from app.core.database import ensure_aware_utc
from app.models.portfolio import HoldingSnapshot
from app.models.thesis import ThesisVersion
from app.documents.indexing import document_index
from app.monitoring import alert_service
from app.portfolio import service, intelligence

settings = get_settings()


async def _refresh_stale_intelligence(db, holdings, cutoff) -> None:
    for holding in holdings:
        if holding.intelligence_updated_at is not None and ensure_aware_utc(holding.intelligence_updated_at) >= cutoff:
            continue
        result = await intelligence.build_holding_intelligence(db, holding)
        db.add(HoldingSnapshot(
            holding_id=holding.id, portfolio_id=holding.portfolio_id, ticker=holding.ticker,
            price=holding.latest_price or 0.0, market_value=holding.market_value,
            unrealized_gain=holding.unrealized_gain, unrealized_gain_pct=holding.unrealized_gain_pct,
            health_score=holding.health_score, confidence=result["confidence"],
        ))
    await db.flush()


def _winners_and_losers(holdings, top_n: int = 3) -> tuple[list[dict], list[dict]]:
    movers = [h for h in holdings if h.day_change_pct is not None]
    winners = sorted([h for h in movers if h.day_change_pct > 0], key=lambda h: h.day_change_pct, reverse=True)[:top_n]
    losers = sorted([h for h in movers if h.day_change_pct < 0], key=lambda h: h.day_change_pct)[:top_n]
    to_dict = lambda h: {"ticker": h.ticker, "day_change_pct": h.day_change_pct, "market_value": h.market_value}
    return [to_dict(h) for h in winners], [to_dict(h) for h in losers]


async def _new_alerts(db, tickers: list[str], cutoff: datetime) -> list[dict]:
    found = []
    for ticker in tickers:
        alerts = await alert_service.list_alerts(db, ticker=ticker, limit=50)
        found.extend(a.to_dict() for a in alerts if ensure_aware_utc(a.created_at) >= cutoff)
    return found


async def _thesis_changes(db, tickers: list[str], cutoff: datetime) -> list[dict]:
    changes = []
    for ticker in tickers:
        workspace = await intelligence._find_tracking_workspace(db, ticker)
        if workspace is None or workspace.current_thesis_version_id is None:
            continue
        result = await db.execute(
            select(ThesisVersion).where(ThesisVersion.id == workspace.current_thesis_version_id)
        )
        version = result.scalar_one_or_none()
        if version is not None and ensure_aware_utc(version.created_at) >= cutoff:
            changes.append({
                "ticker": ticker, "workspace_id": str(workspace.id), "workspace_title": workspace.title,
                "signal": version.signal, "change_type": version.change_type,
                "is_major_change": version.is_major_change, "lifecycle_stage": version.lifecycle_stage,
            })
    return changes


async def _confidence_changes(db, holdings, threshold: float = 0.03) -> list[dict]:
    changes = []
    for holding in holdings:
        result = await db.execute(
            select(HoldingSnapshot)
            .where(HoldingSnapshot.holding_id == holding.id)
            .order_by(HoldingSnapshot.snapshot_at.desc())
            .limit(2)
        )
        snapshots = result.scalars().all()
        if len(snapshots) < 2:
            continue
        current, previous = snapshots[0], snapshots[1]
        if current.confidence is None or previous.confidence is None:
            continue
        delta = round(current.confidence - previous.confidence, 3)
        if abs(delta) >= threshold:
            changes.append({
                "ticker": holding.ticker, "previous_confidence": previous.confidence,
                "current_confidence": current.confidence, "delta": delta,
            })
    return changes


async def _evidence_changes(db, tickers: list[str], cutoff: datetime) -> list[dict]:
    changes = []
    for ticker in tickers:
        docs = await document_index.list_documents(db, ticker=ticker, limit=10)
        for doc in docs:
            if ensure_aware_utc(doc.updated_at) >= cutoff:
                changes.append({
                    "ticker": ticker, "doc_type": doc.doc_type, "title": doc.title,
                    "status": doc.status, "updated_at": doc.updated_at.isoformat(),
                })
    return changes


async def _macro_events(holdings) -> list[str]:
    """One LLM call across every holding's cached AI summary — looks for a
    shared macro theme rather than repeating per-ticker analysis."""
    summaries = "\n".join(f"- {h.ticker}: {h.ai_summary}" for h in holdings if h.ai_summary)
    if not summaries:
        return []
    try:
        result = await llm_json(
            system="""Given per-holding summaries from an investment portfolio, identify shared
macroeconomic or cross-cutting themes affecting multiple holdings (e.g. rate policy, a sector-wide
regulatory shift, a supply chain theme). Return JSON: {"themes": ["1 sentence each, only include themes that plausibly affect 2+ holdings"]}. Return an empty list if nothing clearly cross-cutting stands out — don't force it.""",
            user=summaries[:3000],
            fast=True,
        )
    except Exception:
        return []
    themes = result.get("themes", []) if isinstance(result, dict) else []
    return [t for t in themes if isinstance(t, str)]


async def generate_daily_summary(db, portfolio_id, refresh_intelligence: bool = True) -> dict | None:
    portfolio = await service.get_portfolio(db, portfolio_id)
    if portfolio is None:
        return None

    await service.sync_portfolio_market_data(db, portfolio_id, write_snapshots=False)
    holdings = await service.get_holdings(db, portfolio_id, status="open")
    tickers = [h.ticker for h in holdings]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.portfolio_summary_lookback_hours)

    if refresh_intelligence:
        await _refresh_stale_intelligence(db, holdings, cutoff)

    winners, losers = _winners_and_losers(holdings)

    return {
        "portfolio_id": str(portfolio_id),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_hours": settings.portfolio_summary_lookback_hours,
        "total_market_value": portfolio.total_market_value,
        "total_unrealized_gain": portfolio.total_unrealized_gain,
        "total_unrealized_gain_pct": round(
            portfolio.total_unrealized_gain / portfolio.total_cost_basis * 100, 2
        ) if portfolio.total_cost_basis else 0.0,
        "biggest_winners": winners,
        "biggest_losers": losers,
        "new_alerts": await _new_alerts(db, tickers, cutoff),
        "thesis_changes": await _thesis_changes(db, tickers, cutoff),
        "confidence_changes": await _confidence_changes(db, holdings),
        "evidence_changes": await _evidence_changes(db, tickers, cutoff),
        "macro_events": await _macro_events(holdings),
    }
