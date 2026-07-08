"""
Company-level document index — the read-side query surface for `documents`.

Why it exists:
  Both ingestion (to decide whether a discovered filing is already known)
  and retrieval/API (to answer "what do we have for AAPL?") need the same
  set of lookups. Centralizing them here means both consumers, and the
  future retrieval layer, share one query implementation instead of each
  hand-rolling `select(Document).where(...)`.
"""
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.models.document import Document, DocumentVersion


async def get_by_external_id(db: AsyncSession, provider_source: str, external_id: str) -> Optional[Document]:
    result = await db.execute(
        select(Document).where(
            Document.provider_source == provider_source,
            Document.external_id == external_id,
        )
    )
    return result.scalar_one_or_none()


async def get_latest_version(db: AsyncSession, document: Document) -> Optional[DocumentVersion]:
    if not document.latest_version_id:
        return None
    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.id == document.latest_version_id)
    )
    return result.scalar_one_or_none()


async def list_documents(
    db: AsyncSession,
    ticker: Optional[str] = None,
    doc_type: Optional[str] = None,
    limit: int = 50,
) -> list[Document]:
    query = select(Document)
    if ticker:
        query = query.where(Document.ticker == ticker.upper())
    if doc_type:
        query = query.where(Document.doc_type == doc_type)
    query = query.order_by(Document.filing_date.desc().nullslast()).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_document(db: AsyncSession, document_id) -> Optional[Document]:
    result = await db.execute(select(Document).where(Document.id == document_id))
    return result.scalar_one_or_none()
