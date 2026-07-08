"""
Portfolio router — Milestone 5.

Endpoints named per the milestone spec: /portfolio, /portfolio/{id},
/portfolio/summary, /portfolio/health, /portfolio/holdings, /watchlists.
Full API polish (pagination, bulk edits) is Milestone 9's job — this gives
enough surface for real CRUD + the intelligence/summary/health views to be
exercised end to end.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.database import get_db
from app.models.portfolio import Watchlist
from app.portfolio import service, intelligence, summary as summary_mod

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])
watchlist_router = APIRouter(prefix="/api/v1/watchlists", tags=["watchlists"])


# ── Request models ────────────────────────────────────────────────────────

class CreatePortfolioRequest(BaseModel):
    name: str
    description: str = ""
    base_currency: str = "USD"


class UpdatePortfolioRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class BuyRequest(BaseModel):
    ticker: str
    quantity: float
    price: float
    description: str = ""


class SellRequest(BaseModel):
    quantity: float
    price: float
    description: str = ""


class ImportPositionsRequest(BaseModel):
    positions: list[dict]  # [{"ticker": str, "quantity": float, "average_cost": float}]


class CreateWatchlistRequest(BaseModel):
    name: str
    description: str = ""
    tickers: list[str] = []


class UpdateWatchlistRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tickers: Optional[list[str]] = None


def _uuid(value: str, label: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(400, f"Invalid {label}")


# ── Portfolio CRUD ────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_portfolio(body: CreatePortfolioRequest):
    async for db in get_db():
        portfolio = await service.create_portfolio(db, body.name, body.description, body.base_currency)
        await db.commit()
        await db.refresh(portfolio)
        return portfolio.to_dict()


@router.get("")
async def list_portfolios(status: Optional[str] = "active"):
    async for db in get_db():
        portfolios = await service.list_portfolios(db, status=status)
        return [p.to_dict() for p in portfolios]


@router.get("/{portfolio_id}")
async def get_portfolio(portfolio_id: str, sync: bool = Query(False, description="Refresh market data before returning")):
    async for db in get_db():
        pid = _uuid(portfolio_id, "portfolio ID")
        portfolio = await service.get_portfolio(db, pid)
        if portfolio is None:
            raise HTTPException(404, "Portfolio not found")

        if sync:
            await service.sync_portfolio_market_data(db, pid)
            await db.commit()
            await db.refresh(portfolio)

        holdings = await service.get_holdings(db, pid, status="open")
        data = portfolio.to_dict()
        data["holdings"] = [h.to_dict() for h in holdings]
        data["allocation"] = service.calculate_allocation(holdings)
        data["concentration"] = service.calculate_concentration(holdings)
        return data


@router.patch("/{portfolio_id}")
async def update_portfolio(portfolio_id: str, body: UpdatePortfolioRequest):
    async for db in get_db():
        pid = _uuid(portfolio_id, "portfolio ID")
        portfolio = await service.get_portfolio(db, pid)
        if portfolio is None:
            raise HTTPException(404, "Portfolio not found")
        if body.name is not None:
            portfolio.name = body.name
        if body.description is not None:
            portfolio.description = body.description
        await db.commit()
        await db.refresh(portfolio)
        return portfolio.to_dict()


@router.delete("/{portfolio_id}", status_code=204)
async def archive_portfolio(portfolio_id: str):
    async for db in get_db():
        pid = _uuid(portfolio_id, "portfolio ID")
        portfolio = await service.archive_portfolio(db, pid)
        if portfolio is None:
            raise HTTPException(404, "Portfolio not found")
        await db.commit()


@router.post("/{portfolio_id}/sync")
async def sync_portfolio(portfolio_id: str):
    async for db in get_db():
        pid = _uuid(portfolio_id, "portfolio ID")
        portfolio = await service.sync_portfolio_market_data(db, pid)
        if portfolio is None:
            raise HTTPException(404, "Portfolio not found")
        await db.commit()
        await db.refresh(portfolio)
        return portfolio.to_dict()


# ── Holdings ──────────────────────────────────────────────────────────────

@router.get("/{portfolio_id}/holdings")
async def list_holdings(portfolio_id: str, status: Optional[str] = "open"):
    async for db in get_db():
        pid = _uuid(portfolio_id, "portfolio ID")
        holdings = await service.get_holdings(db, pid, status=status)
        return [h.to_dict() for h in holdings]


@router.post("/{portfolio_id}/holdings", status_code=201)
async def buy_holding(portfolio_id: str, body: BuyRequest):
    async for db in get_db():
        pid = _uuid(portfolio_id, "portfolio ID")
        if await service.get_portfolio(db, pid) is None:
            raise HTTPException(404, "Portfolio not found")
        try:
            activity = await service.record_buy(db, pid, body.ticker, body.quantity, body.price, body.description)
        except ValueError as e:
            raise HTTPException(400, str(e))
        await service.recalculate_portfolio_aggregates(db, pid)
        await db.commit()
        return activity.to_dict()


@router.post("/{portfolio_id}/holdings/import")
async def import_positions(portfolio_id: str, body: ImportPositionsRequest):
    async for db in get_db():
        pid = _uuid(portfolio_id, "portfolio ID")
        if await service.get_portfolio(db, pid) is None:
            raise HTTPException(404, "Portfolio not found")
        holdings = await service.import_positions(db, pid, body.positions)
        await service.recalculate_portfolio_aggregates(db, pid)
        await db.commit()
        return [h.to_dict() for h in holdings]


@router.post("/{portfolio_id}/holdings/{holding_id}/sell")
async def sell_holding(portfolio_id: str, holding_id: str, body: SellRequest):
    async for db in get_db():
        pid, hid = _uuid(portfolio_id, "portfolio ID"), _uuid(holding_id, "holding ID")
        holding = await service.get_holding(db, hid)
        if holding is None or holding.portfolio_id != pid:
            raise HTTPException(404, "Holding not found")
        try:
            activity = await service.record_sell(db, pid, holding.ticker, body.quantity, body.price, body.description)
        except ValueError as e:
            raise HTTPException(400, str(e))
        await service.recalculate_portfolio_aggregates(db, pid)
        await db.commit()
        return activity.to_dict()


@router.delete("/{portfolio_id}/holdings/{holding_id}")
async def remove_holding(portfolio_id: str, holding_id: str, price: Optional[float] = None):
    async for db in get_db():
        pid, hid = _uuid(portfolio_id, "portfolio ID"), _uuid(holding_id, "holding ID")
        activity = await service.remove_holding(db, pid, hid, price=price)
        if activity is None:
            raise HTTPException(404, "Holding not found or already closed")
        await service.recalculate_portfolio_aggregates(db, pid)
        await db.commit()
        return activity.to_dict()


@router.get("/{portfolio_id}/holdings/{holding_id}/intelligence")
async def get_holding_intelligence(portfolio_id: str, holding_id: str):
    async for db in get_db():
        hid = _uuid(holding_id, "holding ID")
        holding = await service.get_holding(db, hid)
        if holding is None or str(holding.portfolio_id) != portfolio_id:
            raise HTTPException(404, "Holding not found")
        payload = await intelligence.build_holding_intelligence(db, holding)
        await db.commit()
        return payload


@router.get("/{portfolio_id}/activity")
async def list_activity(portfolio_id: str, limit: int = Query(50, ge=1, le=500)):
    from sqlalchemy import select
    from app.models.portfolio import PortfolioActivity

    async for db in get_db():
        pid = _uuid(portfolio_id, "portfolio ID")
        result = await db.execute(
            select(PortfolioActivity)
            .where(PortfolioActivity.portfolio_id == pid)
            .order_by(PortfolioActivity.created_at.desc())
            .limit(limit)
        )
        return [a.to_dict() for a in result.scalars().all()]


# ── Summary + Health ──────────────────────────────────────────────────────

@router.get("/{portfolio_id}/summary")
async def get_daily_summary(portfolio_id: str, refresh_intelligence: bool = True):
    async for db in get_db():
        pid = _uuid(portfolio_id, "portfolio ID")
        result = await summary_mod.generate_daily_summary(db, pid, refresh_intelligence=refresh_intelligence)
        if result is None:
            raise HTTPException(404, "Portfolio not found")
        await db.commit()
        return result


@router.get("/{portfolio_id}/health")
async def get_portfolio_health(portfolio_id: str):
    async for db in get_db():
        pid = _uuid(portfolio_id, "portfolio ID")
        portfolio = await service.get_portfolio(db, pid)
        if portfolio is None:
            raise HTTPException(404, "Portfolio not found")

        holdings = await service.get_holdings(db, pid, status="open")
        concentration = service.calculate_concentration(holdings)

        scored = [h for h in holdings if h.health_score is not None]
        avg_health = round(sum(h.health_score for h in scored) / len(scored), 1) if scored else None

        return {
            "portfolio_id": portfolio_id,
            "average_health_score": avg_health,
            "concentration": concentration,
            "holdings": sorted(
                [{"ticker": h.ticker, "health_score": h.health_score, "risk_score": h.risk_score,
                  "sentiment_score": h.sentiment_score, "weight_pct": next(
                      (a["weight_pct"] for a in service.calculate_allocation(holdings) if a["ticker"] == h.ticker), 0.0
                  )} for h in holdings],
                key=lambda r: (r["health_score"] if r["health_score"] is not None else 999),
            ),
        }


# ── Watchlists ────────────────────────────────────────────────────────────

@watchlist_router.post("", status_code=201)
async def create_watchlist(body: CreateWatchlistRequest):
    import json
    async for db in get_db():
        watchlist = Watchlist(name=body.name, description=body.description, tickers=json.dumps(body.tickers))
        db.add(watchlist)
        await db.commit()
        await db.refresh(watchlist)
        return watchlist.to_dict()


@watchlist_router.get("")
async def list_watchlists():
    from sqlalchemy import select
    async for db in get_db():
        result = await db.execute(select(Watchlist).order_by(Watchlist.updated_at.desc()))
        return [w.to_dict() for w in result.scalars().all()]


@watchlist_router.get("/{watchlist_id}")
async def get_watchlist(watchlist_id: str):
    from sqlalchemy import select
    async for db in get_db():
        wid = _uuid(watchlist_id, "watchlist ID")
        result = await db.execute(select(Watchlist).where(Watchlist.id == wid))
        watchlist = result.scalar_one_or_none()
        if watchlist is None:
            raise HTTPException(404, "Watchlist not found")
        return watchlist.to_dict()


@watchlist_router.patch("/{watchlist_id}")
async def update_watchlist(watchlist_id: str, body: UpdateWatchlistRequest):
    import json
    from datetime import datetime, timezone
    from sqlalchemy import select
    async for db in get_db():
        wid = _uuid(watchlist_id, "watchlist ID")
        result = await db.execute(select(Watchlist).where(Watchlist.id == wid))
        watchlist = result.scalar_one_or_none()
        if watchlist is None:
            raise HTTPException(404, "Watchlist not found")
        if body.name is not None:
            watchlist.name = body.name
        if body.description is not None:
            watchlist.description = body.description
        if body.tickers is not None:
            watchlist.tickers = json.dumps(body.tickers)
        watchlist.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(watchlist)
        return watchlist.to_dict()


@watchlist_router.delete("/{watchlist_id}", status_code=204)
async def delete_watchlist(watchlist_id: str):
    from sqlalchemy import select
    async for db in get_db():
        wid = _uuid(watchlist_id, "watchlist ID")
        result = await db.execute(select(Watchlist).where(Watchlist.id == wid))
        watchlist = result.scalar_one_or_none()
        if watchlist is None:
            raise HTTPException(404, "Watchlist not found")
        await db.delete(watchlist)
        await db.commit()
