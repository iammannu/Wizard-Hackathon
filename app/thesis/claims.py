"""
Atomic claim extraction + longitudinal tracking.

Why it exists:
  A thesis is a bundle of individually falsifiable claims (a bull point, a
  risk, an assumption...). Tracking the *thesis* as a blob only tells you the
  headline changed; tracking *claims* tells you which specific belief held up
  across research runs and which one quietly disappeared. That's the input
  Phase 2 (AI Memory) needs to promote durable claims into long-term memory.

How it integrates:
  app/thesis/versioner.py calls sync_claims(db, workspace_id, thesis_version)
  after the ThesisVersion row is flushed (so thesis_version.id/version_number
  exist). It reads/writes ThesisClaim rows directly — no ORM relationships,
  per the project convention for async sessions.

Matching strategy (deterministic, Phase 1):
  Claims are matched by (normalized claim_text, claim_type) within a
  workspace. Exact-after-normalization matching is cheap, has no false
  positives, and is good enough while thesis history is shallow. Semantic
  matching (e.g. "EU regulatory risk" == "regulation in Europe") is a Phase 2
  candidate once embeddings are already in the stack for AI Memory — adding
  a vector call here today would be exactly the kind of unnecessary LLM/embedding
  call the project explicitly avoids.

Refutation heuristic (deterministic, Phase 1):
  A claim is marked "refuted" only when it stops appearing AND the thesis's
  overall signal has fully flipped (bull_point claims refuted by a flip to
  bearish, and vice versa) — i.e. refutation is tied to a confirmed
  directional reversal, not per-claim negation detection, which would require
  real semantic reasoning. A claim that merely stops appearing without a
  signal flip is "weakened", not "refuted".

Future extension points:
  - ThesisClaim.memory_id gets populated here once Phase 2 adds MemoryEntry:
    claims reaching status="confirmed" (appearance_count >= 3) are the
    promotion candidates.
"""
import re
from sqlalchemy import select
from app.models.thesis import ThesisClaim, ThesisVersion

WEAKENED_AFTER_MISSED_VERSIONS = 2
CONFIRMED_AFTER_APPEARANCES = 3

_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]")


def _normalize(text: str) -> str:
    text = _PUNCT_RE.sub("", text.lower())
    return _WHITESPACE_RE.sub(" ", text).strip()


def extract_claims(new_fields: dict) -> list[dict]:
    """new_fields: same dict shape passed to comparator.compute_diff."""
    claims: list[dict] = []
    bull_prob = (new_fields["bull_case"] or {}).get("probability", 0.5)
    bear_prob = (new_fields["bear_case"] or {}).get("probability", 0.5)

    for point in (new_fields["bull_case"] or {}).get("key_points", []):
        claims.append({"claim_type": "bull_point", "claim_text": point, "claim_confidence": bull_prob})
    for point in (new_fields["bear_case"] or {}).get("key_points", []):
        claims.append({"claim_type": "bear_point", "claim_text": point, "claim_confidence": bear_prob})
    for risk in new_fields["key_risks"]:
        claims.append({"claim_type": "risk", "claim_text": risk, "claim_confidence": 0.6})
    for assumption in new_fields["key_assumptions"]:
        claims.append({"claim_type": "assumption", "claim_text": assumption, "claim_confidence": 0.5})
    for cond in new_fields["invalidation_conditions"]:
        claims.append({"claim_type": "invalidation_condition", "claim_text": cond, "claim_confidence": 0.5})
    for unknown in new_fields["known_unknowns"]:
        claims.append({"claim_type": "known_unknown", "claim_text": unknown, "claim_confidence": 0.3})

    return [c for c in claims if c["claim_text"] and c["claim_text"].strip()]


async def sync_claims(db, workspace_id, thesis_version: ThesisVersion) -> None:
    """Upsert ThesisClaim rows for the newly created thesis_version."""
    extracted = extract_claims({
        "bull_case": thesis_version.bull_case_dict(),
        "bear_case": thesis_version.bear_case_dict(),
        "key_risks": thesis_version.key_risks_list(),
        "key_assumptions": thesis_version.key_assumptions_list(),
        "invalidation_conditions": thesis_version.invalidation_conditions_list(),
        "known_unknowns": thesis_version.known_unknowns_list(),
    })

    # De-dupe within this run's own extraction first. The synthesis LLM can
    # (rarely) restate the same point under two fields — e.g. a risk repeated
    # as an invalidation condition — and without this the upsert loop below
    # would insert two ThesisClaim rows for one appearance-key on the same
    # version, since the "already seen" check only guards against rows that
    # existed *before* this run.
    deduped: dict[tuple[str, str], dict] = {}
    for item in extracted:
        key = (_normalize(item["claim_text"]), item["claim_type"])
        deduped.setdefault(key, item)
    extracted = list(deduped.values())

    result = await db.execute(
        select(ThesisClaim).where(
            ThesisClaim.workspace_id == workspace_id,
            ThesisClaim.status != "refuted",
        )
    )
    existing = result.scalars().all()
    existing_by_key = {(_normalize(c.claim_text), c.claim_type): c for c in existing}

    seen_keys = set()
    for item in extracted:
        key = (_normalize(item["claim_text"]), item["claim_type"])
        seen_keys.add(key)
        existing_claim = existing_by_key.get(key)

        if existing_claim is None:
            db.add(ThesisClaim(
                workspace_id=workspace_id,
                thesis_version_id=thesis_version.id,
                claim_type=item["claim_type"],
                claim_text=item["claim_text"],
                claim_confidence=item["claim_confidence"],
                first_version=thesis_version.version_number,
                last_confirmed_version=thesis_version.version_number,
                appearance_count=1,
                status="active",
            ))
            continue

        existing_claim.thesis_version_id = thesis_version.id
        existing_claim.last_confirmed_version = thesis_version.version_number
        existing_claim.appearance_count += 1
        existing_claim.claim_confidence = item["claim_confidence"]
        if existing_claim.appearance_count >= CONFIRMED_AFTER_APPEARANCES:
            existing_claim.status = "confirmed"
        elif existing_claim.status not in ("confirmed",):
            existing_claim.status = "strengthened" if existing_claim.appearance_count >= 2 else "active"

    # Claims that didn't reappear this version: weaken or refute based on gap.
    signal_flipped_bull_to_bear = thesis_version.signal == "bearish"
    signal_flipped_bear_to_bull = thesis_version.signal == "bullish"

    for key, claim in existing_by_key.items():
        if key in seen_keys:
            continue
        gap = thesis_version.version_number - claim.last_confirmed_version
        if gap < 1:
            continue

        refuted = (
            (claim.claim_type == "bull_point" and signal_flipped_bull_to_bear) or
            (claim.claim_type == "bear_point" and signal_flipped_bear_to_bull)
        )
        if refuted:
            claim.status = "refuted"
        elif gap >= WEAKENED_AFTER_MISSED_VERSIONS and claim.status != "weakened":
            claim.status = "weakened"
