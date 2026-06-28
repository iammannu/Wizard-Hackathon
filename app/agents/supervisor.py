"""
Supervisor — orchestrates the full Autonomous Investment Intelligence Pipeline.

Pipeline:
  1. Intent parsing
  2. Evidence gathering (You.com + Tavily)
  3. 12 agents in parallel
  4. Agent debate (when signals conflict)
  5. Scenario simulation
  6. Knowledge graph extraction
  7. Synthesis → institutional investment thesis

on_event: optional async callable — if supplied, every pipeline event is pushed
          to the caller immediately (real-time SSE). Events are also collected in
          state.stream_events for backwards-compatible callers.
"""
import asyncio
import json
from typing import Optional, Callable, Awaitable
from app.agents.state import AgentState
from app.agents.base import llm_json
from app.agents.agents import (
    technical_agent, fundamental_agent, sentiment_agent,
    valuation_agent, risk_agent, macro_agent,
    growth_investor_agent, value_investor_agent, quant_researcher_agent,
    industry_specialist_agent, short_seller_agent, devils_advocate_agent,
)
from app.agents.debate import run_debate
from app.agents.scenarios import generate_scenarios
from app.agents.graph import extract_knowledge_graph
from app.providers.evidence import gather_evidence, format_for_agents

# All 12 agents — always active on full-depth queries
ALL_AGENTS = [
    "technical", "fundamental", "sentiment", "risk", "valuation", "macro",
    "growth_investor", "value_investor", "quant_researcher",
    "industry_specialist", "short_seller", "devils_advocate",
]

# Quick-mode subsets (depth="quick") — 3-4 most relevant per intent
INTENT_TO_AGENTS_QUICK = {
    "stock_analysis":    ["technical", "fundamental", "sentiment"],
    "portfolio_check":   ["risk", "macro", "value_investor"],
    "macro_query":       ["macro", "sentiment", "industry_specialist"],
    "screener":          ["fundamental", "technical", "risk"],
    "comparison":        ["fundamental", "valuation", "technical"],
    "scenario_analysis": ["macro", "risk", "devils_advocate"],
    "event_impact":      ["macro", "sentiment", "risk"],
    "general":           ["fundamental", "sentiment", "macro"],
}

AGENT_WEIGHTS = {
    "stock_analysis": {
        "technical": 0.10, "fundamental": 0.20, "sentiment": 0.08, "risk": 0.10, "valuation": 0.18,
        "growth_investor": 0.10, "value_investor": 0.10, "quant_researcher": 0.06,
        "industry_specialist": 0.05, "short_seller": 0.02, "devils_advocate": 0.01,
    },
    "portfolio_check":   {"risk": 0.40, "macro": 0.30, "quant_researcher": 0.20, "value_investor": 0.10},
    "macro_query":       {"macro": 0.50, "sentiment": 0.30, "industry_specialist": 0.20},
    "comparison":        {"fundamental": 0.25, "valuation": 0.25, "risk": 0.15, "technical": 0.15, "growth_investor": 0.10, "value_investor": 0.10},
}

AGENT_FN = {
    "technical":           technical_agent,
    "fundamental":         fundamental_agent,
    "sentiment":           sentiment_agent,
    "valuation":           valuation_agent,
    "risk":                risk_agent,
    "macro":               macro_agent,
    "growth_investor":     growth_investor_agent,
    "value_investor":      value_investor_agent,
    "quant_researcher":    quant_researcher_agent,
    "industry_specialist": industry_specialist_agent,
    "short_seller":        short_seller_agent,
    "devils_advocate":     devils_advocate_agent,
}

AGENT_DISPLAY_NAMES = {
    "technical":           "Technical Analyst",
    "fundamental":         "Fundamental Analyst",
    "sentiment":           "Sentiment Analyst",
    "valuation":           "Valuation Expert",
    "risk":                "Risk Manager",
    "macro":               "Macro Economist",
    "growth_investor":     "Growth Investor",
    "value_investor":      "Value Investor",
    "quant_researcher":    "Quant Researcher",
    "industry_specialist": "Industry Specialist",
    "short_seller":        "Short Seller",
    "devils_advocate":     "Devil's Advocate",
}


async def parse_intent(state: AgentState, emit: Callable) -> AgentState:
    result = await llm_json(
        system="""Parse this financial query and classify the intent. Respond ONLY with JSON.

Intent rules:
- "stock_analysis"    — any query about a specific stock, ticker, company, or investment thesis (even thematic ones like "AI Infrastructure" or "space economy")
- "comparison"        — comparing 2+ stocks or sectors
- "screener"          — filtering/finding stocks by criteria
- "macro_query"       — broad macroeconomic questions with NO company focus
- "portfolio_check"   — portfolio-level risk or allocation questions
- "scenario_analysis" — what-if scenarios
- "event_impact"      — impact of a specific event (earnings, Fed, etc.)
- "general"           — everything else

Default to "stock_analysis" when the query involves an investment thesis, sector play, or any named asset.

{"intent":"stock_analysis"|"portfolio_check"|"macro_query"|"screener"|"comparison"|"scenario_analysis"|"event_impact"|"general","tickers":[],"timeframe":"short_term"|"long_term"|"general"}""",
        user=state.query,
        fast=True,
    )
    intent = result.get("intent", "general")
    tickers = state.tickers or result.get("tickers", [])

    if state.depth == "quick":
        active = INTENT_TO_AGENTS_QUICK.get(intent, ["fundamental", "sentiment", "macro"])
    else:
        active = ALL_AGENTS  # always all 12 on full depth

    state.intent = intent
    state.tickers = tickers
    state.timeframe = result.get("timeframe", "general")
    state.active_agents = active
    await emit({"type": "intent_parsed", "intent": intent, "tickers": tickers, "agents": active})
    return state


async def run_agents(state: AgentState, emit: Callable) -> AgentState:
    """Run all active agents in parallel — each emits completion the moment it finishes."""
    primary = [n for n in state.active_agents if n != "devils_advocate"]
    has_advocate = "devils_advocate" in state.active_agents

    # Signal all agents as started so the UI shows them immediately in "thinking" state
    for name in primary:
        await emit({
            "type": "agent_start",
            "agent": name,
            "display_name": AGENT_DISPLAY_NAMES.get(name, name),
        })

    # Each coroutine emits its own completion event as soon as it finishes
    async def run_one(name: str):
        try:
            result = await AGENT_FN[name](state)
        except Exception as e:
            print(f"[agent error] {name}: {e}")
            return
        setattr(state, f"{name}_output", result)
        await emit({
            "type": "agent_complete",
            "agent": name,
            "display_name": AGENT_DISPLAY_NAMES.get(name, name),
            "signal": result.get("signal"),
            "confidence": result.get("confidence"),
            "key_finding": result.get("key_finding", ""),
        })

    await asyncio.gather(*[run_one(n) for n in primary if n in AGENT_FN])

    # Devil's advocate runs after all others (needs their outputs)
    if has_advocate and "devils_advocate" in AGENT_FN:
        await emit({
            "type": "agent_start",
            "agent": "devils_advocate",
            "display_name": "Devil's Advocate",
        })
        try:
            da_result = await devils_advocate_agent(state)
            state.devils_advocate_output = da_result
            await emit({
                "type": "agent_complete",
                "agent": "devils_advocate",
                "display_name": "Devil's Advocate",
                "signal": da_result.get("signal"),
                "confidence": da_result.get("confidence"),
                "key_finding": da_result.get("key_finding", ""),
            })
        except Exception as e:
            print(f"[agent error] devils_advocate: {e}")

    return state


def _compute_confidence(state: AgentState) -> tuple[float, dict]:
    outputs = {n: getattr(state, f"{n}_output") for n in state.active_agents if getattr(state, f"{n}_output", None)}
    if not outputs:
        return 0.3, {"data_quality": 0.3, "signal_agreement": 0.3, "overall": 0.3}

    weights = AGENT_WEIGHTS.get(state.intent, {})
    total_w = sum(weights.get(a, 0.15) for a in outputs)
    weighted_conf = sum(outputs[a].get("confidence", 0.5) * weights.get(a, 0.15) for a in outputs) / max(total_w, 0.01)

    signals = [outputs[a].get("signal") for a in outputs if outputs[a].get("signal")]
    if signals:
        dominant = max(set(signals), key=signals.count)
        agreement = signals.count(dominant) / len(signals)
    else:
        agreement = 0.5

    bullish = [k for k, v in outputs.items() if v.get("signal") == "bullish"]
    bearish = [k for k, v in outputs.items() if v.get("signal") == "bearish"]

    conflicts = []
    if bullish and bearish:
        conflicts.append({
            "between": [bullish[0], bearish[0]],
            "description": f"{AGENT_DISPLAY_NAMES.get(bullish[0], bullish[0])} bullish vs {AGENT_DISPLAY_NAMES.get(bearish[0], bearish[0])} bearish",
        })

    state.conflicts = conflicts
    conflict_penalty = len(conflicts) * 0.04
    overall = round(min(0.95, max(0.15, weighted_conf - conflict_penalty)), 3)

    return overall, {"data_quality": round(weighted_conf, 3), "signal_agreement": round(agreement, 3), "overall": overall}


async def synthesize(state: AgentState, emit: Callable, evidence_text: str = "", debate: dict | None = None) -> AgentState:
    outputs_summary = {}
    for name in state.active_agents:
        out = getattr(state, f"{name}_output", None)
        if out:
            outputs_summary[name] = {
                "display_name": AGENT_DISPLAY_NAMES.get(name, name),
                "signal": out.get("signal"),
                "key_finding": out.get("key_finding"),
                "confidence": out.get("confidence"),
            }

    confidence, breakdown = _compute_confidence(state)

    debate_ctx = ""
    if debate and debate.get("debate_occurred"):
        debate_ctx = f"\nDebate conclusion: {debate.get('moderator_conclusion','')}\nKey insight: {debate.get('key_insight','')}"

    result = await llm_json(
        system=f"""You are the Research Director synthesizing a 12-analyst institutional investment committee.

Agent outputs:
{json.dumps(outputs_summary, indent=2)}

External research evidence:
{evidence_text[:600] if evidence_text else "None available"}
{debate_ctx}

Generate institutional-grade investment thesis as JSON:
{{
  "recommendation": "Precise, actionable recommendation (2-3 sentences). Name specific price levels or conditions where applicable.",
  "explanation": "4-5 sentence synthesis explaining the weight of evidence and key drivers.",
  "bull_case": {{"summary":"string","key_points":["3-4 specific points with data"],"probability":0-1}},
  "bear_case": {{"summary":"string","key_points":["3-4 specific points with data"],"probability":0-1}},
  "key_risks": ["4-5 specific risks with context"],
  "invalidation_conditions": ["3 conditions that would invalidate the bull case"],
  "known_unknowns": ["3-4 things we cannot currently assess"]
}}

Be specific. Reference actual agent findings. Institutional quality.""",
        user=f"Query: {state.query}\nIntent: {state.intent}\nTickers: {state.tickers}",
    )

    evidence_boost = (state.evidence or {}).get("confidence_boost", 0)
    boosted_confidence = round(min(0.95, confidence + evidence_boost), 3)

    state.confidence = boosted_confidence
    state.confidence_breakdown = {**breakdown, "overall": boosted_confidence, "evidence_boost": evidence_boost}
    state.recommendation = result.get("recommendation", "")
    state.explanation = result.get("explanation", "")
    state.bull_case = result.get("bull_case", {})
    state.bear_case = result.get("bear_case", {})
    state.key_risks = result.get("key_risks", [])
    state.invalidation_conditions = result.get("invalidation_conditions", [])
    state.known_unknowns = result.get("known_unknowns", [])
    await emit({"type": "synthesis_complete", "confidence": boosted_confidence})
    return state


async def run_research(
    query: str,
    tickers: list[str] | None = None,
    depth: str = "full",
    workspace_id: str | None = None,
    themes: list[str] | None = None,
    on_event: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> AgentState:
    """
    Full Autonomous Investment Intelligence Pipeline.

    on_event: if provided, every pipeline event is awaited immediately so callers
              can forward to SSE clients in real time. Events are always collected
              in state.stream_events for backwards-compat callers that don't supply
              on_event.
    """
    state = AgentState(query=query, tickers=tickers or [], depth=depth, workspace_id=workspace_id)

    async def emit(event: dict):
        state.stream_events.append(event)
        if on_event:
            await on_event(event)

    # 1. Parse intent
    state = await parse_intent(state, emit)

    # 2. Gather evidence (You.com + Tavily) — graceful degradation if keys missing
    await emit({"type": "evidence_searching", "message": "Searching You.com + Tavily..."})
    evidence = await gather_evidence(state.tickers, query, themes or [])
    state.evidence = evidence
    await emit({
        "type": "evidence_gathered",
        "you_com_count": evidence["you_com"]["count"],
        "tavily_count": evidence["tavily"]["count"],
        "total_sources": evidence["total_sources"],
        "coverage": evidence["coverage"],
        "you_com_available": evidence["you_com"]["available"],
        "tavily_available": evidence["tavily"]["available"],
    })

    evidence_text = format_for_agents(evidence)

    # 3. Run all 12 agents in parallel — per-agent completion events stream immediately
    state = await run_agents(state, emit)

    # 4. Agent debate when bull/bear conflict + full depth
    outputs = {n: getattr(state, f"{n}_output") for n in state.active_agents if getattr(state, f"{n}_output", None)}
    bull_agents = [k for k, v in outputs.items() if v.get("signal") == "bullish"]
    bear_agents = [k for k, v in outputs.items() if v.get("signal") == "bearish"]

    debate: dict = {"debate_occurred": False}
    if bull_agents and bear_agents and depth == "full":
        await emit({"type": "debate_starting", "bull": bull_agents[0], "bear": bear_agents[0]})
        debate = await run_debate(state, bull_agents, bear_agents, evidence_text)
        state.debate = debate
        await emit({
            "type": "debate_complete",
            "winner": debate.get("debate_winner", "draw"),
            "key_insight": debate.get("key_insight", ""),
            "rounds": len(debate.get("rounds", [])),
        })

    # 5. Generate scenarios
    await emit({"type": "scenarios_generating"})
    scenarios = await generate_scenarios(state, evidence_text, debate.get("moderator_conclusion", ""))
    state.scenarios = scenarios
    await emit({"type": "scenarios_generated", "count": len(scenarios)})

    # 6. Extract knowledge graph
    if state.tickers and depth == "full":
        await emit({"type": "graph_building"})
        graph = await extract_knowledge_graph(state, evidence_text)
        state.knowledge_graph = graph
        await emit({"type": "graph_built", "nodes": graph.get("node_count", 0), "edges": graph.get("edge_count", 0)})

    # 7. Synthesize final institutional thesis
    await emit({"type": "synthesizing"})
    state = await synthesize(state, emit, evidence_text=evidence_text, debate=debate)

    return state
