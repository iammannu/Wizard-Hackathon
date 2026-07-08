"""
Chunk-level read queries — the chunk-scoped counterpart to document_index.py.

Same rationale as that module: ingestion, the embedding worker, and the
retrieval layer all need the same lookups ("chunks for this document",
"does this chunk already have an embedding"), so they're centralized here
instead of each caller hand-rolling `select(DocumentChunk).where(...)`.

No ORM relationship() is used anywhere in this codebase (async-session
eager-load complexity) — joins are written out manually, same convention
as document_index.py.
"""
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.models.chunk import DocumentChunk
from app.documents.models.document import Document
from app.documents.models.embedding import DocumentEmbedding


async def get_chunks_for_document(
    db: AsyncSession, document_id: uuid.UUID, version_id: Optional[uuid.UUID] = None
) -> list[DocumentChunk]:
    """Chunks for one document. Defaults to the document's latest version."""
    if version_id is None:
        doc_result = await db.execute(select(Document.latest_version_id).where(Document.id == document_id))
        version_id = doc_result.scalar_one_or_none()
        if version_id is None:
            return []

    result = await db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_version_id == version_id)
        .order_by(DocumentChunk.chunk_index)
    )
    return list(result.scalars().all())


async def get_chunk(db: AsyncSession, chunk_id: uuid.UUID) -> Optional[DocumentChunk]:
    result = await db.execute(select(DocumentChunk).where(DocumentChunk.id == chunk_id))
    return result.scalar_one_or_none()


async def get_embedding(
    db: AsyncSession, chunk_id: uuid.UUID, provider: str, model: str
) -> Optional[DocumentEmbedding]:
    result = await db.execute(
        select(DocumentEmbedding).where(
            DocumentEmbedding.chunk_id == chunk_id,
            DocumentEmbedding.provider == provider,
            DocumentEmbedding.model == model,
        )
    )
    return result.scalar_one_or_none()


async def find_embedding_by_content_hash(
    db: AsyncSession, content_hash: str, provider: str, model: str
) -> Optional[DocumentEmbedding]:
    """Any existing embedding for identical chunk text under this
    (provider, model) — the dedup path so repeated boilerplate (legal
    language repeated across every 10-K, for instance) is embedded once."""
    result = await db.execute(
        select(DocumentEmbedding)
        .where(
            DocumentEmbedding.content_hash == content_hash,
            DocumentEmbedding.provider == provider,
            DocumentEmbedding.model == model,
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_candidate_chunks(
    db: AsyncSession,
    ticker: Optional[str] = None,
    doc_type: Optional[str] = None,
    provider_source: Optional[str] = None,
    document_ids: Optional[list[uuid.UUID]] = None,
    limit: int = 500,
) -> list[tuple[DocumentChunk, Document]]:
    """Metadata-filtered candidate set for hybrid search — bounded so a
    query never has to BM25-rank or cosine-scan the entire table."""
    query = select(DocumentChunk, Document).join(Document, DocumentChunk.document_id == Document.id)
    if ticker:
        query = query.where(Document.ticker == ticker.upper())
    if doc_type:
        query = query.where(Document.doc_type == doc_type)
    if provider_source:
        query = query.where(Document.provider_source == provider_source)
    if document_ids:
        query = query.where(DocumentChunk.document_id.in_(document_ids))
    query = query.limit(limit)

    result = await db.execute(query)
    return [(row[0], row[1]) for row in result.all()]


async def get_chunks_needing_embedding(
    db: AsyncSession, provider: str, model: str, limit: int = 500
) -> list[DocumentChunk]:
    """Chunks with no document_embeddings row yet for (provider, model) —
    a backfill query for a manual re-embed-all pass, not the normal
    per-ingest hook (that enqueues chunks directly at creation time)."""
    embedded_chunk_ids = select(DocumentEmbedding.chunk_id).where(
        DocumentEmbedding.provider == provider, DocumentEmbedding.model == model
    )
    result = await db.execute(
        select(DocumentChunk).where(DocumentChunk.id.not_in(embedded_chunk_ids)).limit(limit)
    )
    return list(result.scalars().all())
