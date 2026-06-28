"""
Tavily Search API — cross-validation and deep research layer.
Tavily's AI-generated answers are used to validate You.com findings.
Agreement between sources raises confidence; disagreement lowers it.
Gracefully degrades when API key is missing.
"""
import asyncio
import httpx
from app.core.config import get_settings
from app.core.cache import cache_get, cache_set


async def _search(query: str, max_results: int = 5, depth: str = "advanced") -> dict:
    settings = get_settings()
    if not settings.tavily_api_key:
        return {"results": [], "answer": None, "source": "tavily", "available": False, "query": query}

    cache_key = f"tavily:{query[:80]}:{max_results}"
    if cached := cache_get(cache_key):
        return cached

    payload = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "search_depth": depth,
        "include_answer": True,
        "include_raw_content": False,
        "max_results": max_results,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post("https://api.tavily.com/search", json=payload)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return {"results": [], "answer": None, "source": "tavily", "available": True, "error": str(e), "query": query}

    results = [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("content", "")[:400],
            "score": item.get("score", 0),
            "source": "tavily",
        }
        for item in (data.get("results", []) or [])[:max_results]
    ]

    output = {
        "results": results,
        "answer": data.get("answer"),
        "source": "tavily",
        "available": True,
        "query": query,
        "count": len(results),
    }
    cache_set(cache_key, output, ttl=300)
    return output


async def research_query(tickers: list[str], query: str, themes: list[str] | None = None) -> dict:
    """Parallel Tavily searches for cross-validation."""
    searches, labels = [], []

    for ticker in (tickers or [])[:2]:
        searches.append(_search(f"{ticker} investment thesis bull bear analysis", max_results=3))
        labels.append(f"{ticker}_thesis")

    for theme in (themes or [])[:2]:
        searches.append(_search(f"{theme} sector outlook market opportunities risks", max_results=3))
        labels.append(f"theme_{theme}")

    if not searches:
        searches.append(_search(query, max_results=5))
        labels.append("general")

    results_list = await asyncio.gather(*searches, return_exceptions=True)

    combined, answers = [], []
    for label, res in zip(labels, results_list):
        if isinstance(res, Exception):
            continue
        for item in res.get("results", []):
            combined.append({**item, "label": label})
        if res.get("answer"):
            answers.append({"label": label, "answer": res["answer"]})

    return {
        "source": "tavily",
        "results": combined,
        "answers": answers,
        "count": len(combined),
        "tickers": tickers,
    }
