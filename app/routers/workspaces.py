"""
Workspace router — Living Research Workspaces.
CRUD + streaming research within a persistent workspace context.
"""
import uuid
import json
import asyncio
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select, update

from app.core.database import get_db
from app.models.workspace import Workspace, WorkspaceResearch
from app.models.thesis import ThesisVersion, ConfidenceSnapshot, ThesisClaim
from app.agents.supervisor import run_research
from app.thesis.versioner import create_thesis_version

logger = logging.getLogger(__name__)

VALID_CLAIM_STATUSES = {"active", "strengthened", "confirmed", "weakened", "refuted"}
MAX_PAGE_LIMIT = 200

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
            thesis_version = await _save_research(workspace_id, body.query, state, payload)
            if thesis_version:
                yield f"data: {json.dumps({'type': 'thesis_version', 'thesis_version': thesis_version})}\n\n"

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

        result["thesis_version"] = await _save_research(workspace_id, body.query, state, result)
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


# ── Living Thesis ───────────────────────────────────────────────────────────────

@router.get("/{workspace_id}/thesis")
async def get_current_thesis(workspace_id: str):
    """Full detail of the workspace's current (latest) thesis version."""
    async for db in get_db():
        ws = await _get_ws(db, workspace_id)
        if not ws.current_thesis_version_id:
            return {"workspace_id": workspace_id, "thesis_version": None}

        result = await db.execute(
            select(ThesisVersion).where(ThesisVersion.id == ws.current_thesis_version_id)
        )
        version = result.scalar_one_or_none()
        return {
            "workspace_id": workspace_id,
            "thesis_lifecycle_stage": ws.thesis_lifecycle_stage,
            "conviction_score": ws.conviction_score,
            "thesis_signal": ws.thesis_signal,
            "thesis_version_count": ws.thesis_version_count,
            "thesis_version": version.to_dict() if version else None,
        }


@router.get("/{workspace_id}/thesis/versions")
async def list_thesis_versions(workspace_id: str, limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT)):
    """Lightweight version history for the timeline view."""
    async for db in get_db():
        ws = await _get_ws(db, workspace_id)
        result = await db.execute(
            select(ThesisVersion)
            .where(ThesisVersion.workspace_id == ws.id)
            .order_by(ThesisVersion.version_number.desc())
            .limit(limit)
        )
        versions = result.scalars().all()
        return [v.to_summary_dict() for v in versions]


@router.get("/{workspace_id}/thesis/versions/{version_id}")
async def get_thesis_version(workspace_id: str, version_id: str):
    """Full detail of one thesis version, including its diff from the prior one."""
    async for db in get_db():
        ws = await _get_ws(db, workspace_id)
        try:
            version_uuid = uuid.UUID(version_id)
        except ValueError:
            raise HTTPException(400, "Invalid thesis version ID")

        result = await db.execute(
            select(ThesisVersion).where(
                ThesisVersion.id == version_uuid, ThesisVersion.workspace_id == ws.id
            )
        )
        version = result.scalar_one_or_none()
        if not version:
            raise HTTPException(404, "Thesis version not found")
        return version.to_dict()


@router.get("/{workspace_id}/thesis/confidence-history")
async def get_confidence_history(workspace_id: str, limit: int = Query(100, ge=1, le=500)):
    """Time series of confidence/conviction — feeds the sparkline chart."""
    async for db in get_db():
        ws = await _get_ws(db, workspace_id)
        result = await db.execute(
            select(ConfidenceSnapshot)
            .where(ConfidenceSnapshot.workspace_id == ws.id)
            .order_by(ConfidenceSnapshot.snapshot_at.asc())
            .limit(limit)
        )
        snapshots = result.scalars().all()
        return [s.to_dict() for s in snapshots]


@router.get("/{workspace_id}/thesis/claims")
async def get_thesis_claims(workspace_id: str, status: Optional[str] = None):
    """
    Atomic claims tracked across thesis versions, newest-confirmed first.
    Optional ?status= filter: active | strengthened | confirmed | weakened | refuted
    """
    if status is not None and status not in VALID_CLAIM_STATUSES:
        raise HTTPException(400, f"Invalid status. Must be one of: {', '.join(sorted(VALID_CLAIM_STATUSES))}")

    async for db in get_db():
        ws = await _get_ws(db, workspace_id)
        query = select(ThesisClaim).where(ThesisClaim.workspace_id == ws.id)
        if status:
            query = query.where(ThesisClaim.status == status)
        query = query.order_by(ThesisClaim.last_confirmed_version.desc())

        result = await db.execute(query)
        claims = result.scalars().all()
        return [c.to_dict() for c in claims]


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


async def _save_research(workspace_id: str, query: str, state, result_dict: dict) -> Optional[dict]:
    """
    Persist research result, update workspace confidence/thesis, and version
    the Living Thesis. Returns the new thesis version's summary dict (or None
    if the workspace no longer exists or versioning fails) so callers can
    surface it to the client without a second round trip.
    """
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
            await db.flush()  # assign research.id for the ThesisVersion FK

            ws_result = await db.execute(select(Workspace).where(Workspace.id == ws_uuid))
            ws = ws_result.scalar_one_or_none()
            if not ws:
                await db.rollback()
                return None

            ws.thesis = state.recommendation
            ws.confidence = state.confidence
            ws.updated_at = datetime.now(timezone.utc)

            # create_thesis_version() promises its writes (ThesisVersion +
            # ConfidenceSnapshot + ThesisClaim rows + the workspace's thesis
            # columns) land atomically or not at all. A bare try/except around
            # it here isn't enough — by the time it raises, some of those
            # writes may already be flushed, and committing afterward would
            # persist a half-built version. A SAVEPOINT scopes the rollback to
            # just this block, so the research record and ws.thesis/confidence
            # update (already staged above, outside the savepoint) still land.
            thesis_version = None
            try:
                async with db.begin_nested():
                    thesis_version = await create_thesis_version(db, ws, research, state)
            except Exception:
                logger.exception(
                    "Thesis versioning failed for workspace_id=%s — research saved without a new version",
                    workspace_id,
                )
                thesis_version = None

            await db.commit()
            return thesis_version.to_summary_dict() if thesis_version else None
    except Exception:
        logger.exception("Failed to save research result for workspace_id=%s", workspace_id)
        return None
