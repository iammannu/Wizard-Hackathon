"""
Agent Debate Engine — structured two-round debate between opposing signals.
Bull and bear agents argue, then a neutral moderator reaches a conclusion.
The debate transcript is streamed live to the frontend.
"""
import json
from app.agents.base import llm_json


AGENT_PERSONAS = {
    "technical":           "You are a technical analyst who reads price action and momentum.",
    "fundamental":         "You are a fundamental analyst focused on earnings quality and balance sheet health.",
    "sentiment":           "You are a sentiment analyst tracking news flow and market narrative shifts.",
    "valuation":           "You are a valuation specialist focused on intrinsic value and margin of safety.",
    "risk":                "You are a risk manager who protects against tail risks and drawdowns.",
    "macro":               "You are a macro economist assessing rate environment and economic cycle.",
    "growth_investor":     "You are a growth investor who bets on exponential TAM expansion and disruption.",
    "value_investor":      "You are a deep value investor who demands a significant margin of safety.",
    "quant_researcher":    "You are a quant researcher who trusts statistical signals over narratives.",
    "industry_specialist": "You are an industry expert with deep competitive dynamics knowledge.",
    "short_seller":        "You are a short seller who finds overvaluation and structural decline.",
    "devils_advocate":     "You are the devil's advocate who challenges all consensus views.",
}


async def run_debate(state, bull_agents: list[str], bear_agents: list[str], evidence_text: str = "") -> dict:
    """Two-round structured debate between bull and bear agents, moderated by a neutral party."""
    if not bull_agents or not bear_agents:
        return {"debate_occurred": False, "rounds": [], "moderator_conclusion": ""}

    bull = bull_agents[0]
    bear = bear_agents[0]

    bull_out = getattr(state, f"{bull}_output", {}) or {}
    bear_out = getattr(state, f"{bear}_output", {}) or {}

    bull_finding = bull_out.get("key_finding", f"{bull} is bullish")
    bear_finding = bear_out.get("key_finding", f"{bear} is bearish")

    bull_persona = AGENT_PERSONAS.get(bull, f"You are the {bull} analyst.")
    bear_persona = AGENT_PERSONAS.get(bear, f"You are the {bear} analyst.")

    rounds = []
    ctx = f"Tickers: {state.tickers}\nQuery: {state.query}\nEvidence excerpt: {evidence_text[:400]}"

    # Round 1 — opening statements
    bull_open, bear_open = await _parallel(
        llm_json(
            system=f"""{bull_persona} Make your BULLISH opening argument in 2 sentences.
Return JSON: {{"argument":"your argument","key_point":"strongest point","confidence":0-1}}""",
            user=f"Your finding: {bull_finding}\n{ctx}",
            fast=True,
        ),
        llm_json(
            system=f"""{bear_persona} Make your BEARISH opening argument in 2 sentences.
Return JSON: {{"argument":"your argument","key_point":"strongest point","confidence":0-1}}""",
            user=f"Your finding: {bear_finding}\n{ctx}",
            fast=True,
        ),
    )

    rounds.append({
        "round": 1, "type": "opening",
        "bull": {"agent": bull, "persona": bull_persona[:60], "argument": bull_open.get("argument", ""), "key_point": bull_open.get("key_point", "")},
        "bear": {"agent": bear, "persona": bear_persona[:60], "argument": bear_open.get("argument", ""), "key_point": bear_open.get("key_point", "")},
    })

    # Round 2 — rebuttals
    bull_reply, bear_reply = await _parallel(
        llm_json(
            system=f"""{bull_persona} Rebut the bear's argument and reinforce your bull thesis in 2 sentences.
Return JSON: {{"argument":"your rebuttal","concession":"any point you admit is valid","confidence":0-1}}""",
            user=f"Bear argued: {bear_open.get('argument','')}\nYour position: {bull_finding}",
            fast=True,
        ),
        llm_json(
            system=f"""{bear_persona} Rebut the bull's argument and reinforce your bear thesis in 2 sentences.
Return JSON: {{"argument":"your rebuttal","concession":"any point you admit is valid","confidence":0-1}}""",
            user=f"Bull argued: {bull_open.get('argument','')}\nYour position: {bear_finding}",
            fast=True,
        ),
    )

    rounds.append({
        "round": 2, "type": "rebuttal",
        "bull": {"agent": bull, "argument": bull_reply.get("argument", ""), "concession": bull_reply.get("concession", "")},
        "bear": {"agent": bear, "argument": bear_reply.get("argument", ""), "concession": bear_reply.get("concession", "")},
    })

    # Moderator synthesis
    moderator = await llm_json(
        system="""You are a neutral investment committee chair. Synthesize this debate.
Return JSON: {"conclusion":"2-3 sentence balanced conclusion","winner":"bull"|"bear"|"draw","key_insight":"most important debate insight","residual_uncertainty":"main remaining question"}""",
        user=f"""Bull ({bull}): Opening: "{bull_open.get('argument','')}" | Rebuttal: "{bull_reply.get('argument','')}"
Bear ({bear}): Opening: "{bear_open.get('argument','')}" | Rebuttal: "{bear_reply.get('argument','')}"
Query: {state.query}""",
        fast=True,
    )

    return {
        "debate_occurred": True,
        "participants": {"bull": bull, "bear": bear},
        "rounds": rounds,
        "moderator_conclusion": moderator.get("conclusion", ""),
        "debate_winner": moderator.get("winner", "draw"),
        "key_insight": moderator.get("key_insight", ""),
        "residual_uncertainty": moderator.get("residual_uncertainty", ""),
    }


async def _parallel(*coros):
    import asyncio
    return await asyncio.gather(*coros, return_exceptions=False)
