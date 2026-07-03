"""
Structured diff between the previous ThesisVersion and the version being created.

Why it exists:
  A thesis is "living" because each research run can reinforce, refine, or
  overturn the last one. The UI and the alert system (Phase 6) both need a
  machine-readable answer to "what changed and how much does it matter?"
  rather than re-reading two full theses and eyeballing it.

How it integrates:
  app/thesis/versioner.py calls compute_diff(previous, new_fields) after
  deriving the new version's signal/conviction but before persisting the row.
  The result is stored verbatim in ThesisVersion.diff (JSON) plus the two
  scalar columns is_major_change / change_type used for quick filtering.

Performance considerations:
  Pure string/set comparisons on already-in-memory data — no DB round trips,
  no LLM calls. Safe to run on every research call.

Future extension points:
  - change_type is a 4-bucket deterministic classification (reinforced /
    evolved / challenged / invalidated). Phase 6 (Alerts) can subscribe to
    "challenged" and "invalidated" directly off this field.
  - Claim-level diffing (which specific claims flipped) lives in claims.py —
    this module only handles thesis-level (signal/conviction/set) diffing.
"""
from typing import Optional

CONVICTION_MAJOR_DELTA = 0.15
CONVICTION_CHALLENGE_DELTA = -0.15
INVALIDATION_CONVICTION_FLOOR = 0.30


def _normalized_set(items) -> set:
    return {str(i).strip().lower() for i in (items or []) if str(i).strip()}


def _set_diff(old_items, new_items) -> dict:
    old_set, new_set = _normalized_set(old_items), _normalized_set(new_items)
    return {
        "added": sorted(new_set - old_set),
        "removed": sorted(old_set - new_set),
    }


def compute_diff(previous, new_fields: dict) -> tuple[Optional[dict], bool, Optional[str]]:
    """
    previous: ThesisVersion | None (None for version 1)
    new_fields: dict with keys signal, conviction_score, confidence, bull_case,
                bear_case, key_risks, key_assumptions, invalidation_conditions,
                known_unknowns

    Returns (diff_dict_or_None, is_major_change, change_type_or_None)
    """
    if previous is None:
        return None, False, None

    old_signal = previous.signal
    new_signal = new_fields["signal"]
    signal_changed = old_signal != new_signal

    conviction_delta = round(new_fields["conviction_score"] - previous.conviction_score, 3)
    confidence_delta = round(new_fields["confidence"] - previous.confidence, 3)

    diff = {
        "previous_signal": old_signal,
        "new_signal": new_signal,
        "signal_changed": signal_changed,
        "conviction_delta": conviction_delta,
        "confidence_delta": confidence_delta,
        "key_risks": _set_diff(previous.key_risks_list(), new_fields["key_risks"]),
        "key_assumptions": _set_diff(previous.key_assumptions_list(), new_fields["key_assumptions"]),
        "invalidation_conditions": _set_diff(
            previous.invalidation_conditions_list(), new_fields["invalidation_conditions"]
        ),
        "known_unknowns": _set_diff(previous.known_unknowns_list(), new_fields["known_unknowns"]),
        "bull_points": _set_diff(
            (previous.bull_case_dict() or {}).get("key_points", []),
            (new_fields["bull_case"] or {}).get("key_points", []),
        ),
        "bear_points": _set_diff(
            (previous.bear_case_dict() or {}).get("key_points", []),
            (new_fields["bear_case"] or {}).get("key_points", []),
        ),
    }

    change_type = _classify_change(signal_changed, new_signal, conviction_delta, new_fields["conviction_score"])
    is_major_change = signal_changed or abs(conviction_delta) >= CONVICTION_MAJOR_DELTA

    return diff, is_major_change, change_type


def _classify_change(signal_changed: bool, new_signal: str, conviction_delta: float, new_conviction: float) -> str:
    if signal_changed:
        # A directional flip is always at least a challenge; it's a full
        # invalidation once conviction in the new direction is also weak,
        # meaning the flip isn't yet backed by strong evidence either.
        if new_conviction < INVALIDATION_CONVICTION_FLOOR:
            return "invalidated"
        return "challenged"

    if conviction_delta <= CONVICTION_CHALLENGE_DELTA:
        return "challenged"

    if abs(conviction_delta) < 0.05:
        return "reinforced"

    return "evolved"
