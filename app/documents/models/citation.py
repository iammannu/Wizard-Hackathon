"""
ClaimCitation — the provenance link between a thesis claim and the primary
source document(s) that back it.

Why it exists:
  "Every thesis claim should ultimately trace back to one or more source
  documents" is a hard requirement, not an aspiration. A citation_id
  computed on the fly at retrieval time (and thrown away after the response
  is sent) cannot satisfy that — provenance has to be a persisted fact,
  queryable independent of the request that created it, or a claim's
  sourcing becomes unrecoverable the moment the response that mentioned it
  scrolls off screen. This table is that persisted fact.

Cardinality is many-to-many by design: one claim is often supported by
multiple filings (e.g. a margin-expansion claim citing both the latest 10-Q
and the prior-year 10-K for comparison), and one chunk can back multiple
claims across thesis versions.

citation_id is a deterministic, human-showable string derived from
(document.external_id, chunk_index) — see app/documents/citations/
(milestone 3) for the derivation — so the same underlying evidence always
renders the same citation whether it's cited once or a hundred times.

chunk_id is nullable to allow a document-level citation (e.g. "see the FY24
10-K generally") when provenance is at the document level rather than one
specific passage.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, Float, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class ClaimCitation(Base):
    __tablename__ = "claim_citations"
    __table_args__ = (
        UniqueConstraint("claim_id", "document_id", "chunk_id", name="uq_claim_citations_claim_doc_chunk"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("thesis_claims.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True
    )

    citation_id: Mapped[str] = mapped_column(String(160), nullable=False)
    relevance_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "claim_id": str(self.claim_id),
            "document_id": str(self.document_id),
            "chunk_id": str(self.chunk_id) if self.chunk_id else None,
            "citation_id": self.citation_id,
            "relevance_score": self.relevance_score,
            "created_at": self.created_at.isoformat(),
        }
