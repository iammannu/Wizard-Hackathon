"""
Memory router — Milestone 3 read-only surface.

Full CRUD/management for memory (edit/retract a memory item, etc.) is
Milestone 9's job ("Memory APIs"); this milestone only needs enough surface
to inspect what's been consolidated and to manually exercise semantic
recall — the same read-only-first approach Milestone 2 took with
POST /retrieval/query before Milestone 9 rounds out the rest of the surface.
"""
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.core.database import get_db
from app.models.memory import ConversationMemory, WorkspaceMemory, CompanyMemory, ThesisMemory
from app.memory import retriever

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


class RecallRequest(BaseModel):
    query: str
    workspace_id: Optional[str] = None
    ticker: Optional[str] = None
    top_k: int = 6


@router.post("/recall")
async def recall_memory(body: RecallRequest):
    """Semantic memory recall — the same function agents call
    (app.agents.base.recall_memory) before hitting their LLMs, exposed here
    for manual inspection/debugging."""
    if not body.workspace_id and not body.ticker:
        raise HTTPException(400, "At least one of workspace_id or ticker is required")

    async for db in get_db():
        pack = await retriever.recall(
            db, body.query, workspace_id=body.workspace_id, ticker=body.ticker, top_k=body.top_k
        )
        return pack.model_dump(mode="json")


@router.get("/workspace/{workspace_id}")
async def list_workspace_memory(
    workspace_id: str,
    memory_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
):
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(400, "Invalid workspace ID")

    async for db in get_db():
        query = select(WorkspaceMemory).where(WorkspaceMemory.workspace_id == ws_uuid)
        if memory_type:
            query = query.where(WorkspaceMemory.memory_type == memory_type)
        if status:
            query = query.where(WorkspaceMemory.status == status)
        query = query.order_by(WorkspaceMemory.updated_at.desc()).limit(limit)

        result = await db.execute(query)
        rows = result.scalars().all()
        return [r.to_dict() for r in rows]


@router.get("/company/{ticker}")
async def list_company_memory(ticker: str, memory_type: Optional[str] = None, limit: int = Query(100, ge=1, le=500)):
    async for db in get_db():
        query = select(CompanyMemory).where(CompanyMemory.ticker == ticker.upper())
        if memory_type:
            query = query.where(CompanyMemory.memory_type == memory_type)
        query = query.order_by(CompanyMemory.last_confirmed_at.desc()).limit(limit)

        result = await db.execute(query)
        rows = result.scalars().all()
        return [r.to_dict() for r in rows]


@router.get("/workspace/{workspace_id}/conversations")
async def list_conversation_memory(workspace_id: str, limit: int = Query(20, ge=1, le=200)):
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(400, "Invalid workspace ID")

    async for db in get_db():
        result = await db.execute(
            select(ConversationMemory)
            .where(ConversationMemory.workspace_id == ws_uuid)
            .order_by(ConversationMemory.created_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
        return [r.to_dict() for r in rows]


@router.get("/workspace/{workspace_id}/decisions")
async def list_thesis_memory(workspace_id: str, memory_type: Optional[str] = None, limit: int = Query(50, ge=1, le=200)):
    """ThesisMemory rows — confirmed/refuted beliefs and investment decisions."""
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(400, "Invalid workspace ID")

    async for db in get_db():
        query = select(ThesisMemory).where(ThesisMemory.workspace_id == ws_uuid)
        if memory_type:
            query = query.where(ThesisMemory.memory_type == memory_type)
        query = query.order_by(ThesisMemory.created_at.desc()).limit(limit)

        result = await db.execute(query)
        rows = result.scalars().all()
        return [r.to_dict() for r in rows]
