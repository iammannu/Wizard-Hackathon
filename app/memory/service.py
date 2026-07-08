"""
Memory service — the one place that knows how a completed research session
(AgentState + its ThesisVersion, when versioning succeeded) becomes
ConversationMemory + WorkspaceMemory + CompanyMemory + ThesisMemory rows,
and the session-owning entry point agents use to recall memory without
carrying a DB session themselves (mirrors app.agents.base.search_evidence's
relationship to app.documents.retrieval.service.search).

Why this shape (mirrors app/thesis/versioner.py's own module docstring):
  Keeping the full extract -> consolidate -> promote assembly in one
  function makes memory testable independent of the HTTP/SSE layer, and
  gives app/routers/workspaces.py a single call to make after
  create_thesis_version() — consistent with how that same router already
  treats thesis versioning as one atomic, isolable unit of work.
"""
import json
import logging
import uuid
from typing import Optional

from app.agents.state import AgentState
from app.memory import consolidator, retriever
from app.memory.extractor import extract_memory_candidates
from app.memory.models import MemoryPack
from app.models.memory import ConversationMemory

logger = logging.getLogger(__name__)


async def consolidate_research(
    db,
    workspace_id: uuid.UUID,
    research_id: Optional[uuid.UUID],
    state: AgentState,
    thesis_version=None,  # Optional[ThesisVersion]
) -> dict:
    """Extracts and consolidates memory from one completed research session.
    Does not commit — caller owns the transaction boundary, same convention
    as create_thesis_version(). Returns a summary dict for logging/SSE."""
    candidates = await extract_memory_candidates(state, thesis_version)

    db.add(ConversationMemory(
        workspace_id=workspace_id,
        research_id=research_id,
        query=state.query,
        summary=(state.explanation or state.recommendation or "")[:500],
        extracted_items=json.dumps([c.model_dump(mode="json") for c in candidates]),
        item_count=len(candidates),
    ))

    affected_rows = await consolidator.consolidate_workspace_memory(
        db, workspace_id, candidates, research_id=research_id
    )

    company_promotions = 0
    for ticker in (state.tickers or []):
        ticker_rows = [r for r in affected_rows if ticker in r.tickers_list()]
        if ticker_rows:
            await consolidator.promote_to_company_memory(db, ticker, workspace_id, ticker_rows)
            company_promotions += len(ticker_rows)

    thesis_memories_created = 0
    if thesis_version is not None:
        promoted_claims = await consolidator.promote_thesis_claims(db, workspace_id, thesis_version)
        await consolidator.record_investment_decision(db, workspace_id, thesis_version)
        thesis_memories_created = len(promoted_claims) + 1

    return {
        "candidates_extracted": len(candidates),
        "workspace_memory_affected": len(affected_rows),
        "company_memory_promotions": company_promotions,
        "thesis_memories_created": thesis_memories_created,
    }


async def recall_for_agent(
    query: str,
    workspace_id: Optional[str] = None,
    ticker: Optional[str] = None,
    top_k: Optional[int] = None,
) -> MemoryPack:
    """Session-owning wrapper for agents (which don't carry a DB session) —
    same pattern as app.agents.base.search_evidence()."""
    from app.core.database import SessionLocal

    async with SessionLocal() as db:
        return await retriever.recall(db, query, workspace_id=workspace_id, ticker=ticker, top_k=top_k)
