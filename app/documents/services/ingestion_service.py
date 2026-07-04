"""
Ingestion service — the one place that turns a DiscoveredDocument into
persisted Document + DocumentVersion + DocumentChunk rows.

Why it exists:
  This is the provider-agnostic orchestrator required by "replace providers
  later without changing the research pipeline." It only calls
  `provider.discover()` / `provider.fetch()` — the DocumentProvider
  interface — so adding InvestorRelationsProvider, TranscriptProvider, or
  swapping SECProvider for something else later means writing a new
  provider class and nothing else in this file changes.

Idempotency (the two checks, in order):
  1. external_id already ingested successfully -> skip the fetch entirely.
     Correct for SEC filings: an accession number is immutable once issued;
     content under it never changes (an amendment is a new accession
     number, i.e. a new external_id, not a mutation of the old one).
  2. content_hash unchanged after fetching -> skip re-parsing/re-chunking.
     Needed for source types where the same URL/external_id can be
     corrected in place after publication (a press release, for instance).

Failure handling:
  A single bad filing (network error, unparseable content) does not abort
  ingest_ticker() for the rest — it's recorded as a `failed` Document row
  with error_message set, so it's visible and retriable, not silently
  dropped or a batch-wide crash.

Not yet handled (see app/documents/parsers/__init__.py docstring history for
why): PDF ingestion. SEC's own Tier-1 doc types are all HTML, so this gap
doesn't block SECProvider; it needs to land before any Tier 2 provider that
serves PDFs (investor decks, some shareholder letters) goes live.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from app.documents.providers.base import DocumentProvider, DiscoveredDocument
from app.documents.parsers.html_sections import parse_filing_sections, parse_generic_html
from app.documents.chunking.chunker import chunk_sections, count_tokens
from app.documents.models.document import Document, DocumentVersion
from app.documents.models.chunk import DocumentChunk
from app.documents.indexing import document_index

logger = logging.getLogger(__name__)

# Doc types whose SEC filings follow "Item N." numbering — everything else
# (DEF-14A, Form 4, Form 13F, and all Tier 2/3 doc types) falls back to
# whole-document text via parse_generic_html.
ITEM_STRUCTURED_DOC_TYPES = {"10-K", "10-Q", "8-K"}


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _extract_sections(doc_type: str, raw_format: str, raw_content) -> dict:
    if raw_format == "pdf":
        raise NotImplementedError(f"PDF parsing not yet implemented (doc_type={doc_type})")
    parser = parse_filing_sections if doc_type in ITEM_STRUCTURED_DOC_TYPES else parse_generic_html
    return parser(raw_content)


def _new_document(discovered: DiscoveredDocument, status: str, error_message: Optional[str] = None) -> Document:
    return Document(
        external_id=discovered.external_id,
        provider_source=discovered.provider_source,
        doc_type=discovered.doc_type,
        ticker=discovered.ticker,
        company_name=discovered.company_name,
        cik=discovered.cik,
        title=discovered.title,
        filing_date=discovered.filing_date,
        period_end_date=discovered.period_end_date,
        source_url=discovered.source_url,
        status=status,
        error_message=error_message,
    )


async def ingest_document(db, provider: DocumentProvider, discovered: DiscoveredDocument) -> Document:
    existing = await document_index.get_by_external_id(db, discovered.provider_source, discovered.external_id)
    if existing and existing.status in ("chunked", "embedded") and provider.immutable_once_ingested:
        return existing

    fetched = await provider.fetch(discovered)
    sections = _extract_sections(discovered.doc_type, fetched.raw_format, fetched.raw_content)

    if not sections:
        if existing:
            existing.status = "failed"
            existing.error_message = "No extractable text content"
            existing.updated_at = datetime.now(timezone.utc)
            return existing
        document = _new_document(discovered, status="failed", error_message="No extractable text content")
        db.add(document)
        return document

    full_text = "\n\n".join(sections.values())
    content_hash = _hash(full_text)

    if existing and existing.content_hash == content_hash:
        existing.updated_at = datetime.now(timezone.utc)
        return existing

    if existing:
        document = existing
        version_number = document.latest_version_number + 1
    else:
        document = _new_document(discovered, status="fetched")
        db.add(document)
        await db.flush()  # assign document.id for the DocumentVersion FK
        version_number = 1

    version = DocumentVersion(
        document_id=document.id,
        version_number=version_number,
        raw_format=fetched.raw_format,
        extracted_text=full_text,
        sections=json.dumps(sections),
        token_count=count_tokens(full_text),
        content_hash=content_hash,
    )
    db.add(version)
    await db.flush()  # assign version.id for the DocumentChunk FK

    chunks = chunk_sections(sections)
    for index, chunk in enumerate(chunks):
        db.add(DocumentChunk(
            document_id=document.id,
            document_version_id=version.id,
            chunk_index=index,
            section=chunk.section,
            text=chunk.text,
            token_count=chunk.token_count,
            content_hash=_hash(chunk.text),
        ))

    document.content_hash = content_hash
    document.status = "chunked"
    document.latest_version_id = version.id
    document.latest_version_number = version_number
    document.error_message = None
    document.updated_at = datetime.now(timezone.utc)

    return document


async def ingest_ticker(
    db,
    provider: DocumentProvider,
    ticker: str,
    doc_types: list[str],
    since=None,
) -> list[Document]:
    """Discover + ingest every matching document for one ticker. Commits are
    the caller's responsibility, same convention as create_thesis_version()."""
    discovered_list = await provider.discover(ticker, doc_types, since)
    documents: list[Document] = []

    for discovered in discovered_list:
        try:
            documents.append(await ingest_document(db, provider, discovered))
        except Exception:
            logger.exception(
                "Ingestion failed for %s %s (external_id=%s)",
                provider.source_name, discovered.doc_type, discovered.external_id,
            )
            existing = await document_index.get_by_external_id(db, discovered.provider_source, discovered.external_id)
            if existing:
                existing.status = "failed"
                existing.error_message = "Ingestion error — see server logs"
                existing.updated_at = datetime.now(timezone.utc)
                documents.append(existing)
            else:
                failed = _new_document(discovered, status="failed", error_message="Ingestion error — see server logs")
                db.add(failed)
                documents.append(failed)

    return documents
