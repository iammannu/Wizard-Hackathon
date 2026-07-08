"""
Documents router — embedding trigger + document-level semantic search.
Ingestion itself (SEC EDGAR discover/fetch/chunk) has no HTTP trigger yet;
these endpoints operate on documents already ingested via
app.documents.services.ingestion_service.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.database import get_db
from app.documents.indexing import document_index
from app.documents.embeddings.service import embed_document_sync
from app.documents.embeddings.queue import EmbedQueueItem, enqueue
from app.documents.indexing import chunk_index
from app.documents.retrieval import service as retrieval_service

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


class EmbedDocumentRequest(BaseModel):
    provider: Optional[str] = None
    wait: bool = False


@router.post("/{document_id}/embed")
async def embed_document(document_id: str, body: EmbedDocumentRequest = EmbedDocumentRequest()):
    doc_uuid = _parse_document_id(document_id)

    async for db in get_db():
        document = await document_index.get_document(db, doc_uuid)
        if not document:
            raise HTTPException(404, "Document not found")

        if body.wait:
            result = await embed_document_sync(db, doc_uuid, provider_name=body.provider)
            await db.commit()
            return result

        chunks = await chunk_index.get_chunks_for_document(db, doc_uuid)
        if not chunks:
            return {"document_id": document_id, "status": "no_chunks", "chunks_total": 0}

        await enqueue([
            EmbedQueueItem(chunk_id=c.id, document_id=doc_uuid, text=c.text, content_hash=c.content_hash)
            for c in chunks
        ])
        return {"document_id": document_id, "status": "queued", "chunks_total": len(chunks)}


@router.get("/search")
async def search_documents(
    q: str,
    ticker: Optional[str] = None,
    doc_type: Optional[str] = None,
    provider_source: Optional[str] = None,
    limit: int = Query(10, ge=1, le=50),
):
    async for db in get_db():
        results = await retrieval_service.search_documents(
            db, q, ticker=ticker, doc_type=doc_type, provider_source=provider_source, limit=limit,
        )
        return {"query": q, "results": results, "total": len(results)}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_document_id(document_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(400, "Invalid document ID")
