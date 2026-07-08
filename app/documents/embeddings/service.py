"""
EmbeddingService — turns queued (or directly requested) chunks into
DocumentEmbedding rows + the denormalized DocumentChunk cache columns, and
flips Document.status to "embedded" once a document's latest chunks are
fully embedded under the active provider/model.
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from app.documents.models.chunk import DocumentChunk
from app.documents.models.document import Document
from app.documents.models.embedding import DocumentEmbedding
from app.documents.embeddings.provider import get_embedding_provider
from app.documents.embeddings.queue import EmbedQueueItem
from app.documents.indexing import chunk_index

logger = logging.getLogger(__name__)

_CHUNK_FETCH_RETRIES = 3
_CHUNK_FETCH_BACKOFF_SECONDS = 0.5


async def _get_chunk_with_retry(db, chunk_id: uuid.UUID) -> Optional[DocumentChunk]:
    """See queue.py's module docstring: the enqueuing transaction may not be
    committed yet when the worker runs. A few short retries covers that
    narrow window without blocking the worker indefinitely on a truly
    missing/deleted chunk."""
    for attempt in range(_CHUNK_FETCH_RETRIES):
        chunk = await chunk_index.get_chunk(db, chunk_id)
        if chunk is not None:
            return chunk
        if attempt < _CHUNK_FETCH_RETRIES - 1:
            await asyncio.sleep(_CHUNK_FETCH_BACKOFF_SECONDS)
    return None


async def _mark_document_embedded_if_complete(db, document_id: uuid.UUID, provider: str, model: str) -> None:
    doc_result = await db.execute(select(Document).where(Document.id == document_id))
    document = doc_result.scalar_one_or_none()
    if document is None or document.status == "embedded":
        return

    chunks = await chunk_index.get_chunks_for_document(db, document_id)
    if not chunks:
        return

    embedded_result = await db.execute(
        select(DocumentEmbedding.chunk_id).where(
            DocumentEmbedding.document_id == document_id,
            DocumentEmbedding.provider == provider,
            DocumentEmbedding.model == model,
        )
    )
    embedded_chunk_ids = {row[0] for row in embedded_result.all()}
    if all(chunk.id in embedded_chunk_ids for chunk in chunks):
        document.status = "embedded"
        document.updated_at = datetime.now(timezone.utc)


async def embed_queue_batch(db, items: list[EmbedQueueItem], provider_name: Optional[str] = None) -> int:
    """Embeds a batch of queued chunks. Returns the count of chunks that
    actually required a provider API call (dedup hits don't count)."""
    provider = get_embedding_provider(provider_name)
    api_call_count = 0
    affected_documents: set[uuid.UUID] = set()

    # Resolve each item to a live chunk row first, so a missing/late-committed
    # chunk is skipped rather than crashing the whole batch.
    resolved: list[tuple[EmbedQueueItem, DocumentChunk]] = []
    for item in items:
        chunk = await _get_chunk_with_retry(db, item.chunk_id)
        if chunk is None:
            logger.warning("Skipping embed for missing chunk_id=%s", item.chunk_id)
            continue
        resolved.append((item, chunk))

    # Dedup: identical chunk text embedded once, reused across chunks/documents.
    texts_to_embed: list[str] = []
    text_index_by_hash: dict[str, int] = {}
    plan: list[tuple[EmbedQueueItem, DocumentChunk, Optional[int]]] = []  # index into texts_to_embed, or None if deduped

    for item, chunk in resolved:
        existing = await chunk_index.find_embedding_by_content_hash(
            db, item.content_hash, provider.provider_name, provider.model_name
        )
        if existing is not None:
            plan.append((item, chunk, None))
            await _upsert_embedding_row(db, chunk, item, provider, existing.vector_array())
            affected_documents.add(item.document_id)
            continue

        if item.content_hash in text_index_by_hash:
            plan.append((item, chunk, text_index_by_hash[item.content_hash]))
        else:
            text_index_by_hash[item.content_hash] = len(texts_to_embed)
            plan.append((item, chunk, len(texts_to_embed)))
            texts_to_embed.append(item.text)

    if texts_to_embed:
        vectors = await provider.embed_texts(texts_to_embed)
        api_call_count = len(texts_to_embed)

        for item, chunk, text_idx in plan:
            if text_idx is None:
                continue
            await _upsert_embedding_row(db, chunk, item, provider, vectors[text_idx])
            affected_documents.add(item.document_id)

    await db.flush()
    for document_id in affected_documents:
        await _mark_document_embedded_if_complete(db, document_id, provider.provider_name, provider.model_name)

    return api_call_count


async def _upsert_embedding_row(db, chunk: DocumentChunk, item: EmbedQueueItem, provider, vector: list[float]) -> None:
    """True upsert on (chunk_id, provider, model) — makes re-embedding an
    already-embedded chunk (e.g. a repeated POST .../embed) idempotent
    instead of hitting the table's unique constraint."""
    vector_json = json.dumps(vector)

    existing_row = await chunk_index.get_embedding(db, chunk.id, provider.provider_name, provider.model_name)
    if existing_row is not None:
        existing_row.vector = vector_json
        existing_row.dimension = len(vector)
        existing_row.content_hash = item.content_hash
    else:
        db.add(
            DocumentEmbedding(
                chunk_id=chunk.id,
                document_id=item.document_id,
                provider=provider.provider_name,
                model=provider.model_name,
                dimension=len(vector),
                vector=vector_json,
                content_hash=item.content_hash,
            )
        )

    # Denormalized "currently active embedding" cache on DocumentChunk itself
    # — see app/documents/models/embedding.py's module docstring for why.
    chunk.embedding = vector_json
    chunk.embedding_model = provider.model_name
    chunk.embedding_dim = len(vector)


async def embed_document_sync(db, document_id: uuid.UUID, provider_name: Optional[str] = None) -> dict:
    """Synchronous path for POST /documents/{id}/embed?wait=true — embeds
    inline rather than enqueuing, so the caller sees the result immediately."""
    chunks = await chunk_index.get_chunks_for_document(db, document_id)
    if not chunks:
        return {"document_id": str(document_id), "status": "no_chunks", "chunks_total": 0, "chunks_embedded": 0}

    items = [
        EmbedQueueItem(chunk_id=c.id, document_id=document_id, text=c.text, content_hash=c.content_hash)
        for c in chunks
    ]
    embedded_count = await embed_queue_batch(db, items, provider_name=provider_name)

    provider = get_embedding_provider(provider_name)
    return {
        "document_id": str(document_id),
        "status": "embedded",
        "chunks_total": len(chunks),
        "chunks_embedded": embedded_count,
        "provider": provider.provider_name,
        "model": provider.model_name,
    }
