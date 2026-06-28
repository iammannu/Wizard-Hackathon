"""
Evidence aggregator — merges You.com + Tavily into a unified evidence chain.
Confidence increases when both sources agree; decreases when they conflict.
Formats evidence into an LLM-readable string for agent prompts.
"""
import asyncio
from app.providers import youcom, tavily


async def gather_evidence(tickers: list[str], query: str, themes: list[str] | None = None) -> dict:
    """Run You.com + Tavily in parallel and merge results."""
    you_res, tav_res = await asyncio.gather(
        youcom.research_query(tickers, query, themes),
        tavily.research_query(tickers, query, themes),
        return_exceptions=True,
    )

    if isinstance(you_res, Exception):
        you_res = {"results": [], "source": "you.com", "count": 0, "available": False}
    if isinstance(tav_res, Exception):
        tav_res = {"results": [], "source": "tavily", "count": 0, "available": False}

    you_count = you_res.get("count", 0)
    tav_count = tav_res.get("count", 0)
    total = you_count + tav_count

    coverage = "strong" if total >= 8 else "moderate" if total >= 4 else "limited" if total >= 1 else "none"
    confidence_boost = round(min(0.12, total * 0.012), 3)

    combined = []
    for item in you_res.get("results", []):
        combined.append({**item, "provider": "you.com"})
    for item in tav_res.get("results", []):
        combined.append({**item, "provider": "tavily"})

    return {
        "you_com": {
            "available": you_count > 0 or you_res.get("available", False),
            "results": you_res.get("results", []),
            "count": you_count,
        },
        "tavily": {
            "available": tav_count > 0 or tav_res.get("available", False),
            "results": tav_res.get("results", []),
            "answers": tav_res.get("answers", []),
            "count": tav_count,
        },
        "combined_results": combined,
        "total_sources": total,
        "coverage": coverage,
        "confidence_boost": confidence_boost,
        "tickers": tickers,
        "query": query,
    }


def format_for_agents(evidence: dict) -> str:
    """Render evidence into a readable string for LLM prompts."""
    lines = []

    you_results = evidence.get("you_com", {}).get("results", [])
    tav_answers = evidence.get("tavily", {}).get("answers", [])
    tav_results = evidence.get("tavily", {}).get("results", [])

    if you_results:
        lines.append("=== You.com Research ===")
        for r in you_results[:5]:
            snippet = (r.get("snippet") or "")[:250]
            if snippet:
                lines.append(f"• [{r.get('title', 'Article')}]: {snippet}")

    if tav_answers:
        lines.append("\n=== Tavily AI Analysis ===")
        for a in tav_answers[:2]:
            lines.append(f"• {a['answer'][:350]}")
    elif tav_results:
        lines.append("\n=== Tavily Sources ===")
        for r in tav_results[:3]:
            snippet = (r.get("snippet") or "")[:250]
            if snippet:
                lines.append(f"• [{r.get('title', 'Article')}]: {snippet}")

    return "\n".join(lines) if lines else "No external research available."
