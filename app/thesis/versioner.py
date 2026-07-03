"""
Orchestrates signal derivation, diffing, lifecycle transition, and claim
tracking into a single persisted ThesisVersion per research run.

Why it exists:
  This is the one place that knows how a completed AgentState becomes a row
  in thesis_versions + confidence_snapshots + thesis_claims, and how the
  parent Workspace's denormalized thesis columns get updated. Keeping that
  assembly in one function (rather than spread across the router) is what
  makes the Living Thesis system testable independent of the SSE/HTTP layer.

How it integrates:
  Called from app/routers/workspaces.py::_save_research, after the
  WorkspaceResearch row has been flushed (so research.id exists for the FK).
  Does not commit — the caller owns the transaction boundary so the research
  row, thesis version, confidence snapshot, claim updates, and workspace
  column updates land atomically or not at all.

Performance considerations:
  One SELECT to load the previous ThesisVersion (for diffing), one ranged
  SELECT to compute the signal-agreement streak (a single query over the last
  MAX_STREAK_HOPS version_numbers, not a chain-walk — version_number is
  sequential per workspace so a range scan replaces what would otherwise be
  up to N round trips), and the claims sync's two SELECTs. All scoped to a
  single workspace's history — cheap at any realistic per-workspace version
  count.

Future extension points:
  - triggered_by is currently always "user_query"; Phase 5 (Monitoring) will
    call this same function with triggered_by="scheduled_refresh" from a
    background scheduler, and Phase 6 (Alerts) with "alert_trigger".
"""
import json
from typing import Optional
from sqlalchemy import select

from app.agents.state import AgentState
from app.models.workspace import Workspace, WorkspaceResearch
from app.models.thesis import ThesisVersion, ConfidenceSnapshot
from app.thesis.signal import derive_signal, compute_conviction
from app.thesis.comparator import compute_diff
from app.thesis.lifecycle import determine_lifecycle_stage
from app.thesis.claims import sync_claims

MAX_STREAK_HOPS = 5


async def _load_previous(db, workspace: Workspace) -> Optional[ThesisVersion]:
    if not workspace.current_thesis_version_id:
        return None
    result = await db.execute(
        select(ThesisVersion).where(ThesisVersion.id == workspace.current_thesis_version_id)
    )
    return result.scalar_one_or_none()


async def _agreement_streak(db, workspace_id, new_version_number: int, new_signal: str) -> int:
    """
    Count consecutive prior versions (most recent first) that share new_signal.

    version_number is sequential per workspace, so the last MAX_STREAK_HOPS
    versions can be fetched with a single ranged query instead of walking
    previous_version_id one row at a time.
    """
    if new_version_number <= 1:
        return 0

    lower_bound = max(1, new_version_number - MAX_STREAK_HOPS)
    result = await db.execute(
        select(ThesisVersion.signal)
        .where(
            ThesisVersion.workspace_id == workspace_id,
            ThesisVersion.version_number >= lower_bound,
            ThesisVersion.version_number < new_version_number,
        )
        .order_by(ThesisVersion.version_number.desc())
    )
    signals_desc = [row[0] for row in result.all()]

    streak = 0
    for signal in signals_desc:
        if signal != new_signal:
            break
        streak += 1
    return streak


async def create_thesis_version(
    db,
    workspace: Workspace,
    research: WorkspaceResearch,
    state: AgentState,
    triggered_by: str = "user_query",
) -> ThesisVersion:
    previous = await _load_previous(db, workspace)
    version_number = workspace.thesis_version_count + 1

    signal = derive_signal(state)
    streak = await _agreement_streak(db, workspace.id, version_number, signal)
    conviction_score = compute_conviction(state, agreement_streak=streak)

    new_fields = {
        "signal": signal,
        "conviction_score": conviction_score,
        "confidence": state.confidence,
        "bull_case": state.bull_case or {},
        "bear_case": state.bear_case or {},
        "key_risks": state.key_risks,
        "key_assumptions": state.key_assumptions,
        "invalidation_conditions": state.invalidation_conditions,
        "known_unknowns": state.known_unknowns,
    }
    diff, is_major_change, change_type = compute_diff(previous, new_fields)
    lifecycle_stage = determine_lifecycle_stage(
        previous.lifecycle_stage if previous else "forming", change_type, version_number
    )

    evidence = state.evidence or {}
    agent_signals = {
        name: getattr(state, f"{name}_output").get("signal")
        for name in state.active_agents
        if getattr(state, f"{name}_output", None)
    }

    if previous is not None:
        previous.status = "superseded"

    thesis_version = ThesisVersion(
        workspace_id=workspace.id,
        research_id=research.id,
        version_number=version_number,
        triggered_by=triggered_by,
        trigger_query=state.query,
        signal=signal,
        recommendation=state.recommendation,
        explanation=state.explanation,
        conviction_score=conviction_score,
        confidence=state.confidence,
        bull_case=json.dumps(state.bull_case or {}),
        bear_case=json.dumps(state.bear_case or {}),
        key_risks=json.dumps(state.key_risks),
        key_assumptions=json.dumps(state.key_assumptions),
        invalidation_conditions=json.dumps(state.invalidation_conditions),
        known_unknowns=json.dumps(state.known_unknowns),
        evidence_source_count=evidence.get("total_sources", 0),
        evidence_coverage=evidence.get("coverage", "none"),
        evidence_providers=json.dumps({
            "you_com": evidence.get("you_com", {}).get("count", 0),
            "tavily": evidence.get("tavily", {}).get("count", 0),
        }),
        agent_signals=json.dumps(agent_signals),
        active_agents=json.dumps(state.active_agents),
        lifecycle_stage=lifecycle_stage,
        status="active",
        previous_version_id=previous.id if previous else None,
        diff=json.dumps(diff) if diff is not None else None,
        is_major_change=is_major_change,
        change_type=change_type,
    )
    db.add(thesis_version)
    await db.flush()  # assign thesis_version.id without committing the transaction

    breakdown = state.confidence_breakdown or {}
    db.add(ConfidenceSnapshot(
        workspace_id=workspace.id,
        thesis_version_id=thesis_version.id,
        confidence=state.confidence,
        conviction_score=conviction_score,
        signal=signal,
        data_quality=breakdown.get("data_quality", 0.0),
        signal_agreement=breakdown.get("signal_agreement", 0.0),
        evidence_boost=breakdown.get("evidence_boost", 0.0),
        evidence_sources=evidence.get("total_sources", 0),
    ))

    await sync_claims(db, workspace.id, thesis_version)

    workspace.current_thesis_version_id = thesis_version.id
    workspace.thesis_version_count = version_number
    workspace.thesis_lifecycle_stage = lifecycle_stage
    workspace.conviction_score = conviction_score
    workspace.thesis_signal = signal

    return thesis_version
