"""
Signal + conviction derivation for a single research run.

Why it exists:
  AgentState carries per-agent signals and an LLM-authored bull_case/bear_case
  with probabilities, but nothing rolls those up into the single "signal"
  and "conviction_score" that ThesisVersion/Workspace need for list views,
  badges, and lifecycle transitions. That rollup has to be deterministic
  (rule: change detection must be deterministic) since it runs on every
  research call and feeds version-over-version comparison.

How it integrates:
  Called once by app/thesis/versioner.py per research run, after synthesize()
  has populated state.bull_case/bear_case/confidence/confidence_breakdown.

Future extension points:
  - compute_conviction's weighting is a first-pass heuristic. Phase 2 (AI
    Memory) can feed a "claim durability" term once ThesisClaim history is
    deep enough to be predictive.
  - derive_signal falls back to per-agent majority vote when the synthesis
    step doesn't return bull/bear probabilities (e.g. LLM call failed) —
    keeps the pipeline degrading gracefully instead of raising.
"""
from collections import Counter
from app.agents.state import AgentState

SIGNAL_SPLIT_THRESHOLD = 0.15  # min probability gap between bull/bear to call a direction


def derive_signal(state: AgentState) -> str:
    """Roll up the thesis-level signal: 'bullish' | 'bearish' | 'neutral'."""
    bull_prob = (state.bull_case or {}).get("probability")
    bear_prob = (state.bear_case or {}).get("probability")

    if isinstance(bull_prob, (int, float)) and isinstance(bear_prob, (int, float)):
        gap = bull_prob - bear_prob
        if gap > SIGNAL_SPLIT_THRESHOLD:
            return "bullish"
        if gap < -SIGNAL_SPLIT_THRESHOLD:
            return "bearish"
        return "neutral"

    # Fallback: majority vote across per-agent signals.
    signals = [
        getattr(state, f"{name}_output").get("signal")
        for name in state.active_agents
        if getattr(state, f"{name}_output", None) and getattr(state, f"{name}_output").get("signal")
    ]
    if not signals:
        return "neutral"

    # Counter.most_common() ties break on first-inserted for equal counts, but
    # Python's set() iteration order is hash-seed dependent — using set() here
    # would make a tied vote non-reproducible across process restarts, which
    # breaks the "change detection must be deterministic" invariant. A genuine
    # tie between directions has no dominant call, so it resolves to neutral
    # rather than picking one arbitrarily.
    counts = Counter(signals)
    top_count = max(counts.values())
    leaders = {signal for signal, count in counts.items() if count == top_count}
    if len(leaders) > 1:
        return "neutral"
    dominant = leaders.pop()
    return dominant if dominant in ("bullish", "bearish") else "neutral"


def compute_conviction(state: AgentState, agreement_streak: int = 0) -> float:
    """
    Multi-factor conviction score — distinct from the raw pipeline confidence.

    Factors (weights sum to 1.0, plus a bounded stability bonus):
      - 0.6  base confidence (agent-weighted, conflict-penalized)
      - 0.3  cross-agent signal agreement
      - 0.1  evidence boost (external source corroboration)
      + up to 0.10 stability bonus: +0.02 per consecutive prior version that
        confirmed the same signal, capped at 5 versions. A thesis that keeps
        surviving re-research deserves higher conviction than one asserted once.
    """
    breakdown = state.confidence_breakdown or {}
    base = state.confidence or 0.0
    agreement = breakdown.get("signal_agreement", 0.5)
    evidence_boost = breakdown.get("evidence_boost", 0.0)

    stability_bonus = min(0.10, 0.02 * max(0, agreement_streak))
    conviction = base * 0.6 + agreement * 0.3 + evidence_boost * 1.0 + stability_bonus
    return round(min(0.98, max(0.05, conviction)), 3)
