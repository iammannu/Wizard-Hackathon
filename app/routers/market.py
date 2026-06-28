from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.providers.market import get_quote, get_candles, get_fundamentals, get_analyst, get_news

router = APIRouter(prefix="/api/v1/market", tags=["market"])


@router.get("/stocks/{ticker}")
async def quote(ticker: str):
    data = await get_quote(ticker.upper())
    if not data:
        raise HTTPException(404, f"No data for {ticker}")
    return data


@router.get("/stocks/{ticker}/candles")
async def candles(ticker: str, interval: str = "1d", limit: int = Query(100, le=500)):
    return {"ticker": ticker.upper(), "candles": await get_candles(ticker.upper(), interval, limit)}


@router.get("/stocks/{ticker}/fundamentals")
async def fundamentals(ticker: str):
    data = await get_fundamentals(ticker.upper())
    if not data:
        raise HTTPException(404, f"No fundamentals for {ticker}")
    return data


@router.get("/stocks/{ticker}/analyst")
async def analyst(ticker: str):
    data = await get_analyst(ticker.upper())
    if not data:
        raise HTTPException(404, "No analyst data")
    return data


@router.get("/stocks/{ticker}/news")
async def news(ticker: str, limit: int = Query(10, le=50)):
    return {"ticker": ticker.upper(), "news": await get_news(ticker.upper(), limit)}
