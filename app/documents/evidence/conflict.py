"""
Conflict Detection — finds evidence pairs that address the same topic
closely enough to potentially agree or disagree, then classifies each pair
as supports / contradicts / neutral.

Cost-bounded by design: classifying every possible pair with an LLM call
would be O(n^2) API calls per query. Instead:
  1. Candidate pairs are narrowed first by cosine similarity between
     evidence vectors >= evidence_conflict_threshold — pairs below that are
     about different things and can't meaningfully "conflict."
  2. All surviving candidate pairs are classified in a SINGLE llm_json call
     (app/core/llm.py, the same helper app/agents/debate.py already uses
     for exactly this kind of structured judgment), not one call per pair —
     bounding LLM cost to O(1) per EvidencePack regardless of how many
     candidate pairs exist.
  3. llm_json never raises (returns {} on any failure, per its own
     contract) — if that happens, every candidate pair is classified
     "neutral" rather than the pack construction failing. This is the
     existing error-handling convention every other agent already relies
     on, not a mock/simplified path invented here.

Evidence.supports / Evidence.conflicts_with are populated in place;
conflict_summary is returned separately for EvidencePack.conflict_summary.
"""
import json
from itertools import combinations

from app.core.config import get_settings
from app.core.llm import llm_json
from app.documents.evidence.models import Evidence
from app.documents.evidence.extractor import EvidenceVectors
from app.documents.retrieval.similarity import cosine_similarity

settings = get_settings()

_SYSTEM_PROMPT = (
    "You are a financial research analyst comparing pairs of evidence "
    "passages from SEC filings. For each numbered pair, decide whether "
    "passage B supports, contradicts, or is neutral toward passage A. "
    '"contradicts" means the passages state genuinely inconsistent facts '
    "or conclusions (e.g. differing figures for the same metric and "
    "period, or opposite directional claims) — not just differing tone or "
    "coverage of different topics. Respond with JSON: "
    '{"pairs": [{"index": 0, "relationship": "supports"|"contradicts"|"neutral"}, ...]}. '
    "Include exactly one entry per pair index, in any order."
)


def _find_candidate_pairs(
    evidence_list: list[Evidence], vectors: EvidenceVectors, threshold: float
) -> list[tuple[Evidence, Evidence]]:
    pairs = []
    for a, b in combinations(evidence_list, 2):
        similarity = cosine_similarity(vectors.get(a.id, []), vectors.get(b.id, []))
        if similarity >= threshold:
            pairs.append((a, b))
    return pairs


def _build_pairs_prompt(pairs: list[tuple[Evidence, Evidence]]) -> str:
    lines = []
    for i, (a, b) in enumerate(pairs):
        lines.append(f"Pair {i}:\nA: {a.text[:600]}\nB: {b.text[:600]}\n")
    return "\n".join(lines)


async def detect_conflicts(
    evidence_list: list[Evidence], vectors: EvidenceVectors, threshold: float = None
) -> dict:
    """Returns conflict_summary; mutates evidence_list's .supports/.conflicts_with in place."""
    threshold = settings.evidence_conflict_threshold if threshold is None else threshold
    summary = {"pairs_checked": 0, "supports_count": 0, "contradicts_count": 0, "neutral_count": 0, "conflicting_pairs": []}

    if len(evidence_list) < 2:
        return summary

    candidate_pairs = _find_candidate_pairs(evidence_list, vectors, threshold)
    summary["pairs_checked"] = len(candidate_pairs)
    if not candidate_pairs:
        return summary

    response = await llm_json(_SYSTEM_PROMPT, _build_pairs_prompt(candidate_pairs))
    classifications = {item.get("index"): item.get("relationship") for item in response.get("pairs", [])}

    for i, (a, b) in enumerate(candidate_pairs):
        relationship = classifications.get(i, "neutral")
        if relationship == "contradicts":
            a.conflicts_with.append(b.id)
            b.conflicts_with.append(a.id)
            summary["contradicts_count"] += 1
            summary["conflicting_pairs"].append([str(a.id), str(b.id)])
        elif relationship == "supports":
            a.supports.append(b.id)
            b.supports.append(a.id)
            summary["supports_count"] += 1
        else:
            summary["neutral_count"] += 1

    return summary
