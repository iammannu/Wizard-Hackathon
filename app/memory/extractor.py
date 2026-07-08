"""
Memory extraction — turns one completed research session (AgentState +,
when available, its just-created ThesisVersion) into a capped list of
MemoryCandidate objects: facts, beliefs, investment decisions, open
questions, resolved questions, and user notes.

Why LLM-based (unlike app/thesis/claims.py's deterministic extraction):
  Thesis claims are extracted deterministically because they're already
  structured (bull_case.key_points, key_risks, ...) — no judgment needed.
  Memory candidates need judgment: deciding *what's worth remembering*
  ("AAPL's Q3 gross margin was 46.2%" is a fact worth keeping; "the RSI
  ticked up today" usually isn't), classifying it into a type, and writing
  it as a durable, context-free sentence (a memory item must make sense
  read cold, months later, without the original query in front of it) is
  exactly the kind of synthesis judgment this codebase already delegates to
  llm_json elsewhere (thesis synthesis, evidence claim building).

How it integrates:
  Called from app/memory/service.py::consolidate_research(), after
  create_thesis_version() has run (so a ThesisVersion, if any, is
  available) but before consolidator.py decides new/reinforce/contradict.
"""
import json
from typing import Optional

from app.agents.base import llm_json
from app.agents.state import AgentState
from app.core.config import get_settings
from app.memory.models import MemoryCandidate, MemorySourceCitation

settings = get_settings()

_VALID_TYPES = {"fact", "belief", "investment_decision", "open_question", "resolved_question", "user_note"}


def _agent_outputs_summary(state: AgentState) -> dict:
    summary = {}
    for name in state.active_agents:
        out = getattr(state, f"{name}_output", None)
        if out:
            summary[name] = {
                "signal": out.get("signal"),
                "key_finding": out.get("key_finding"),
            }
    return summary


async def extract_memory_candidates(
    state: AgentState,
    thesis_version=None,  # Optional[ThesisVersion] — avoids a hard import cycle with app.models.thesis
) -> list[MemoryCandidate]:
    """Extract durable memory candidates from a completed research session.

    Returns [] (never raises) on LLM failure — a missed extraction for one
    session is not worth failing the research-save transaction over, same
    resilience contract as app/documents/evidence/claims.py."""
    if not state.recommendation and not state.explanation:
        return []

    thesis_ctx = ""
    if thesis_version is not None:
        thesis_ctx = (
            f"\nThesis signal: {thesis_version.signal}, "
            f"conviction: {thesis_version.conviction_score}, "
            f"lifecycle: {thesis_version.lifecycle_stage}"
        )

    max_items = max(1, settings.memory_max_extracted_per_session)

    try:
        result = await llm_json(
            system=f"""You extract durable, standalone memory items from a completed investment research session.

Each item must:
- Make sense read cold, months later, with no other context (name the ticker/company explicitly, don't say "it" or "this stock").
- Be classified as exactly one type:
  "fact"                — an objective, checkable data point (financials, events, ratios).
  "belief"               — an analytical judgment or thesis-level view that could later be confirmed or refuted.
  "investment_decision"  — a concrete recommendation/action taken (buy/sell/hold, sizing, timing).
  "open_question"        — something identified as unresolved/unknown that should be revisited.
  "resolved_question"    — something previously uncertain that this session's evidence settled.
  "user_note"            — a note about user intent/preference/context inferred from the query itself, not the market.
- Get a confidence 0-1 reflecting how well-supported the item is by the session's evidence and agent agreement.
- Skip trivial, generic, or purely momentary observations (e.g. "RSI is 55 today") — only keep what's worth recalling next session.

Return at most {max_items} items, ranked most important first, as JSON:
{{"items": [{{"memory_type": "fact"|"belief"|"investment_decision"|"open_question"|"resolved_question"|"user_note", "content": "standalone sentence", "confidence": 0-1, "decision_signal": "bullish"|"bearish"|"neutral"|null}}]}}

decision_signal is only non-null for memory_type="investment_decision".""",
            user=(
                f"Query: {state.query}\n"
                f"Tickers: {state.tickers}\n"
                f"Recommendation: {state.recommendation}\n"
                f"Explanation: {state.explanation}\n"
                f"Bull case: {json.dumps(state.bull_case or {})[:500]}\n"
                f"Bear case: {json.dumps(state.bear_case or {})[:500]}\n"
                f"Key risks: {state.key_risks}\n"
                f"Known unknowns: {state.known_unknowns}\n"
                f"Agent signals: {json.dumps(_agent_outputs_summary(state))[:800]}"
                f"{thesis_ctx}"
            ),
        )
    except Exception:
        return []

    raw_items = result.get("items", []) if isinstance(result, dict) else []
    citation = MemorySourceCitation(query=state.query)

    candidates: list[MemoryCandidate] = []
    for raw in raw_items[:max_items]:
        if not isinstance(raw, dict):
            continue
        memory_type = raw.get("memory_type")
        content = (raw.get("content") or "").strip()
        if memory_type not in _VALID_TYPES or not content:
            continue
        try:
            confidence = float(raw.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))
        if confidence < settings.memory_min_confidence:
            continue

        candidates.append(MemoryCandidate(
            memory_type=memory_type,
            content=content,
            confidence=confidence,
            tickers=list(state.tickers or []),
            citations=[citation],
            decision_signal=raw.get("decision_signal") if memory_type == "investment_decision" else None,
        ))

    return candidates
