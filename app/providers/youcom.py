"""
You.com Web Search API — primary research evidence engine.
API: https://api.you.com/v1/search
Response: {"results": {"web": [...], "news": [...]}, "metadata": {...}}
"""
import asyncio
import httpx
from app.core.config import get_settings
from app.core.cache import cache_get, cache_set

_BASE = "https://api.you.com/v1/search"


async def _search(query: str, num_results: int = 5, search_type: str = "web") -> dict:
    settings = get_settings()
    if not settings.youcom_api_key:
        return {"results": [], "source": "you.com", "available": False, "query": query}

    cache_key = f"youcom:{search_type}:{query[:80]}"
    if cached := cache_get(cache_key):
        return cached

    headers = {"X-API-Key": settings.youcom_api_key}
    params = {"query": query, "num_web_results": num_results}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(_BASE, headers=headers, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return {"results": [], "source": "you.com", "available": True, "error": str(e), "query": query}

    raw = data.get("results", {})
    results = []

    if search_type == "news":
        for item in (raw.get("news", []) or [])[:num_results]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
                "age": item.get("page_age", ""),
                "source": "you.com/news",
            })
    else:
        for item in (raw.get("web", []) or [])[:num_results]:
            snippet = item.get("description", "")
            # snippets field is a list of strings on some results
            if not snippet and item.get("snippets"):
                snippet = " ".join(item["snippets"])
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": snippet,
                "source": "you.com",
            })

    output = {"results": results, "source": "you.com", "available": True, "query": query, "count": len(results)}
    cache_set(cache_key, output, ttl=300)
    return output


async def research_query(tickers: list[str], query: str, themes: list[str] | None = None) -> dict:
    """Parallel You.com searches across tickers + themes."""
    searches, labels = [], []

    for ticker in (tickers or [])[:3]:
        searches.append(_search(f"{ticker} stock analysis earnings revenue {query}", num_results=3))
        labels.append(f"{ticker}_analysis")
        searches.append(_search(f"{ticker} latest news catalyst", num_results=3, search_type="news"))
        labels.append(f"{ticker}_news")

    for theme in (themes or [])[:2]:
        searches.append(_search(f"{theme} investment trends market analysis 2025", num_results=3))
        labels.append(f"theme_{theme}")

    if not searches:
        searches.append(_search(query, num_results=5))
        labels.append("general")

    results_list = await asyncio.gather(*searches, return_exceptions=True)

    combined = []
    available = False
    for label, res in zip(labels, results_list):
        if isinstance(res, Exception):
            continue
        if res.get("available"):
            available = True
        for item in res.get("results", []):
            combined.append({**item, "label": label})

    return {
        "source": "you.com",
        "available": available,
        "results": combined,
        "count": len(combined),
        "tickers": tickers,
    }
