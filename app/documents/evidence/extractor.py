"""
Evidence Extraction — converts post-MMR ScoredChunks into Evidence objects.

Responsibilities (per Milestone 2 spec):
  - converting retrieved chunks into evidence objects
  - extracting metadata (document title/ticker/doc_type/section/page)
  - preserving document hierarchy (document -> version -> chunk, via the
    3-way join below)
  - preserving chunk ids (Evidence.chunk_id, Citation.chunk_id)
  - attaching document version (Citation.version — the actual
    DocumentVersion.version_number this specific chunk belongs to, not just
    Document.latest_version_number, since document_chunks accumulates rows
    across versions and a retrieved chunk may not be from the latest one)

Embedding vectors are returned alongside the Evidence list, keyed by
Evidence.id, rather than stored on the Evidence model itself — see
models.py's module docstring for why. Every downstream stage (scorer,
deduplication, conflict detection) takes and returns this same
(evidence_list, vectors) shape.
"""
import uuid

from sqlalchemy import select

from app.documents.models.chunk import DocumentChunk
from app.documents.models.document import Document, DocumentVersion
from app.documents.evidence.models import Evidence, EvidenceScore
from app.documents.evidence.citations import build_citation
from app.documents.retrieval.vector_store import ScoredChunk

EvidenceVectors = dict[uuid.UUID, list[float]]


async def extract_evidence(db, scored_chunks: list[ScoredChunk]) -> tuple[list[Evidence], EvidenceVectors]:
    if not scored_chunks:
        return [], {}

    chunk_ids = [s.chunk_id for s in scored_chunks]
    result = await db.execute(
        select(DocumentChunk, Document, DocumentVersion)
        .join(Document, DocumentChunk.document_id == Document.id)
        .join(DocumentVersion, DocumentChunk.document_version_id == DocumentVersion.id)
        .where(DocumentChunk.id.in_(chunk_ids))
    )
    rows = {chunk.id: (chunk, document, version) for chunk, document, version in result.all()}

    evidence_list: list[Evidence] = []
    vectors: EvidenceVectors = {}

    for scored in scored_chunks:
        hydrated = rows.get(scored.chunk_id)
        if not hydrated:
            continue  # chunk deleted/moved between candidate selection and extraction — skip, don't crash the pack
        chunk, document, version = hydrated

        citation = build_citation(chunk, document, version.version_number)
        evidence = Evidence(
            chunk_id=chunk.id,
            document_id=document.id,
            document_title=document.title,
            ticker=document.ticker,
            doc_type=document.doc_type,
            section=chunk.section,
            filing_date=document.filing_date,
            text=chunk.text,
            citation=citation,
            score=EvidenceScore(),
        )
        evidence_list.append(evidence)
        if scored.vector:
            vectors[evidence.id] = scored.vector

    return evidence_list, vectors
