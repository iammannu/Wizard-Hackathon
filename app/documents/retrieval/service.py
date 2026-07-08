"""
Top-level retrieval orchestration.

Milestone 2 (Evidence Engine 2.0) changed what `search()` returns: it now
runs the full evidence pipeline (app/documents/evidence/service.py) and
returns an EvidencePack, not a list[RetrievedChunk] — this is what
POST /retrieval/query and app.agents.base.search_evidence() consume.

The original Milestone 1 chunk-level pipeline (hybrid -> MMR -> hydrate ->
optional context packing) is preserved as search_chunks() rather than
removed: GET /documents/search only needs one best-scoring snippet per
document, and doesn't warrant paying for evidence scoring, dedup, conflict
detection, or claim-synthesis LLM calls just to render a snippet list —
search_documents() below still calls search_chunks(), unchanged.
"""
import uuid
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select

from app.documents.models.chunk import DocumentChunk
from app.documents.models.document import Document
from app.documents.embeddings.provider import get_embedding_provider
from app.documents.retrieval.hybrid import hybrid_candidates
from app.documents.retrieval.mmr import mmr_rerank
from app.documents.retrieval.context_packer import pack_context
from app.documents.evidence.service import build_evidence_pack
from app.documents.evidence.models import EvidencePack
from app.core.config import get_settings

settings = get_settings()


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    ticker: Optional[str]
    doc_type: str
    section: Optional[str]
    text: str
    score: float
    # Lightweight derivation (external_id + chunk position) — kept simple
    # here since search_chunks() only backs the lightweight /documents/search
    # snippet endpoint. app/documents/evidence/citations.py builds the same
    # scheme for the full Evidence Engine (Milestone 2) pipeline.
    citation_id: str = field(default="")


async def _hydrate(db, scored) -> list[RetrievedChunk]:
    """Join DocumentChunk + Document metadata onto the ranked chunk_ids,
    preserving the incoming (already-ranked) order."""
    if not scored:
        return []
    chunk_ids = [s.chunk_id for s in scored]
    result = await db.execute(
        select(DocumentChunk, Document)
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(DocumentChunk.id.in_(chunk_ids))
    )
    rows = {chunk.id: (chunk, doc) for chunk, doc in result.all()}

    hydrated: list[RetrievedChunk] = []
    for s in scored:
        pair = rows.get(s.chunk_id)
        if not pair:
            continue
        chunk, doc = pair
        hydrated.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=doc.id,
                document_title=doc.title,
                ticker=doc.ticker,
                doc_type=doc.doc_type,
                section=chunk.section,
                text=chunk.text,
                score=s.score,
                citation_id=f"{doc.external_id}#chunk-{chunk.chunk_index}",
            )
        )
    return hydrated


async def search_chunks(
    db,
    query: str,
    ticker: Optional[str] = None,
    doc_type: Optional[str] = None,
    provider_source: Optional[str] = None,
    document_ids: Optional[list[uuid.UUID]] = None,
    top_k: Optional[int] = None,
    max_context_tokens: Optional[int] = None,
    use_mmr: bool = True,
    mmr_lambda: float = 0.5,
) -> list[RetrievedChunk]:
    """The Milestone 1 chunk-level pipeline — see module docstring for why
    this is kept alongside the new evidence-pack search()."""
    top_k = top_k or settings.retrieval_top_k_default

    provider = get_embedding_provider()
    query_vector = await provider.embed_query(query)

    candidates = await hybrid_candidates(
        db, query, query_vector, ticker=ticker, doc_type=doc_type,
        provider_source=provider_source, document_ids=document_ids,
    )
    if not candidates:
        return []

    ranked = mmr_rerank(candidates, top_k=top_k, lambda_mult=mmr_lambda) if use_mmr else candidates[:top_k]
    hydrated = await _hydrate(db, ranked)

    if max_context_tokens:
        hydrated = pack_context(hydrated, max_tokens=max_context_tokens)
    return hydrated


async def search(
    db,
    query: str,
    ticker: Optional[str] = None,
    doc_type: Optional[str] = None,
    provider_source: Optional[str] = None,
    document_ids: Optional[list[uuid.UUID]] = None,
    top_k: Optional[int] = None,
    max_context_tokens: Optional[int] = None,
    use_mmr: bool = True,
    mmr_lambda: float = 0.5,
) -> EvidencePack:
    """Milestone 2 entry point: the full evidence pipeline (extraction ->
    scoring -> dedup -> conflict detection -> claim building -> citation
    building), returning a structured EvidencePack rather than raw chunks.
    This is what POST /retrieval/query and app.agents.base.search_evidence()
    call. For the old chunk-level shape, use search_chunks()."""
    return await build_evidence_pack(
        db, query, ticker=ticker, doc_type=doc_type, provider_source=provider_source,
        document_ids=document_ids, top_k=top_k, use_mmr=use_mmr, mmr_lambda=mmr_lambda,
        max_context_tokens=max_context_tokens,
    )


async def search_documents(
    db,
    query: str,
    ticker: Optional[str] = None,
    doc_type: Optional[str] = None,
    provider_source: Optional[str] = None,
    limit: int = 10,
) -> list[dict]:
    """Document-level search: runs the same embed+hybrid+MMR path, then
    keeps only each document's single best-scoring chunk as a snippet."""
    results = await search_chunks(
        db, query, ticker=ticker, doc_type=doc_type, provider_source=provider_source,
        top_k=max(limit * 5, 50),  # over-fetch chunks so limit documents actually get filled in
        use_mmr=False,
    )

    best_per_document: dict[uuid.UUID, RetrievedChunk] = {}
    for chunk in results:
        existing = best_per_document.get(chunk.document_id)
        if existing is None or chunk.score > existing.score:
            best_per_document[chunk.document_id] = chunk

    ranked_documents = sorted(best_per_document.values(), key=lambda c: c.score, reverse=True)[:limit]
    return [
        {
            "document_id": str(c.document_id),
            "title": c.document_title,
            "ticker": c.ticker,
            "doc_type": c.doc_type,
            "best_chunk_id": str(c.chunk_id),
            "best_snippet": c.text[:500],
            "score": c.score,
        }
        for c in ranked_documents
    ]
