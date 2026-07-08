"""
Evidence Scoring — eight weighted factors, each normalized to [0, 1],
combined into EvidenceScore.overall via the configurable weights in
app/core/config.py (Settings.evidence_weight_*). Overall is what dedup,
conflict detection, claim building, and the final EvidencePack.confidence
all rank/aggregate on.

Factor definitions and why each is computed the way it is:

  semantic_similarity  Cosine(query_vector, evidence_vector) — recomputed
                       here rather than reusing hybrid.py's RRF-fused score,
                       because RRF scores are rank-based and not a
                       [0, 1]-comparable "how similar is this text" signal
                       (see hybrid.py's own docstring on why RRF was chosen
                       over raw-score normalization for fusion — the same
                       reasoning means it can't be reused as a factor here).

  keyword_overlap      Overlap coefficient (not Jaccard) between query and
                       chunk token sets: |intersection| / |query_tokens|.
                       Overlap coefficient is used instead of Jaccard because
                       a long chunk containing every query term shouldn't
                       score lower just for also containing many other
                       words — Jaccard's union term would punish chunk
                       length, which conflates "on topic" with "short."

  section_importance  Static lookup by SEC Item-numbering key (chunk.section,
                       e.g. "item_7" = MD&A). Domain knowledge: MD&A and
                       Financial Statements are where analysts actually find
                       decision-relevant facts; boilerplate legal/cover-page
                       sections are not. Unknown/generic sections
                       (_full_text, _preamble, non-10-K doc types) get a
                       neutral default rather than being penalized outright.

  recency              Linear decay from 1.0 (filed today) to 0.0 at
                       evidence_recency_decay_years old. Missing filing_date
                       (some Tier 2/3 doc types have none) scores a neutral
                       0.5 rather than 0 — absence of a date isn't evidence
                       of staleness.

  authority            Static lookup by provider_source. SEC EDGAR is the
                       ground-truth regulatory filing; press releases and
                       generic search-discovered pages are lower-authority
                       secondary sources — this is the same Tier 1/2/3
                       distinction already documented in
                       app/documents/providers/ and CLAUDE.md.

  source_quality       Static lookup by doc_type. A 10-K/10-Q is a far more
                       reliable, audited source than a Form 4 (a routine
                       insider-transaction filing) or a press release.

  completeness         Rewards chunks that read as a complete thought:
                       length ratio against the chunker's own
                       CHUNK_TOKEN_TARGET (reused, not reinvented — see
                       app/documents/chunking/chunker.py), plus a bonus if
                       the chunk ends on sentence-ending punctuation (not a
                       mid-sentence cut).

  citation_density     Proxy for "how fact-dense is this passage" — count of
                       numeric/currency/percentage tokens per 100 words.
                       Financial evidence dense with figures is more useful
                       to cite than a paragraph of qualitative narrative.
"""
import re
from datetime import date, datetime, timezone
from typing import Optional

from app.core.config import get_settings
from app.documents.chunking.chunker import CHUNK_TOKEN_TARGET, count_tokens
from app.documents.evidence.models import Evidence
from app.documents.evidence.extractor import EvidenceVectors
from app.documents.retrieval.similarity import cosine_similarity

settings = get_settings()

# SEC Item-numbering key -> importance. Anything not listed (generic
# doc types' "_full_text", "_preamble", or an unrecognized key) falls back
# to _DEFAULT_SECTION_IMPORTANCE.
_SECTION_IMPORTANCE = {
    "item_7": 1.00,   # MD&A — where analysts look first
    "item_8": 0.95,   # Financial Statements
    "item_1a": 0.90,  # Risk Factors
    "item_1": 0.80,   # Business
    "item_7a": 0.70,  # Quantitative/Qualitative Disclosures About Market Risk
    "item_3": 0.60,   # Legal Proceedings
    "item_5": 0.40,   # Market for Registrant's Common Equity
    "item_9a": 0.30,  # Controls and Procedures
    "_preamble": 0.20,
}
_DEFAULT_SECTION_IMPORTANCE = 0.50

# provider_source (app/documents/providers/) -> authority. Mirrors the
# Tier 1/2/3 source hierarchy already documented across app/documents/.
_AUTHORITY = {
    "sec_edgar": 1.00,
    "investor_relations": 0.80,
    "transcript": 0.70,
    "press_release": 0.60,
    "search_discovery": 0.40,
}
_DEFAULT_AUTHORITY = 0.50

# doc_type -> source quality. Audited/regulatory filings outrank routine or
# promotional documents.
_SOURCE_QUALITY = {
    "10-K": 1.00,
    "10-Q": 0.90,
    "8-K": 0.75,
    "DEF-14A": 0.65,
    "shareholder_letter": 0.60,
    "investor_presentation": 0.55,
    "management_commentary": 0.55,
    "transcript": 0.55,
    "press_release": 0.45,
    "FORM-4": 0.40,
    "FORM-13F": 0.40,
    "product_announcement": 0.35,
}
_DEFAULT_SOURCE_QUALITY = 0.50

_NUMERIC_TOKEN_RE = re.compile(r"[\$€£]?\d[\d,\.]*%?")
_SENTENCE_END_RE = re.compile(r"[.!?]\"?$")


def _keyword_overlap(query: str, text: str) -> float:
    query_tokens = set(query.lower().split())
    if not query_tokens:
        return 0.0
    text_tokens = set(text.lower().split())
    return len(query_tokens & text_tokens) / len(query_tokens)


def _section_importance(section: Optional[str]) -> float:
    if not section:
        return _DEFAULT_SECTION_IMPORTANCE
    return _SECTION_IMPORTANCE.get(section.lower(), _DEFAULT_SECTION_IMPORTANCE)


def _recency(filing_date: Optional[date]) -> float:
    if filing_date is None:
        return 0.5
    age_years = (datetime.now(timezone.utc).date() - filing_date).days / 365.25
    decay_years = max(settings.evidence_recency_decay_years, 0.01)
    return max(0.0, 1.0 - age_years / decay_years)


def _authority(provider_source: str) -> float:
    return _AUTHORITY.get(provider_source, _DEFAULT_AUTHORITY)


def _source_quality(doc_type: str) -> float:
    return _SOURCE_QUALITY.get(doc_type, _DEFAULT_SOURCE_QUALITY)


def _completeness(text: str) -> float:
    length_ratio = min(count_tokens(text) / CHUNK_TOKEN_TARGET, 1.0)
    boundary_bonus = 1.0 if _SENTENCE_END_RE.search(text.strip()) else 0.8
    return length_ratio * boundary_bonus


def _citation_density(text: str) -> float:
    word_count = max(len(text.split()), 1)
    numeric_count = len(_NUMERIC_TOKEN_RE.findall(text))
    density_per_100_words = (numeric_count / word_count) * 100
    # 8+ numeric tokens per 100 words is treated as maximally fact-dense —
    # financial prose rarely exceeds this without becoming a data table.
    return min(density_per_100_words / 8.0, 1.0)


def score_evidence(
    evidence_list: list[Evidence], vectors: EvidenceVectors, query: str, query_vector: list[float]
) -> list[Evidence]:
    """Mutates and returns evidence_list with .score populated on each item."""
    for evidence in evidence_list:
        semantic_similarity = cosine_similarity(query_vector, vectors.get(evidence.id, []))
        # Cosine can be slightly negative for near-orthogonal vectors;
        # clamp into [0, 1] since every other factor is already in that range.
        semantic_similarity = max(0.0, semantic_similarity)

        keyword_overlap = _keyword_overlap(query, evidence.text)
        section_importance = _section_importance(evidence.section)
        recency = _recency(evidence.filing_date)
        authority = _authority(evidence.citation.provider)
        source_quality = _source_quality(evidence.doc_type)
        completeness = _completeness(evidence.text)
        citation_density = _citation_density(evidence.text)

        overall = (
            settings.evidence_weight_semantic_similarity * semantic_similarity
            + settings.evidence_weight_keyword_overlap * keyword_overlap
            + settings.evidence_weight_section_importance * section_importance
            + settings.evidence_weight_recency * recency
            + settings.evidence_weight_authority * authority
            + settings.evidence_weight_source_quality * source_quality
            + settings.evidence_weight_completeness * completeness
            + settings.evidence_weight_citation_density * citation_density
        )

        evidence.score.semantic_similarity = semantic_similarity
        evidence.score.keyword_overlap = keyword_overlap
        evidence.score.section_importance = section_importance
        evidence.score.recency = recency
        evidence.score.authority = authority
        evidence.score.source_quality = source_quality
        evidence.score.completeness = completeness
        evidence.score.citation_density = citation_density
        evidence.score.overall = max(0.0, min(overall, 1.0))

    return evidence_list
