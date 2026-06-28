"""
Intelligence router — SSE streaming + sync research.
Uses asyncio.Queue so agent events are forwarded to the client the moment they fire,
not batched at the end of the run.
"""
import uuid
import json
import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from app.agents.supervisor import run_research

router = APIRouter(prefix="/api/v1/intelligence", tags=["intelligence"])


class ResearchRequest(BaseModel):
    query: str
    tickers: Optional[list[str]] = None
    depth: str = "full"


@router.post("/research")
async def research_stream(body: ResearchRequest):
    """Stream multi-agent analysis via SSE — each event is forwarded the moment it fires."""

    async def generate():
        session_id = str(uuid.uuid4())
        yield f"data: {json.dumps({'type': 'session_start', 'session_id': session_id})}\n\n"

        queue: asyncio.Queue = asyncio.Queue()
        state_holder: dict = {}

        async def on_event(event: dict):
            await queue.put(event)

        async def run():
            try:
                state_holder["state"] = await run_research(
                    body.query, body.tickers, body.depth,
                    on_event=on_event,
                )
            except Exception as e:
                await queue.put({"type": "error", "message": str(e)})
            finally:
                await queue.put(None)  # sentinel — signals generator to stop

        asyncio.create_task(run())

        # Forward events as they arrive — this is the real-time path
        while True:
            event = await queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"

        # Send final result payload once the pipeline is done
        if "state" in state_holder:
            state = state_holder["state"]
            payload = {
                "type": "result",
                "session_id": session_id,
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
                "agent_outputs": {
                    name: getattr(state, f"{name}_output")
                    for name in state.active_agents
                    if getattr(state, f"{name}_output", None)
                },
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
            yield f"data: {json.dumps({'type': 'complete', 'session_id': session_id})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/research/sync")
async def research_sync(body: ResearchRequest):
    """Non-streaming version — returns full analysis in one response."""
    try:
        state = await run_research(body.query, body.tickers, body.depth)
        return {
            "session_id": str(uuid.uuid4()),
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
            "agent_outputs": {
                name: getattr(state, f"{name}_output")
                for name in state.active_agents
                if getattr(state, f"{name}_output", None)
            },
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
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/compare")
async def compare(tickers: list[str], query: str = "Compare these stocks"):
    if len(tickers) < 2 or len(tickers) > 4:
        raise HTTPException(400, "Provide 2-4 tickers")
    state = await run_research(f"Compare {' vs '.join(tickers)}: {query}", tickers=tickers, depth="full")
    return {
        "tickers": tickers,
        "recommendation": state.recommendation,
        "explanation": state.explanation,
        "confidence": state.confidence,
        "agent_outputs": {n: getattr(state, f"{n}_output") for n in state.active_agents if getattr(state, f"{n}_output", None)},
    }
