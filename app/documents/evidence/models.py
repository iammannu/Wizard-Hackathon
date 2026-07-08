"""
Evidence domain models — Milestone 2 (Evidence Engine 2.0).

Pydantic, not dataclasses: unlike app/documents/retrieval/'s internal
ScoredChunk/RetrievedChunk (dataclasses, never leave that module's
pipeline), these objects cross the retrieval -> agent -> API boundary —
agents consume them as structured objects (app/agents/base.py's
search_evidence()) and POST /retrieval/query serializes them directly as
the response body. Pydantic gives typed validation and JSON serialization
for both for free, which a dataclass doesn't.

Raw embedding vectors are deliberately NOT a field on any of these models —
they're an internal implementation detail of scoring/dedup/conflict
detection (see app/documents/evidence/extractor.py's return shape), and
serializing a 1536-float array per Evidence item into every API response
would be pure waste for a consumer that only wants text + score + citation.
"""
import uuid
from datetime import date, datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class RetrievalMetadata(BaseModel):
    """What was asked for and how the candidate set was produced — the
    "how was this evidence found" record that travels with an EvidencePack."""

    query: str
    ticker: Optional[str] = None
    doc_type: Optional[str] = None
    provider_source: Optional[str] = None
    top_k: int
    use_mmr: bool
    mmr_lambda: float
    hybrid_candidate_count: int
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Citation(BaseModel):
    """Everything needed to point a human or another system at the exact
    primary-source passage an Evidence item came from."""

    citation_id: str
    document_id: uuid.UUID
    document_title: str
    external_id: str  # SEC accession number (or provider-specific natural key)
    chunk_id: uuid.UUID
    page: Optional[int] = None
    section: Optional[str] = None
    provider: str  # provider_source, e.g. "sec_edgar"
    version: int  # the document_version_number this chunk was extracted from
    url: Optional[str] = None


class EvidenceScore(BaseModel):
    """Eight weighted factors (app/documents/evidence/scorer.py), each
    normalized to [0, 1]. `overall` is the weighted sum used for ranking,
    dedup tie-breaking, and confidence calculation — see
    Settings.evidence_weight_* in app/core/config.py for the weights."""

    semantic_similarity: float = 0.0
    keyword_overlap: float = 0.0
    section_importance: float = 0.0
    recency: float = 0.0
    authority: float = 0.0
    source_quality: float = 0.0
    completeness: float = 0.0
    citation_density: float = 0.0
    overall: float = 0.0


class Evidence(BaseModel):
    """One retrieved, scored chunk — the atomic unit the rest of the
    Evidence Engine operates on (dedup, conflict detection, claim
    building all consume/produce lists of these)."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    ticker: Optional[str] = None
    doc_type: str
    section: Optional[str] = None
    filing_date: Optional[date] = None
    text: str
    citation: Citation
    score: EvidenceScore = Field(default_factory=EvidenceScore)
    # Other Evidence.id values this item agrees/disagrees with — populated
    # by app/documents/evidence/conflict.py, empty until that stage runs.
    supports: list[uuid.UUID] = Field(default_factory=list)
    conflicts_with: list[uuid.UUID] = Field(default_factory=list)


class Claim(BaseModel):
    """An LLM-synthesized statement backed by one or more Evidence items —
    see app/documents/evidence/claims.py. Confidence and contradictions are
    derived from the supporting evidence's scores and conflict edges, not
    asserted independently."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    text: str
    supporting_evidence_ids: list[uuid.UUID]
    citations: list[Citation]
    confidence: float
    contradictions: list[uuid.UUID] = Field(default_factory=list)


class EvidencePack(BaseModel):
    """The structured output of the full retrieval pipeline (Milestone 2)
    — replaces the old list[RetrievedChunk] as what
    app.agents.base.search_evidence() and POST /retrieval/query return."""

    query: str
    evidence: list[Evidence]
    claims: list[Claim]
    citations: list[Citation]
    confidence: float
    metadata: RetrievalMetadata
    retrieval_stats: dict
    conflict_summary: dict
