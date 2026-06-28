from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.agents.base import llm_json
import json

router = APIRouter(prefix="/api/v1/screener", tags=["screener"])

# Demo stock universe — swap with a real DB query when ready
STOCKS = [
    {"ticker": "AAPL", "name": "Apple", "sector": "Technology", "pe_ratio": 28, "ps_ratio": 7, "net_margin": 0.26, "revenue_growth": 0.06, "market_cap": 3_200_000_000_000, "beta": 1.2, "debt_to_equity": 1.5, "roe": 1.6},
    {"ticker": "MSFT", "name": "Microsoft", "sector": "Technology", "pe_ratio": 32, "ps_ratio": 12, "net_margin": 0.36, "revenue_growth": 0.16, "market_cap": 3_000_000_000_000, "beta": 0.9, "debt_to_equity": 0.4, "roe": 0.42},
    {"ticker": "NVDA", "name": "Nvidia", "sector": "Technology", "pe_ratio": 50, "ps_ratio": 20, "net_margin": 0.55, "revenue_growth": 1.22, "market_cap": 2_800_000_000_000, "beta": 1.7, "debt_to_equity": 0.4, "roe": 1.2},
    {"ticker": "GOOGL", "name": "Alphabet", "sector": "Communication Services", "pe_ratio": 21, "ps_ratio": 6, "net_margin": 0.28, "revenue_growth": 0.15, "market_cap": 2_100_000_000_000, "beta": 1.0, "debt_to_equity": 0.1, "roe": 0.30},
    {"ticker": "META", "name": "Meta", "sector": "Communication Services", "pe_ratio": 24, "ps_ratio": 9, "net_margin": 0.38, "revenue_growth": 0.22, "market_cap": 1_500_000_000_000, "beta": 1.3, "debt_to_equity": 0.1, "roe": 0.35},
    {"ticker": "AMZN", "name": "Amazon", "sector": "Consumer Discretionary", "pe_ratio": 40, "ps_ratio": 3, "net_margin": 0.09, "revenue_growth": 0.11, "market_cap": 2_000_000_000_000, "beta": 1.1, "debt_to_equity": 0.6, "roe": 0.19},
    {"ticker": "JPM", "name": "JPMorgan", "sector": "Financials", "pe_ratio": 13, "ps_ratio": 3, "net_margin": 0.30, "revenue_growth": 0.12, "market_cap": 650_000_000_000, "beta": 1.0, "debt_to_equity": 1.3, "roe": 0.17},
    {"ticker": "JNJ", "name": "Johnson & Johnson", "sector": "Healthcare", "pe_ratio": 15, "ps_ratio": 4, "net_margin": 0.24, "revenue_growth": 0.04, "market_cap": 380_000_000_000, "beta": 0.6, "debt_to_equity": 0.5, "roe": 0.25},
    {"ticker": "XOM", "name": "ExxonMobil", "sector": "Energy", "pe_ratio": 14, "ps_ratio": 1, "net_margin": 0.10, "revenue_growth": -0.05, "market_cap": 460_000_000_000, "beta": 0.8, "debt_to_equity": 0.2, "roe": 0.14},
    {"ticker": "TSLA", "name": "Tesla", "sector": "Consumer Discretionary", "pe_ratio": 65, "ps_ratio": 8, "net_margin": 0.08, "revenue_growth": 0.01, "market_cap": 900_000_000_000, "beta": 2.3, "debt_to_equity": 0.1, "roe": 0.14},
]

OPS = {"gt": lambda a, b: a > b, "gte": lambda a, b: a >= b, "lt": lambda a, b: a < b, "lte": lambda a, b: a <= b, "eq": lambda a, b: a == b, "in": lambda a, b: a in b}


def apply_filters(stocks, filters):
    result = []
    for s in stocks:
        if all(OPS.get(f["operator"], lambda a, b: True)(s.get(f["field"], None), f["value"])
               for f in filters if s.get(f["field"]) is not None):
            result.append(s)
    return result


class ScreenerRequest(BaseModel):
    query: str
    limit: int = 20


@router.post("/screen")
async def screen(body: ScreenerRequest):
    """Natural language screener — LLM parses query to filters, then applies them."""
    parsed = await llm_json(
        system="""Parse this stock screening query into filters. Return JSON:
{"filters":[{"field":"pe_ratio"|"ps_ratio"|"net_margin"|"revenue_growth"|"beta"|"debt_to_equity"|"roe","operator":"gt"|"gte"|"lt"|"lte"|"eq","value":number}],"explanation":"what you extracted"}

Available fields: pe_ratio, ps_ratio, net_margin (0-1), revenue_growth (0-1), beta, debt_to_equity, roe""",
        user=body.query,
        fast=True,
    )

    filters = parsed.get("filters", [])
    results = apply_filters(STOCKS, filters)[:body.limit]

    return {
        "query": body.query,
        "filters_applied": filters,
        "explanation": parsed.get("explanation", ""),
        "results": results,
        "count": len(results),
    }
