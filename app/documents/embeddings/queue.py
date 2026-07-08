"""
In-process embedding queue + background worker — asyncio.Queue +
asyncio.create_task, same pattern already used for SSE streaming in
app/routers/intelligence.py. No Celery/RQ/Redis broker: this is a
single-process monolith, and the existing codebase's "no infra until you
need it" philosophy (see CLAUDE.md) applies here too.

Known limitation, documented rather than hidden: ingest_document() doesn't
commit (commits are the caller's job — same convention as
create_thesis_version()), so there's a narrow window where the worker could
try to embed a chunk whose row isn't committed yet. embed_queue_batch()
retries the chunk fetch a few times with a short backoff before logging a
skip — acceptable for a dev-grade in-process queue, not pretended away.
"""
import asyncio
import logging
from dataclasses import dataclass
import uuid

logger = logging.getLogger(__name__)

_queue: asyncio.Queue = asyncio.Queue()


@dataclass
class EmbedQueueItem:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    text: str
    content_hash: str


async def enqueue(items: list[EmbedQueueItem]) -> None:
    for item in items:
        await _queue.put(item)


async def worker_loop(batch_size: int = 32) -> None:
    """Runs until cancelled. Drains up to batch_size items per iteration so
    one embedding-provider call embeds many chunks at once."""
    from app.core.database import SessionLocal
    from app.documents.embeddings.service import embed_queue_batch

    logger.info("Embedding worker started")
    while True:
        try:
            item = await _queue.get()
            batch = [item]
            while len(batch) < batch_size:
                try:
                    batch.append(_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break

            async with SessionLocal() as db:
                try:
                    embedded_count = await embed_queue_batch(db, batch)
                    await db.commit()
                    logger.info("Embedded %d/%d queued chunks", embedded_count, len(batch))
                except Exception:
                    await db.rollback()
                    logger.exception("Embedding batch failed (%d chunks) — continuing", len(batch))
        except asyncio.CancelledError:
            logger.info("Embedding worker stopped")
            raise
        except Exception:
            logger.exception("Embedding worker loop error — continuing")
