"""
Evidence Deduplication — semantic near-duplicate removal.

Identical chunks are not handled as a separate exact-match pass: two
identical texts embed to (near-)identical vectors, so cosine similarity
between them is ~1.0 — the single near-duplicate threshold check below
already catches "identical" as the extreme case of "near-duplicate,"
without a second code path.

Greedy, score-ordered: evidence is sorted by EvidenceScore.overall
descending, then each item is kept unless it's within
evidence_dedupe_threshold cosine similarity of an already-kept (i.e.
higher-or-equal-scoring) item — this is what "preserve highest quality
evidence" means in practice: the survivor of any near-duplicate cluster is
always its highest-scoring member, never an arbitrary/first-seen one.
"""
from app.core.config import get_settings
from app.documents.evidence.models import Evidence
from app.documents.evidence.extractor import EvidenceVectors
from app.documents.retrieval.similarity import cosine_similarity

settings = get_settings()


def deduplicate(
    evidence_list: list[Evidence], vectors: EvidenceVectors, threshold: float = None
) -> tuple[list[Evidence], EvidenceVectors, int]:
    """Returns (surviving_evidence, surviving_vectors, duplicates_removed_count)."""
    if not evidence_list:
        return [], {}, 0

    threshold = settings.evidence_dedupe_threshold if threshold is None else threshold
    ordered = sorted(evidence_list, key=lambda e: e.score.overall, reverse=True)

    kept: list[Evidence] = []
    removed_count = 0
    for candidate in ordered:
        candidate_vector = vectors.get(candidate.id, [])
        is_duplicate = any(
            cosine_similarity(candidate_vector, vectors.get(kept_item.id, [])) >= threshold
            for kept_item in kept
        )
        if is_duplicate:
            removed_count += 1
            continue
        kept.append(candidate)

    surviving_vectors = {e.id: vectors[e.id] for e in kept if e.id in vectors}
    return kept, surviving_vectors, removed_count
