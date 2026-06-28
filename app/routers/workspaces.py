"""
Workspace router — Living Research Workspaces.
CRUD + streaming research within a persistent workspace context.
"""
import uuid
import json
import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select, update

from app.core.database import get_db
from app.models.workspace import Workspace, WorkspaceResearch
from app.agents.supervisor import run_research

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


# ── Request models ─────────────────────────────────────────────────────────────

class CreateWorkspaceRequest(BaseModel):
    title: str
    description: str = ""
    tracked_tickers: list[str] = []
    tracked_sectors: list[str] = []
    tracked_themes: list[str] = []
    icon: str = "📊"


class UpdateWorkspaceRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tracked_tickers: Optional[list[str]] = None
    tracked_sectors: Optional[list[str]] = None
    tracked_themes: Optional[list[str]] = None
    icon: Optional[str] = None


class WorkspaceResearchRequest(BaseModel):
    query: str
    depth: str = "full"


# ── Workspace CRUD ─────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_workspace(body: CreateWorkspaceRequest):
    async for db in get_db():
        ws = Workspace(
            title=body.title,
            description=body.description,
            tracked_tickers=json.dumps(body.tracked_tickers),
            tracked_sectors=json.dumps(body.tracked_sectors),
            tracked_themes=json.dumps(body.tracked_themes),
            icon=body.icon,
        )
        db.add(ws)
        await db.commit()
        await db.refresh(ws)
        return ws.to_dict()


@router.get("")
async def list_workspaces():
    async for db in get_db():
        result = await db.execute(
            select(Workspace).where(Workspace.status == "active").order_by(Workspace.updated_at.desc())
        )
        workspaces = result.scalars().all()
        return [ws.to_dict() for ws in workspaces]


@router.get("/{workspace_id}")
async def get_workspace(workspace_id: str):
    async for db in get_db():
        ws = await _get_ws(db, workspace_id)
        data = ws.to_dict()

        # Attach research history (latest 10)
        result = await db.execute(
            select(WorkspaceResearch)
            .where(WorkspaceResearch.workspace_id == ws.id)
            .order_by(WorkspaceResearch.created_at.desc())
            .limit(10)
        )
        history = result.scalars().all()
        data["research_history"] = [h.to_dict() for h in history]

        # Attach latest research detail
        if history:
            latest = history[0].result_dict()
            data["latest_research"] = latest

        return data


@router.patch("/{workspace_id}")
async def update_workspace(workspace_id: str, body: UpdateWorkspaceRequest):
    async for db in get_db():
        ws = await _get_ws(db, workspace_id)

        if body.title is not None:        ws.title = body.title
        if body.description is not None:  ws.description = body.description
        if body.tracked_tickers is not None: ws.tracked_tickers = json.dumps(body.tracked_tickers)
        if body.tracked_sectors is not None: ws.tracked_sectors = json.dumps(body.tracked_sectors)
        if body.tracked_themes is not None:  ws.tracked_themes = json.dumps(body.tracked_themes)
        if body.icon is not None:         ws.icon = body.icon
        ws.updated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(ws)
        return ws.to_dict()


@router.delete("/{workspace_id}", status_code=204)
async def archive_workspace(workspace_id: str):
    async for db in get_db():
        ws = await _get_ws(db, workspace_id)
        ws.status = "archived"
        ws.updated_at = datetime.now(timezone.utc)
        await db.commit()


# ── Workspace Research ─────────────────────────────────────────────────────────

@router.post("/{workspace_id}/research")
async def workspace_research_stream(workspace_id: str, body: WorkspaceResearchRequest):
    """SSE streaming research within a workspace context — real-time via asyncio.Queue."""

    async def generate():
        session_id = str(uuid.uuid4())
        yield f"data: {json.dumps({'type': 'session_start', 'session_id': session_id, 'workspace_id': workspace_id})}\n\n"

        # Load workspace tickers + themes before starting background task
        tickers: list = []
        themes: list = []
        try:
            async for db in get_db():
                try:
                    ws = await _get_ws(db, workspace_id)
                    tickers = ws.tickers_list()
                    themes = ws.themes_list()
                except HTTPException:
                    pass
                break
        except Exception:
            pass

        queue: asyncio.Queue = asyncio.Queue()
        state_holder: dict = {}

        async def on_event(event: dict):
            await queue.put(event)

        async def run():
            try:
                state_holder["state"] = await run_research(
                    query=body.query,
                    tickers=tickers or None,
                    depth=body.depth,
                    workspace_id=workspace_id,
                    themes=themes,
                    on_event=on_event,
                )
            except Exception as e:
                await queue.put({"type": "error", "message": str(e)})
            finally:
                await queue.put(None)  # sentinel

        asyncio.create_task(run())

        # Forward events as they arrive
        while True:
            event = await queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"

        if "state" in state_holder:
            state = state_holder["state"]
            agent_outputs = {
                name: getattr(state, f"{name}_output")
                for name in state.active_agents
                if getattr(state, f"{name}_output", None)
            }
            payload = {
                "type": "result",
                "session_id": session_id,
                "workspace_id": workspace_id,
                "intent": state.intent,
                "tickers": state.tickers,
                "agents_activated": state.active_agents,
                "confidence": state.confidence,
                "confidence_breakdown": state.confidence_breakdown,
                "conflicts": state.conflicts,
                "recommendation": state.recommendation,
                "explanation": state.explanation,
                "bull_case": state.bull_case,
                "bear_case": state.bear_case,
                "key_risks": state.key_risks,
                "invalidation_conditions": state.invalidation_conditions,
                "known_unknowns": state.known_unknowns,
                "agent_outputs": agent_outputs,
                "evidence": {
                    "you_com": state.evidence.get("you_com", {}) if state.evidence else {},
                    "tavily": state.evidence.get("tavily", {}) if state.evidence else {},
                    "total_sources": (state.evidence or {}).get("total_sources", 0),
                    "coverage": (state.evidence or {}).get("coverage", "none"),
                },
                "debate": state.debate,
                "scenarios": state.scenarios,
                "knowledge_graph": state.knowledge_graph,
            }
            yield f"data: {json.dumps(payload)}\n\n"

            # Persist to DB after payload is sent
            await _save_research(workspace_id, body.query, state, payload)

            yield f"data: {json.dumps({'type': 'complete', 'session_id': session_id})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{workspace_id}/research/sync")
async def workspace_research_sync(workspace_id: str, body: WorkspaceResearchRequest):
    """Non-streaming workspace research."""
    async for db in get_db():
        try:
            ws = await _get_ws(db, workspace_id)
            tickers = ws.tickers_list()
            themes = ws.themes_list()
        except HTTPException:
            tickers, themes = [], []
        break

    try:
        state = await run_research(
            query=body.query,
            tickers=tickers or None,
            depth=body.depth,
            workspace_id=workspace_id,
            themes=themes,
        )

        agent_outputs = {
            name: getattr(state, f"{name}_output")
            for name in state.active_agents
            if getattr(state, f"{name}_output", None)
        }

        result = {
            "session_id": str(uuid.uuid4()),
            "workspace_id": workspace_id,
            "query": body.query,
            "intent": state.intent,
            "tickers": state.tickers,
            "agents_activated": state.active_agents,
            "confidence": state.confidence,
            "confidence_breakdown": state.confidence_breakdown,
            "conflicts": state.conflicts,
            "recommendation": state.recommendation,
            "explanation": state.explanation,
            "bull_case": state.bull_case,
            "bear_case": state.bear_case,
            "key_risks": state.key_risks,
            "invalidation_conditions": state.invalidation_conditions,
            "known_unknowns": state.known_unknowns,
            "agent_outputs": agent_outputs,
            "evidence": {
                "you_com": state.evidence.get("you_com", {}) if state.evidence else {},
                "tavily": state.evidence.get("tavily", {}) if state.evidence else {},
                "total_sources": (state.evidence or {}).get("total_sources", 0),
                "coverage": (state.evidence or {}).get("coverage", "none"),
            },
            "debate": state.debate,
            "scenarios": state.scenarios,
            "knowledge_graph": state.knowledge_graph,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        await _save_research(workspace_id, body.query, state, result)
        return result

    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/{workspace_id}/history")
async def get_research_history(workspace_id: str):
    async for db in get_db():
        await _get_ws(db, workspace_id)
        result = await db.execute(
            select(WorkspaceResearch)
            .where(WorkspaceResearch.workspace_id == uuid.UUID(workspace_id))
            .order_by(WorkspaceResearch.created_at.desc())
            .limit(20)
        )
        history = result.scalars().all()
        return [h.to_dict() for h in history]


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_ws(db, workspace_id: str) -> Workspace:
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(400, "Invalid workspace ID")

    result = await db.execute(select(Workspace).where(Workspace.id == ws_uuid))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(404, "Workspace not found")
    return ws


async def _save_research(workspace_id: str, query: str, state, result_dict: dict):
    """Persist research result and update workspace confidence/thesis."""
    try:
        async for db in get_db():
            ws_uuid = uuid.UUID(workspace_id)

            research = WorkspaceResearch(
                workspace_id=ws_uuid,
                query=query,
                intent=state.intent,
                tickers=json.dumps(state.tickers),
                result=json.dumps(result_dict, default=str),
                confidence=state.confidence,
            )
            db.add(research)

            # Update workspace with latest thesis and confidence
            ws_result = await db.execute(select(Workspace).where(Workspace.id == ws_uuid))
            ws = ws_result.scalar_one_or_none()
            if ws:
                ws.thesis = state.recommendation
                ws.confidence = state.confidence
                ws.updated_at = datetime.now(timezone.utc)

            await db.commit()
    except Exception as e:
        print(f"[workspace] save error: {e}")
