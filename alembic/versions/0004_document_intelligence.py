"""phase2 — Document Intelligence subsystem.

Adds six new tables. Nothing existing is touched — this is the foundation
for the primary-source document layer (SEC EDGAR, investor relations
sources, transcripts, press releases) that grounds the Living Thesis,
described in app/documents/.

  documents            canonical identity of a real-world filing/document
  document_versions    extracted content for one fetch of a document
  document_chunks      retrievable/embeddable units of a document
  document_entities    entities extracted at ingestion, feeding the
                        knowledge graph
  claim_citations      persisted provenance: thesis_claims -> documents
  workspace_documents  workspace-level document cache

All new tables, all nullable/defaulted where they need to be, zero changes
to existing tables. Downgrade drops all six in dependency order.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-04
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. documents ─────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("provider_source", sa.String(length=40), nullable=False),
        sa.Column("doc_type", sa.String(length=40), nullable=False),
        sa.Column("ticker", sa.String(length=20), nullable=True),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("cik", sa.String(length=20), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=True),
        sa.Column("period_end_date", sa.Date(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="discovered"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("latest_version_id", sa.Uuid(), nullable=True),
        sa.Column("latest_version_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_source", "external_id", name="uq_documents_provider_external_id"),
    )
    op.create_index("ix_documents_external_id", "documents", ["external_id"])
    op.create_index("ix_documents_provider_source", "documents", ["provider_source"])
    op.create_index("ix_documents_doc_type", "documents", ["doc_type"])
    op.create_index("ix_documents_ticker", "documents", ["ticker"])
    op.create_index("ix_documents_cik", "documents", ["cik"])
    op.create_index("ix_documents_filing_date", "documents", ["filing_date"])

    # ── 2. document_versions ────────────────────────────────────────────────
    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("raw_format", sa.String(length=10), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("sections", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "version_number", name="uq_document_versions_document_version"),
    )
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])
    op.create_index("ix_document_versions_content_hash", "document_versions", ["content_hash"])

    # documents.latest_version_id FK — added after document_versions exists.
    with op.batch_alter_table("documents") as batch_op:
        batch_op.create_foreign_key(
            "fk_documents_latest_version", "document_versions", ["latest_version_id"], ["id"],
            ondelete="SET NULL",
        )

    # ── 3. document_chunks ───────────────────────────────────────────────────
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(length=120), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("embedding_model", sa.String(length=60), nullable=True),
        sa.Column("embedding_dim", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_version_id", "chunk_index", name="uq_document_chunks_version_index"),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_document_chunks_document_version_id", "document_chunks", ["document_version_id"])
    op.create_index("ix_document_chunks_content_hash", "document_chunks", ["content_hash"])

    # ── 4. document_entities ─────────────────────────────────────────────────
    op.create_table(
        "document_entities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=True),
        sa.Column("entity_name", sa.String(length=255), nullable=False),
        sa.Column("entity_type", sa.String(length=30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("mention_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_entities_document_id", "document_entities", ["document_id"])
    op.create_index("ix_document_entities_entity_name", "document_entities", ["entity_name"])

    # ── 5. claim_citations ───────────────────────────────────────────────────
    op.create_table(
        "claim_citations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=True),
        sa.Column("citation_id", sa.String(length=160), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.ForeignKeyConstraint(["claim_id"], ["thesis_claims.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("claim_id", "document_id", "chunk_id", name="uq_claim_citations_claim_doc_chunk"),
    )
    op.create_index("ix_claim_citations_claim_id", "claim_citations", ["claim_id"])
    op.create_index("ix_claim_citations_document_id", "claim_citations", ["document_id"])

    # ── 6. workspace_documents ───────────────────────────────────────────────
    op.create_table(
        "workspace_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("first_used_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "document_id", name="uq_workspace_documents_workspace_document"),
    )
    op.create_index("ix_workspace_documents_workspace_id", "workspace_documents", ["workspace_id"])
    op.create_index("ix_workspace_documents_document_id", "workspace_documents", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_workspace_documents_document_id", table_name="workspace_documents")
    op.drop_index("ix_workspace_documents_workspace_id", table_name="workspace_documents")
    op.drop_table("workspace_documents")

    op.drop_index("ix_claim_citations_document_id", table_name="claim_citations")
    op.drop_index("ix_claim_citations_claim_id", table_name="claim_citations")
    op.drop_table("claim_citations")

    op.drop_index("ix_document_entities_entity_name", table_name="document_entities")
    op.drop_index("ix_document_entities_document_id", table_name="document_entities")
    op.drop_table("document_entities")

    op.drop_index("ix_document_chunks_content_hash", table_name="document_chunks")
    op.drop_index("ix_document_chunks_document_version_id", table_name="document_chunks")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")

    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_constraint("fk_documents_latest_version", type_="foreignkey")

    op.drop_index("ix_document_versions_content_hash", table_name="document_versions")
    op.drop_index("ix_document_versions_document_id", table_name="document_versions")
    op.drop_table("document_versions")

    op.drop_index("ix_documents_filing_date", table_name="documents")
    op.drop_index("ix_documents_cik", table_name="documents")
    op.drop_index("ix_documents_ticker", table_name="documents")
    op.drop_index("ix_documents_doc_type", table_name="documents")
    op.drop_index("ix_documents_provider_source", table_name="documents")
    op.drop_index("ix_documents_external_id", table_name="documents")
    op.drop_table("documents")
