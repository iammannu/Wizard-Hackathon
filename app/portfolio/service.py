"""
Portfolio Service — CRUD + accounting for portfolios/holdings/activity.

Accounting method: average cost basis, not FIFO/LIFO — the standard choice
for a research platform (not a tax-lot tool). PortfolioHolding.quantity/
average_cost/realized_gain are never edited directly; every change flows
through record_buy()/record_sell()/import_positions(), each of which writes
a PortfolioActivity row first — the ledger is the source of truth, the
holding's fields are a derived cache (same "ledger is truth, row is cache"
relationship as app/thesis/claims.py's ThesisClaim vs its source thesis
fields).

Market-data refresh reuses app.providers.market.get_quote() (Milestone 0)
directly — no new market-data client. Evidence/Memory/Monitoring/thesis
reuse lives in app/portfolio/intelligence.py, not here — this module is
pure position accounting.
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from app.core.config import get_settings
from app.models.portfolio import Portfolio, PortfolioHolding, HoldingSnapshot, PortfolioActivity
from app.providers.market import get_quote

settings = get_settings()


# ── Portfolio CRUD ───────────────────────────────────────────────────────

async def create_portfolio(db, name: str, description: str = "", base_currency: str = "USD") -> Portfolio:
    portfolio = Portfolio(name=name, description=description, base_currency=base_currency)
    db.add(portfolio)
    await db.flush()
    return portfolio


async def get_portfolio(db, portfolio_id: uuid.UUID) -> Optional[Portfolio]:
    result = await db.execute(select(Portfolio).where(Portfolio.id == portfolio_id))
    return result.scalar_one_or_none()


async def list_portfolios(db, status: str = "active") -> list[Portfolio]:
    query = select(Portfolio)
    if status:
        query = query.where(Portfolio.status == status)
    result = await db.execute(query.order_by(Portfolio.updated_at.desc()))
    return list(result.scalars().all())


async def archive_portfolio(db, portfolio_id: uuid.UUID) -> Optional[Portfolio]:
    portfolio = await get_portfolio(db, portfolio_id)
    if portfolio is None:
        return None
    portfolio.status = "archived"
    portfolio.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return portfolio


async def get_holdings(db, portfolio_id: uuid.UUID, status: Optional[str] = "open") -> list[PortfolioHolding]:
    query = select(PortfolioHolding).where(PortfolioHolding.portfolio_id == portfolio_id)
    if status:
        query = query.where(PortfolioHolding.status == status)
    result = await db.execute(query.order_by(PortfolioHolding.market_value.desc()))
    return list(result.scalars().all())


async def get_holding(db, holding_id: uuid.UUID) -> Optional[PortfolioHolding]:
    result = await db.execute(select(PortfolioHolding).where(PortfolioHolding.id == holding_id))
    return result.scalar_one_or_none()


async def _get_or_create_holding(db, portfolio_id: uuid.UUID, ticker: str) -> PortfolioHolding:
    ticker = ticker.upper()
    result = await db.execute(
        select(PortfolioHolding).where(
            PortfolioHolding.portfolio_id == portfolio_id, PortfolioHolding.ticker == ticker,
        )
    )
    holding = result.scalar_one_or_none()
    if holding is not None:
        return holding

    holding = PortfolioHolding(portfolio_id=portfolio_id, ticker=ticker, status="open")
    db.add(holding)
    await db.flush()
    return holding


# ── Position accounting ──────────────────────────────────────────────────

def _apply_buy(holding: PortfolioHolding, quantity: float, price: float) -> None:
    total_cost = holding.quantity * holding.average_cost + quantity * price
    holding.quantity += quantity
    holding.average_cost = total_cost / holding.quantity if holding.quantity else 0.0
    holding.status = "open"
    holding.closed_at = None
    holding.updated_at = datetime.now(timezone.utc)


def _apply_sell(holding: PortfolioHolding, quantity: float, price: float) -> float:
    """Average-cost realized gain for this sale. Mutates holding in place,
    closing it if the position is fully liquidated. Raises ValueError if
    quantity exceeds what's held — silently clamping would hide a caller
    bug (e.g. a stale quantity from a race) rather than surfacing it."""
    if quantity > holding.quantity + 1e-9:
        raise ValueError(
            f"Cannot sell {quantity} shares of {holding.ticker}: only {holding.quantity} held."
        )
    realized = quantity * (price - holding.average_cost)
    holding.quantity -= quantity
    holding.realized_gain += realized
    holding.updated_at = datetime.now(timezone.utc)
    if holding.quantity <= 1e-9:
        holding.quantity = 0.0
        holding.status = "closed"
        holding.closed_at = datetime.now(timezone.utc)
    return realized


async def record_buy(
    db, portfolio_id: uuid.UUID, ticker: str, quantity: float, price: float, description: str = "",
) -> PortfolioActivity:
    if quantity <= 0 or price < 0:
        raise ValueError("quantity must be > 0 and price must be >= 0")

    holding = await _get_or_create_holding(db, portfolio_id, ticker)
    _apply_buy(holding, quantity, price)

    activity = PortfolioActivity(
        portfolio_id=portfolio_id, holding_id=holding.id, ticker=holding.ticker,
        activity_type="buy", quantity=quantity, price=price, description=description,
    )
    db.add(activity)
    await db.flush()
    return activity


async def record_sell(
    db, portfolio_id: uuid.UUID, ticker: str, quantity: float, price: float, description: str = "",
) -> PortfolioActivity:
    if quantity <= 0 or price < 0:
        raise ValueError("quantity must be > 0 and price must be >= 0")

    holding = await _get_or_create_holding(db, portfolio_id, ticker)
    realized = _apply_sell(holding, quantity, price)

    activity = PortfolioActivity(
        portfolio_id=portfolio_id, holding_id=holding.id, ticker=holding.ticker,
        activity_type="sell", quantity=quantity, price=price, realized_gain=realized, description=description,
    )
    db.add(activity)
    await db.flush()
    return activity


async def remove_holding(
    db, portfolio_id: uuid.UUID, holding_id: uuid.UUID, price: Optional[float] = None,
) -> Optional[PortfolioActivity]:
    """Closes a holding entirely — sells its full remaining quantity at
    `price` (or the last-cached latest_price if not given) so the removal
    is accounted for, not just deleted. Returns None if the holding doesn't
    exist or is already closed with nothing to sell."""
    holding = await get_holding(db, holding_id)
    if holding is None or holding.portfolio_id != portfolio_id or holding.quantity <= 0:
        return None

    exit_price = price if price is not None else (holding.latest_price or holding.average_cost)
    realized = _apply_sell(holding, holding.quantity, exit_price)

    activity = PortfolioActivity(
        portfolio_id=portfolio_id, holding_id=holding.id, ticker=holding.ticker,
        activity_type="holding_removed", quantity=holding.quantity, price=exit_price,
        realized_gain=realized, description="Holding closed",
    )
    db.add(activity)
    await db.flush()
    return activity


async def import_positions(db, portfolio_id: uuid.UUID, positions: list[dict]) -> list[PortfolioHolding]:
    """Bulk-establishes opening positions at a known average cost (e.g. from
    a brokerage export), rather than replaying individual buys. Each entry:
    {"ticker": str, "quantity": float, "average_cost": float, "description": optional str}.
    Importing an existing ticker adds to its position using the same
    weighted-average-cost math as a buy — an import is just a buy whose
    price happens to already be an average."""
    imported: list[PortfolioHolding] = []
    for position in positions:
        ticker = position["ticker"]
        quantity = float(position["quantity"])
        average_cost = float(position["average_cost"])
        if quantity <= 0:
            continue

        holding = await _get_or_create_holding(db, portfolio_id, ticker)
        _apply_buy(holding, quantity, average_cost)

        db.add(PortfolioActivity(
            portfolio_id=portfolio_id, holding_id=holding.id, ticker=holding.ticker,
            activity_type="import", quantity=quantity, price=average_cost,
            description=position.get("description", "Imported position"),
        ))
        imported.append(holding)

    await db.flush()
    return imported


# ── Market data + aggregates ─────────────────────────────────────────────

async def refresh_holding_market_data(holding: PortfolioHolding) -> PortfolioHolding:
    quote = await get_quote(holding.ticker)
    if not quote or not quote.get("price"):
        return holding

    price = quote["price"]
    holding.latest_price = price
    holding.market_value = round(price * holding.quantity, 4)
    holding.unrealized_gain = round((price - holding.average_cost) * holding.quantity, 4)
    holding.unrealized_gain_pct = round(
        (price - holding.average_cost) / holding.average_cost * 100, 4
    ) if holding.average_cost else 0.0
    holding.day_change_pct = quote.get("change_pct")
    holding.updated_at = datetime.now(timezone.utc)
    return holding


def calculate_allocation(holdings: list[PortfolioHolding]) -> list[dict]:
    """Position sizing / allocation weight for each open holding, sorted
    largest-first."""
    total = sum(h.market_value for h in holdings if h.status == "open")
    rows = []
    for h in holdings:
        if h.status != "open":
            continue
        weight_pct = round(h.market_value / total * 100, 2) if total else 0.0
        rows.append({
            "ticker": h.ticker, "holding_id": str(h.id), "market_value": h.market_value,
            "quantity": h.quantity, "weight_pct": weight_pct,
        })
    return sorted(rows, key=lambda r: r["weight_pct"], reverse=True)


def calculate_concentration(holdings: list[PortfolioHolding]) -> dict:
    """Herfindahl-Hirschman Index on a traditional 0-10000 scale (sum of
    squared percentage weights). <1500 = low concentration, 1500-2500 =
    moderate, >2500 = high — the same bands antitrust/finance convention
    uses, configurable via Settings.portfolio_concentration_hhi_*."""
    allocation = calculate_allocation(holdings)
    hhi = round(sum(row["weight_pct"] ** 2 for row in allocation), 2)

    if hhi >= settings.portfolio_concentration_hhi_high:
        band = "high"
    elif hhi >= settings.portfolio_concentration_hhi_moderate:
        band = "moderate"
    else:
        band = "low"

    return {
        "hhi": hhi,
        "band": band,
        "top_holding_weight_pct": allocation[0]["weight_pct"] if allocation else 0.0,
        "top_3_weight_pct": round(sum(r["weight_pct"] for r in allocation[:3]), 2),
        "position_count": len(allocation),
    }


async def recalculate_portfolio_aggregates(db, portfolio_id: uuid.UUID) -> Optional[Portfolio]:
    portfolio = await get_portfolio(db, portfolio_id)
    if portfolio is None:
        return None

    all_holdings = await get_holdings(db, portfolio_id, status=None)
    open_holdings = [h for h in all_holdings if h.status == "open"]

    portfolio.total_cost_basis = round(sum(h.quantity * h.average_cost for h in open_holdings), 4)
    portfolio.total_market_value = round(sum(h.market_value for h in open_holdings), 4)
    portfolio.total_unrealized_gain = round(sum(h.unrealized_gain for h in open_holdings), 4)
    portfolio.total_realized_gain = round(sum(h.realized_gain for h in all_holdings), 4)
    portfolio.holding_count = len(open_holdings)
    portfolio.concentration_hhi = calculate_concentration(open_holdings)["hhi"]
    portfolio.last_synced_at = datetime.now(timezone.utc)
    portfolio.updated_at = portfolio.last_synced_at

    await db.flush()
    return portfolio


async def sync_portfolio_market_data(db, portfolio_id: uuid.UUID, write_snapshots: bool = True) -> Optional[Portfolio]:
    """Refreshes every open holding's market data, recalculates portfolio
    aggregates, and (optionally) writes one HoldingSnapshot per open holding
    — the single entry point app/routers/portfolio.py and
    app/portfolio/summary.py call to get a fully up-to-date portfolio."""
    holdings = await get_holdings(db, portfolio_id, status="open")
    for holding in holdings:
        await refresh_holding_market_data(holding)

    portfolio = await recalculate_portfolio_aggregates(db, portfolio_id)

    if write_snapshots:
        now = datetime.now(timezone.utc)
        for holding in holdings:
            db.add(HoldingSnapshot(
                holding_id=holding.id, portfolio_id=portfolio_id, ticker=holding.ticker,
                price=holding.latest_price or 0.0, market_value=holding.market_value,
                unrealized_gain=holding.unrealized_gain, unrealized_gain_pct=holding.unrealized_gain_pct,
                health_score=holding.health_score, confidence=None, snapshot_at=now,
            ))
        await db.flush()

    return portfolio
