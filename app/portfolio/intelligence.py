"""
Portfolio Intelligence Layer — everything a PortfolioHolding exposes beyond
raw P&L, built entirely by composing existing systems:

  latest evidence     app.agents.base.search_evidence()      (Milestone 2)
  confidence          the EvidencePack's own .confidence, plus thesis
  open alerts         app.monitoring.alert_service.list_alerts() (Milestone 4)
  thesis status       the most-recently-updated Workspace tracking this
                       ticker's denormalized thesis_signal/conviction_score
                       (Milestone 1 Phase — no new thesis logic; a holding
                       isn't itself a workspace, so this is a lookup, not a
                       computation)
  recent SEC filings   app.documents.indexing.document_index.list_documents()
                       (Milestone 1)
  earnings date        app.providers.market.get_earnings()     (Milestone 4)
  analyst changes      app.providers.market.get_analyst() + the
                       analyst_rating MonitoringJob's last_state (Milestone 4)
  insider activity     app.providers.market.get_insider_transactions() (M4)
  risk score            deterministic, from get_candles()'s volatility/
                       drawdown + get_fundamentals()'s beta (reuses
                       app.agents.agents' existing _volatility/_max_drawdown
                       helpers rather than reimplementing them)
  sentiment score +
  AI summary            ONE llm_json call per holding synthesizing news +
                       evidence + memory + alerts — cost-bounded the same
                       way Evidence Engine's conflict/claim detection is
                       (one call per unit of work, not one per input item)

Position Health Score: a deterministic weighted blend of the above 8
factors (Settings.health_weight_*), not LLM-judged — same "scoring is a
formula, not a model call" precedent as
app/documents/evidence/scorer.py.
"""
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from app.core.config import get_settings
from app.core.llm import llm_json
from app.agents.agents import _volatility, _max_drawdown
from app.agents.base import search_evidence, recall_memory
from app.providers.market import get_candles, get_fundamentals, get_analyst, get_earnings, get_insider_transactions, get_news
from app.documents.indexing import document_index
from app.models.workspace import Workspace
from app.models.monitoring import MonitoringJob
from app.models.portfolio import PortfolioHolding
from app.monitoring import alert_service

settings = get_settings()


async def _find_tracking_workspace(db, ticker: str) -> Optional[Workspace]:
    """Most-recently-updated active workspace tracking this ticker, if any.
    Filtered in Python (not a SQL LIKE on the JSON-as-text column) to avoid
    substring false positives like ticker "A" matching a stored "AAPL"."""
    result = await db.execute(
        select(Workspace).where(Workspace.status == "active").order_by(Workspace.updated_at.desc())
    )
    for ws in result.scalars().all():
        if ticker.upper() in ws.tickers_list():
            return ws
    return None


def _risk_score(candles: list[dict], fundamentals: Optional[dict]) -> float:
    """0-100, higher = riskier. Deterministic — volatility (40%), beta
    (30%), max drawdown (30%), each normalized to [0, 1]."""
    closes = [c["close"] for c in candles if c.get("close")]
    if not closes:
        return 50.0  # no data — neutral, not falsely safe

    volatility = _volatility(closes)
    drawdown = abs(_max_drawdown(closes))
    beta = (fundamentals or {}).get("beta") or 1.0

    vol_component = min(1.0, volatility / settings.portfolio_risk_volatility_high_pct)
    beta_component = min(1.0, max(0.0, (beta - 1.0)))
    drawdown_component = min(1.0, drawdown / 50.0)

    return round((vol_component * 0.4 + beta_component * 0.3 + drawdown_component * 0.3) * 100, 1)


def _valuation_factor(fundamentals: Optional[dict]) -> float:
    """0-1, higher = more attractively valued. A deliberately simple PE-band
    heuristic, not a DCF — Evidence Engine / agent-level valuation analysis
    is the deep version of this; this is a fast, formula-only input to the
    health score, consistent with the rest of this function's factors."""
    pe = (fundamentals or {}).get("pe_ratio")
    if pe is None or pe <= 0:
        return 0.5
    if pe <= 15:
        return 1.0
    if pe <= 30:
        return round(1.0 - (pe - 15) / 15 * 0.5, 3)  # linear taper 1.0 -> 0.5
    if pe <= 45:
        return round(0.5 - (pe - 30) / 15 * 0.3, 3)  # taper 0.5 -> 0.2
    return 0.2


async def _analyst_revision_factor(db, ticker: str) -> float:
    """0-1, higher = more positive analyst momentum. Reads the
    analyst_rating MonitoringJob's last_state rather than re-deriving a
    transition history — Milestone 4 already tracks it."""
    result = await db.execute(
        select(MonitoringJob).where(MonitoringJob.ticker == ticker.upper(), MonitoringJob.monitor_type == "analyst_rating")
    )
    job = result.scalar_one_or_none()
    if job is None:
        return 0.6
    consensus = job.last_state_dict().get("consensus")
    return {"buy": 0.9, "hold": 0.55, "sell": 0.2}.get(consensus, 0.6)


def _earnings_risk_factor(earnings: list[dict]) -> float:
    """0-1, higher = lower earnings risk. Based on the most recent reported
    quarter's beat/miss (get_earnings() history, not a forward calendar —
    Finnhub's free tier doesn't expose upcoming earnings dates)."""
    if not earnings:
        return 0.6
    latest = earnings[0]
    actual, estimate = latest.get("actual"), latest.get("estimate")
    if actual is None or not estimate:
        return 0.6
    delta_pct = (actual - estimate) / abs(estimate)
    if delta_pct > 0.01:
        return 0.9
    if delta_pct < -0.01:
        return 0.25
    return 0.6


def _insider_activity_factor(transactions: list[dict]) -> float:
    """0-1, higher = more insider buying (a mildly positive signal),
    lower = more insider selling. Net share change over the most recent
    transactions on file."""
    if not transactions:
        return 0.5
    net_change = sum((t.get("change") or 0) for t in transactions[:10])
    if net_change > 0:
        return 0.75
    if net_change < 0:
        return 0.4
    return 0.5


def _alert_severity_factor(open_alerts: list) -> float:
    """0-1, higher = fewer/less-severe open alerts."""
    penalty = 0.0
    for alert in open_alerts:
        penalty += {"critical": 0.4, "warning": 0.2, "info": 0.05}.get(alert.severity, 0.1)
    return max(0.0, 1.0 - min(1.0, penalty))


async def _sentiment_and_summary(ticker: str, news: list[dict], evidence_text: str, memory_text: str, alert_titles: list[str]) -> tuple[float, str]:
    """One LLM call: sentiment_score (-1..1) + a 2-3 sentence AI summary,
    synthesizing news + evidence + memory + alerts. Never raises — falls
    back to neutral sentiment and a template summary on failure, same
    resilience contract as every other llm_json caller in this codebase."""
    news_text = "\n".join(f"- {n.get('title','')}" for n in news[:6])
    alerts_text = "\n".join(f"- {t}" for t in alert_titles[:5]) or "None"

    try:
        result = await llm_json(
            system="""You are a portfolio analyst summarizing the current state of one holding.
Return JSON: {"sentiment_score": -1.0 to 1.0, "summary": "2-3 sentence plain-English summary of where this position stands right now and why"}""",
            user=(
                f"Ticker: {ticker}\nRecent news:\n{news_text or 'None'}\n"
                f"Retrieved evidence:\n{evidence_text[:500]}\nRelevant memory:\n{memory_text[:500]}\n"
                f"Open alerts:\n{alerts_text}"
            ),
            fast=True,
        )
    except Exception:
        result = {}

    sentiment = result.get("sentiment_score")
    try:
        sentiment = max(-1.0, min(1.0, float(sentiment)))
    except (TypeError, ValueError):
        sentiment = 0.0
    summary = result.get("summary") or f"No AI summary available for {ticker} this cycle."
    return sentiment, summary


async def build_holding_intelligence(db, holding: PortfolioHolding) -> dict:
    """Assembles the full intelligence payload for one holding. Also
    updates the holding's cached health_score/risk_score/sentiment_score/
    ai_summary fields in place (caller commits)."""
    ticker = holding.ticker

    evidence_pack = await search_evidence(f"{ticker} investment thesis recent developments", ticker=ticker, top_k=3)
    memory_pack = await recall_memory(f"{ticker} investment thesis", ticker=ticker, top_k=5)
    open_alerts = await alert_service.list_alerts(db, ticker=ticker, status="unread", limit=20)
    tracking_workspace = await _find_tracking_workspace(db, ticker)
    filings = await document_index.list_documents(db, ticker=ticker, limit=5)

    raw_results = await _gather_market_inputs(ticker)
    list_default_positions = {0, 3, 4, 5}  # candles, earnings, insiders, news default to [] on failure; fundamentals/analyst default to None
    candles, fundamentals, analyst, earnings, insiders, news = [
        (r if not isinstance(r, Exception) else ([] if i in list_default_positions else None))
        for i, r in enumerate(raw_results)
    ]

    risk_score = _risk_score(candles or [], fundamentals)
    evidence_text = "\n".join(e.text[:200] for e in evidence_pack.evidence[:3])
    memory_text = "\n".join(m.content[:150] for m in memory_pack.items[:5])
    sentiment_score, ai_summary = await _sentiment_and_summary(
        ticker, news or [], evidence_text, memory_text, [a.title for a in open_alerts]
    )

    factors = {
        "evidence_quality": evidence_pack.confidence,
        "alert_severity": _alert_severity_factor(open_alerts),
        "valuation": _valuation_factor(fundamentals),
        "analyst_revisions": await _analyst_revision_factor(db, ticker),
        "earnings_risk": _earnings_risk_factor(earnings or []),
        "insider_activity": _insider_activity_factor(insiders or []),
        "sentiment": (sentiment_score + 1.0) / 2.0,
        "thesis_confidence": tracking_workspace.confidence if tracking_workspace else 0.5,
    }
    weights = {
        "evidence_quality": settings.health_weight_evidence_quality,
        "alert_severity": settings.health_weight_alert_severity,
        "valuation": settings.health_weight_valuation,
        "analyst_revisions": settings.health_weight_analyst_revisions,
        "earnings_risk": settings.health_weight_earnings_risk,
        "insider_activity": settings.health_weight_insider_activity,
        "sentiment": settings.health_weight_sentiment,
        "thesis_confidence": settings.health_weight_thesis_confidence,
    }
    health_score = round(sum(factors[k] * weights[k] for k in factors) * 100, 1)

    holding.health_score = health_score
    holding.risk_score = risk_score
    holding.sentiment_score = sentiment_score
    holding.ai_summary = ai_summary
    holding.intelligence_updated_at = datetime.now(timezone.utc)

    return {
        "ticker": ticker,
        "health_score": health_score,
        "health_score_factors": {k: round(v, 3) for k, v in factors.items()},
        "risk_score": risk_score,
        "sentiment_score": round(sentiment_score, 3),
        "ai_summary": ai_summary,
        "confidence": evidence_pack.confidence,
        "latest_evidence": [
            {"text": e.text[:300], "citation": e.citation.citation_id, "score": e.score.overall}
            for e in evidence_pack.evidence[:3]
        ],
        "open_alerts": [a.to_dict() for a in open_alerts],
        "thesis_status": {
            "workspace_id": str(tracking_workspace.id), "workspace_title": tracking_workspace.title,
            "thesis_signal": tracking_workspace.thesis_signal, "conviction_score": tracking_workspace.conviction_score,
            "lifecycle_stage": tracking_workspace.thesis_lifecycle_stage,
        } if tracking_workspace else None,
        "recent_filings": [
            {"doc_type": f.doc_type, "filing_date": f.filing_date.isoformat() if f.filing_date else None, "title": f.title}
            for f in filings
        ],
        "earnings": earnings[0] if earnings else None,
        "analyst": analyst,
        "insider_activity": (insiders or [])[:5],
    }


async def _gather_market_inputs(ticker: str):
    import asyncio
    return await asyncio.gather(
        get_candles(ticker, "1d", 252), get_fundamentals(ticker), get_analyst(ticker),
        get_earnings(ticker), get_insider_transactions(ticker), get_news(ticker, 10),
        return_exceptions=True,
    )
