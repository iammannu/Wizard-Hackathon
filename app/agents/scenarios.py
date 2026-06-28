"""
Scenario Simulation Engine.
Generates multiple plausible investment futures with probabilities.
Never predicts — always frames as calibrated probabilistic scenarios.
"""
import json
from app.agents.base import llm_json


SCENARIO_TEMPLATES = {
    "stock_analysis": [
        {"name": "Bull Case",             "type": "bull",      "color": "#00cba9", "default_prob": 0.30},
        {"name": "Base Case",             "type": "base",      "color": "#a29bfe", "default_prob": 0.40},
        {"name": "Bear Case",             "type": "bear",      "color": "#ff6b6b", "default_prob": 0.20},
        {"name": "Structural Breakout",   "type": "tail_bull", "color": "#fdcb6e", "default_prob": 0.07},
        {"name": "Black Swan",            "type": "tail_bear", "color": "#fd79a8", "default_prob": 0.03},
    ],
    "macro_query": [
        {"name": "Soft Landing",          "type": "bull",      "color": "#00cba9", "default_prob": 0.35},
        {"name": "Muddling Through",      "type": "base",      "color": "#a29bfe", "default_prob": 0.40},
        {"name": "Recession",             "type": "bear",      "color": "#ff6b6b", "default_prob": 0.18},
        {"name": "Stagflation",           "type": "tail_bear", "color": "#fd79a8", "default_prob": 0.07},
    ],
    "comparison": [
        {"name": "Leader Pulls Ahead",    "type": "bull",      "color": "#00cba9", "default_prob": 0.35},
        {"name": "Both Grow Together",    "type": "base",      "color": "#a29bfe", "default_prob": 0.40},
        {"name": "Market Rotation",       "type": "neutral",   "color": "#fdcb6e", "default_prob": 0.25},
    ],
    "default": [
        {"name": "Optimistic",            "type": "bull",      "color": "#00cba9", "default_prob": 0.30},
        {"name": "Base Case",             "type": "base",      "color": "#a29bfe", "default_prob": 0.45},
        {"name": "Pessimistic",           "type": "bear",      "color": "#ff6b6b", "default_prob": 0.25},
    ],
}


async def generate_scenarios(state, evidence_text: str = "", debate_conclusion: str = "") -> list[dict]:
    """Generate probabilistic investment scenarios from agent research."""
    templates = SCENARIO_TEMPLATES.get(state.intent, SCENARIO_TEMPLATES["default"])

    agent_summary = {}
    for name in state.active_agents:
        out = getattr(state, f"{name}_output", None)
        if out:
            agent_summary[name] = {
                "signal": out.get("signal"),
                "key_finding": out.get("key_finding", ""),
                "confidence": out.get("confidence", 0.5),
            }

    scenario_names = [t["name"] for t in templates]

    raw = await llm_json(
        system=f"""You are a scenario planning expert for institutional investment research.
Generate {len(scenario_names)} distinct plausible scenarios. Frame these as probabilistic futures — never claim prediction.
Each scenario must be internally consistent and rooted in the agent research below.

Scenarios to generate: {json.dumps(scenario_names)}

Agent research summary:
{json.dumps(agent_summary, indent=2)}

External evidence:
{evidence_text[:500]}

{f"Debate conclusion: {debate_conclusion}" if debate_conclusion else ""}

Return a JSON array (NOT wrapped in an object):
[{{
  "name": "scenario name from the list above",
  "probability": 0.0-1.0 (must sum to ~1.0 across all scenarios),
  "confidence": 0.0-1.0 (how confident we are in this scenario's structure),
  "summary": "2-3 sentences describing this specific scenario",
  "key_assumptions": ["assumption 1", "assumption 2", "assumption 3"],
  "key_catalysts": ["what triggers this scenario"],
  "estimated_upside_pct": number (positive for gains, negative for losses),
  "time_horizon": "6-12 months" | "1-2 years" | "2-5 years",
  "investment_implication": "what an investor should do in this scenario"
}}]""",
        user=f"Query: {state.query}\nTickers: {state.tickers}\nIntent: {state.intent}",
    )

    # Handle both array and object responses
    scenario_list = raw if isinstance(raw, list) else raw.get("scenarios", raw.get("items", []))
    if not isinstance(scenario_list, list):
        scenario_list = []

    # Merge with templates (add type + color)
    total_prob = sum(s.get("probability", 0) for s in scenario_list)
    if total_prob <= 0:
        total_prob = 1.0

    result = []
    for i, s in enumerate(scenario_list[:len(templates)]):
        t = templates[i]
        prob = s.get("probability", t["default_prob"])
        result.append({
            **s,
            "name": s.get("name", t["name"]),
            "type": t["type"],
            "color": t["color"],
            "probability": round(prob / total_prob, 3),
        })

    # Pad with template defaults if LLM returned fewer scenarios
    for i in range(len(result), len(templates)):
        t = templates[i]
        result.append({
            "name": t["name"],
            "type": t["type"],
            "color": t["color"],
            "probability": round(t["default_prob"] / total_prob, 3),
            "confidence": 0.4,
            "summary": f"A {t['name'].lower()} scenario based on the available research.",
            "key_assumptions": ["Insufficient data to fully model"],
            "key_catalysts": ["Further research needed"],
            "estimated_upside_pct": 10 if t["type"] in ("bull", "tail_bull") else -15,
            "time_horizon": "1-2 years",
            "investment_implication": "Monitor developments closely.",
        })

    return result
