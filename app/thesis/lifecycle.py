"""
Lifecycle stage state machine for a workspace's thesis.

Why it exists:
  lifecycle_stage is the single field the UI and future alerting (Phase 5/6)
  key off to answer "is this thesis still forming, battle-tested, or in
  trouble?" It has to be a small deterministic state machine, not a label
  copied from the latest change_type, so that one good version after a
  challenge doesn't instantly relabel a shaky thesis "established".

How it integrates:
  app/thesis/versioner.py calls determine_lifecycle_stage(previous_stage,
  change_type, version_number) after comparator.py has classified the change.

States: forming -> established -> evolving -> challenged -> invalidated
  - forming:      version 1, or too young to have proven anything yet.
  - established:  signal has been reinforced across enough versions.
  - evolving:      thesis content is shifting but direction hasn't reversed.
  - challenged:   conviction has meaningfully weakened.
  - invalidated:  the directional call flipped without enough new conviction
                  to back the reversal.

Future extension points:
  - ESTABLISHED_AFTER_VERSIONS is a static threshold; Phase 8 (Prediction
    Tracking) could instead require a minimum number of *falsified*
    invalidation_conditions before granting "established".
"""

ESTABLISHED_AFTER_VERSIONS = 3


def determine_lifecycle_stage(previous_stage: str, change_type: str | None, version_number: int) -> str:
    if version_number == 1 or change_type is None:
        return "forming"

    if change_type == "invalidated":
        return "invalidated"

    if change_type == "challenged":
        return "challenged"

    if change_type == "evolved":
        return "evolving"

    # change_type == "reinforced"
    if previous_stage == "challenged":
        # Recovering from a challenge takes one more confirmation before
        # being trusted as "established" again.
        return "evolving"
    if previous_stage in ("forming", "evolving"):
        return "established" if version_number >= ESTABLISHED_AFTER_VERSIONS else previous_stage

    # already established and reinforced again — stays established
    return "established"
