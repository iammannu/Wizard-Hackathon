"""
Market data — Polygon (prices/candles/news) + Finnhub (fundamentals/analyst).
In-process TTL cache replaces Redis. Same API surface as before.
"""
import httpx
from typing import Optional
from datetime import date, timedelta
from app.core.cache import cache_get, cache_set
from app.core.config import get_settings

settings = get_settings()


# ── Polygon ──────────────────────────────────────────────────────────────────

async def get_quote(ticker: str) -> Optional[dict]:
    """
    Quote via Finnhub /quote (free tier) with Polygon prev-close fallback.
    Finnhub returns: c=current, h=high, l=low, o=open, pc=prev_close, d=change, dp=change_pct
    """
    key = f"quote:{ticker}"
    if hit := cache_get(key):
        return hit

    # Finnhub real-time quote (free tier)
    if settings.finnhub_api_key:
        try:
            async with httpx.AsyncClient(timeout=8.0, headers={"X-Finnhub-Token": settings.finnhub_api_key}) as client:
                r = await client.get("https://finnhub.io/api/v1/quote", params={"symbol": ticker})
                r.raise_for_status()
                d = r.json()
                if d.get("c"):
                    result = {
                        "ticker":     ticker,
                        "price":      round(d["c"], 4),
                        "open":       round(d.get("o") or 0, 4),
                        "high":       round(d.get("h") or 0, 4),
                        "low":        round(d.get("l") or 0, 4),
                        "close":      round(d["c"], 4),
                        "prev_close": round(d.get("pc") or 0, 4),
                        "volume":     0,
                        "change":     round(d.get("d") or 0, 4),
                        "change_pct": round(d.get("dp") or 0, 4),
                    }
                    cache_set(key, result, ttl=15)
                    return result
        except Exception as e:
            print(f"[finnhub] quote {ticker}: {e}")

    # Fallback: Polygon previous close (free tier endpoint)
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev",
                params={"adjusted": "true", "apiKey": settings.polygon_api_key},
            )
            r.raise_for_status()
            results = r.json().get("results", [])
            if results:
                d = results[0]
                close = d.get("c") or 0
                open_ = d.get("o") or 0
                result = {
                    "ticker":     ticker,
                    "price":      close,
                    "open":       open_,
                    "high":       d.get("h") or 0,
                    "low":        d.get("l") or 0,
                    "close":      close,
                    "prev_close": open_,
                    "volume":     d.get("v") or 0,
                    "change":     round(close - open_, 4),
                    "change_pct": round((close - open_) / open_ * 100, 4) if open_ else 0,
                }
                cache_set(key, result, ttl=60)
                return result
    except Exception as e:
        print(f"[polygon] prev-close {ticker}: {e}")

    return None


async def get_candles(ticker: str, interval: str = "1d", limit: int = 60) -> list[dict]:
    key = f"candles:{ticker}:{interval}:{limit}"
    if hit := cache_get(key):
        return hit
    multiplier_map = {"1d": (1, "day"), "1h": (1, "hour"), "1w": (1, "week")}
    mult, span = multiplier_map.get(interval, (1, "day"))
    to_date = date.today().isoformat()
    from_date = (date.today() - timedelta(days=max(limit * 2, 365))).isoformat()
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/{mult}/{span}/{from_date}/{to_date}",
                params={"adjusted": "true", "sort": "asc", "limit": limit, "apiKey": settings.polygon_api_key},
            )
            r.raise_for_status()
            candles = [
                {"time": c["t"], "open": c["o"], "high": c["h"], "low": c["l"], "close": c["c"], "volume": c["v"]}
                for c in r.json().get("results", [])
            ]
            cache_set(key, candles, ttl=300)
            return candles
    except Exception as e:
        print(f"[polygon] candles {ticker}: {e}")
        return []


async def get_news(ticker: str, limit: int = 10) -> list[dict]:
    key = f"news:{ticker}"
    if hit := cache_get(key):
        return hit
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                "https://api.polygon.io/v2/reference/news",
                params={"ticker": ticker, "limit": limit, "order": "desc", "apiKey": settings.polygon_api_key},
            )
            r.raise_for_status()
            results = r.json().get("results", [])
            cache_set(key, results, ttl=300)
            return results
    except Exception as e:
        print(f"[polygon] news {ticker}: {e}")
        return []


# ── Finnhub ───────────────────────────────────────────────────────────────────

async def get_fundamentals(ticker: str) -> Optional[dict]:
    key = f"fundamentals:{ticker}"
    if hit := cache_get(key):
        return hit
    try:
        async with httpx.AsyncClient(timeout=8.0, headers={"X-Finnhub-Token": settings.finnhub_api_key}) as client:
            r = await client.get("https://finnhub.io/api/v1/stock/metric", params={"symbol": ticker, "metric": "all"})
            r.raise_for_status()
            m = r.json().get("metric", {})
            result = {
                "ticker": ticker,
                "pe_ratio": m.get("peTTM"),
                "forward_pe": m.get("peForwardTTM"),
                "ps_ratio": m.get("psTTM"),
                "pb_ratio": m.get("pbAnnual"),
                "ev_ebitda": m.get("evEbitdaTTM"),
                "gross_margin": m.get("grossMarginTTM"),
                "operating_margin": m.get("operatingMarginTTM"),
                "net_margin": m.get("netProfitMarginTTM"),
                "roe": m.get("roeTTM"),
                "roa": m.get("roaTTM"),
                "debt_to_equity": m.get("totalDebt/totalEquityAnnual"),
                "current_ratio": m.get("currentRatioAnnual"),
                "revenue_growth_yoy": m.get("revenueGrowthTTMYoy"),
                "earnings_growth_yoy": m.get("epsGrowthTTMYoy"),
                "beta": m.get("beta"),
                "52w_high": m.get("52WeekHigh"),
                "52w_low": m.get("52WeekLow"),
                "dividend_yield": m.get("dividendYieldIndicatedAnnual"),
            }
            cache_set(key, result, ttl=3600 * 4)
            return result
    except Exception as e:
        print(f"[finnhub] fundamentals {ticker}: {e}")
        return None


async def get_analyst(ticker: str) -> Optional[dict]:
    key = f"analyst:{ticker}"
    if hit := cache_get(key):
        return hit
    try:
        async with httpx.AsyncClient(timeout=8.0, headers={"X-Finnhub-Token": settings.finnhub_api_key}) as client:
            r = await client.get("https://finnhub.io/api/v1/stock/recommendation", params={"symbol": ticker})
            r.raise_for_status()
            results = r.json()
            if results:
                latest = results[0]
                total = sum(latest.get(k, 0) for k in ["strongBuy", "buy", "hold", "sell", "strongSell"])
                bullish = latest.get("strongBuy", 0) + latest.get("buy", 0)
                consensus = "buy" if total and bullish / total > 0.5 else "hold" if total and latest.get("hold", 0) / total > 0.4 else "sell"
                result = {"ticker": ticker, "consensus": consensus, "detail": latest}
                cache_set(key, result, ttl=3600 * 12)
                return result
        return None
    except Exception as e:
        print(f"[finnhub] analyst {ticker}: {e}")
        return None