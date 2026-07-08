"""
Base helpers for all agents.
Direct calls to provider functions — no inter-service HTTP.
"""
from typing import Optional
from app.core.config import get_settings
from app.core import llm as _llm
from app.providers import market as mkt
from app.documents.evidence.models import EvidencePack
from app.memory.models import MemoryPack

settings = get_settings()

# Re-exported from app.core.llm (moved there in Milestone 2 so
# app/documents/evidence/ can share it too) — same names, same behavior,
# every existing `from app.agents.base import llm_json` caller is unaffected.
get_client = _llm.get_client
get_model = _llm.get_model
llm_json = _llm.llm_json


# Re-export market data helpers for agents to import from one place
get_quote = mkt.get_quote
get_candles = mkt.get_candles
get_news = mkt.get_news
get_fundamentals = mkt.get_fundamentals
get_analyst = mkt.get_analyst


async def search_evidence(query: str, ticker: Optional[str] = None, top_k: int = 8, **kwargs) -> EvidencePack:
    """Evidence-first retrieval over ingested documents
    (app/documents/retrieval/, app/documents/evidence/), ready for agents to
    call instead of reading full documents. A thin session-owning wrapper,
    not a bare re-export like the market-data helpers above —
    retrieval_service.search() needs a DB session, which agents don't
    otherwise carry.

    Returns an EvidencePack (app/documents/evidence/models.py) — evidence,
    LLM-synthesized claims, deduped citations, an overall confidence score,
    and a conflict summary, not a flat list of chunk dicts (that was the
    Milestone 1 shape; see app/documents/retrieval/service.py's
    search_chunks() if the old flat shape is ever needed instead).

    No agent calls this yet — wiring the 12 agents' prompts to use it is a
    separate follow-up, not part of this milestone."""
    from app.core.database import SessionLocal
    from app.documents.retrieval import service as retrieval_service

    async with SessionLocal() as db:
        return await retrieval_service.search(db, query, ticker=ticker, top_k=top_k, **kwargs)


async def recall_memory(
    query: str, workspace_id: Optional[str] = None, ticker: Optional[str] = None, top_k: int = 6,
) -> MemoryPack:
    """Persistent cross-session research memory (app/memory/), queried
    before agents call their LLMs — see app/agents/supervisor.py's
    gather_memory() step, which populates AgentState.memory_context by
    calling this once per research run. A thin session-owning wrapper for
    the same reason search_evidence() above is: agents don't carry a DB
    session.

    Returns a MemoryPack (app/memory/models.py) — ranked facts, beliefs,
    investment decisions, and open/resolved questions from prior sessions,
    each with a confidence and similarity score. Empty (not an error) when
    neither workspace_id nor ticker is given, or when nothing relevant is
    on file yet."""
    from app.memory.service import recall_for_agent

    return await recall_for_agent(query, workspace_id=workspace_id, ticker=ticker, top_k=top_k)


def format_memory_for_agents(state, max_items: int = 4) -> str:
    """Renders AgentState.memory_context (populated once per run by
    app.agents.supervisor.gather_memory) into a short text block agents can
    fold into their LLM prompt — the memory-recall counterpart to
    app.providers.evidence.format_for_agents. Returns "" when there's
    nothing relevant on file yet, so callers can safely inline it without an
    extra guard."""
    context = getattr(state, "memory_context", None)
    if not context:
        return ""

    lines: list[str] = []
    workspace_pack = context.get("workspace")
    if workspace_pack and workspace_pack.get("items"):
        lines.append("=== Prior Research Memory (this workspace) ===")
        for item in workspace_pack["items"][:max_items]:
            lines.append(f"• [{item['memory_type']}] {item['content'][:200]} (confidence={item['confidence']:.2f})")

    for ticker, pack in (context.get("company") or {}).items():
        items = pack.get("items") or []
        if not items:
            continue
        lines.append(f"=== Prior Company Memory ({ticker}) ===")
        for item in items[:max_items]:
            lines.append(f"• [{item['memory_type']}] {item['content'][:200]} (confidence={item['confidence']:.2f})")

    return "\n".join(lines)
