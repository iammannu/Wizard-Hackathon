"""
Document + DocumentVersion + WorkspaceDocument — the canonical record of a
primary-source financial document and everything ingested from it.

Why it exists:
  Document is the stable, provider-agnostic identity of a real-world filing
  or company communication. DocumentVersion holds the actual extracted
  content for one fetch of it — filings get amended (10-K/A), press releases
  get corrected, so identity (Document) and content-at-a-point-in-time
  (DocumentVersion) are deliberately separate tables, the same split
  ThesisVersion already uses for workspace theses.

Stable identifiers:
  external_id is the natural key a human or another system would use to
  find this exact document again: a SEC accession number for EDGAR filings
  (globally unique, assigned by the SEC — nothing to invent), or a
  content-derived hash for anything without a natural registry (press
  releases, transcripts, IR decks). (provider_source, external_id) is
  unique — see migration 0004. The UUID `id` is the internal FK target;
  external_id is what a citation or a UI shows a human.

How it integrates:
  Written by app/documents/services/ingestion_service.py. Read by
  app/documents/retrieval/ (milestone 2), app/documents/indexing/, and
  eventually app/providers/evidence.py once document evidence feeds the
  research pipeline (milestone 3). Nothing outside app/documents/ should
  construct these directly — go through ingestion_service.

WorkspaceDocument is the "workspace-level document cache" — which documents
a given workspace's research has actually drawn on, so the UI can show a
per-workspace document list without re-running retrieval.
"""
import uuid
import json
from datetime import datetime, date, timezone
from typing import Optional
from sqlalchemy import String, DateTime, Date, ForeignKey, Text, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("provider_source", "external_id", name="uq_documents_provider_external_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # Stable natural identifier — see module docstring.
    external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    provider_source: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # "sec_edgar" | "investor_relations" | "transcript" | "press_release" | "search_discovery"

    doc_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # "10-K" | "10-Q" | "8-K" | "DEF-14A" | "FORM-4" | "FORM-13F" |
    # "transcript" | "investor_presentation" | "press_release" |
    # "shareholder_letter" | "product_announcement" | "management_commentary"

    ticker: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    company_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cik: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)  # SEC Central Index Key

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    filing_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    period_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)

    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # latest version's hash

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="discovered")
    # "discovered" | "fetched" | "parsed" | "chunked" | "embedded" | "failed"
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    latest_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("document_versions.id", ondelete="SET NULL", use_alter=True, name="fk_documents_latest_version"),
        nullable=True, default=None,
    )
    latest_version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "external_id": self.external_id,
            "provider_source": self.provider_source,
            "doc_type": self.doc_type,
            "ticker": self.ticker,
            "company_name": self.company_name,
            "cik": self.cik,
            "title": self.title,
            "filing_date": self.filing_date.isoformat() if self.filing_date else None,
            "period_end_date": self.period_end_date.isoformat() if self.period_end_date else None,
            "source_url": self.source_url,
            "status": self.status,
            "error_message": self.error_message,
            "latest_version_number": self.latest_version_number,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_versions_document_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    raw_format: Mapped[str] = mapped_column(String(10), nullable=False)  # "html" | "pdf" | "text"
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    sections: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # JSON: {section_name: text}
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def sections_dict(self) -> dict:
        try:
            return json.loads(self.sections or "{}")
        except Exception:
            return {}

    def to_dict(self, include_text: bool = False) -> dict:
        data = {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "version_number": self.version_number,
            "raw_format": self.raw_format,
            "sections": list(self.sections_dict().keys()),
            "token_count": self.token_count,
            "content_hash": self.content_hash,
            "fetched_at": self.fetched_at.isoformat(),
            "created_at": self.created_at.isoformat(),
        }
        if include_text:
            data["extracted_text"] = self.extracted_text
            data["sections_detail"] = self.sections_dict()
        return data


class WorkspaceDocument(Base):
    """Workspace-level document cache — which documents a workspace's research has drawn on."""
    __tablename__ = "workspace_documents"
    __table_args__ = (
        UniqueConstraint("workspace_id", "document_id", name="uq_workspace_documents_workspace_document"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    first_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "workspace_id": str(self.workspace_id),
            "document_id": str(self.document_id),
            "first_used_at": self.first_used_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat(),
            "use_count": self.use_count,
        }
