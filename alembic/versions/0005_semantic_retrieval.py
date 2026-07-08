"""milestone1 — Semantic Retrieval Engine.

Adds one new table. Nothing existing is touched — DocumentChunk's three
embedding/embedding_model/embedding_dim columns (added in 0004 as a
placeholder for this exact milestone) are left as-is; they now serve as a
denormalized cache of the currently-active embedding, written alongside the
authoritative document_embeddings row. See app/documents/models/embedding.py.

  document_embeddings   one row per (chunk, provider, model) — the durable,
                         multi-provider embedding store the retrieval layer
                         (app/documents/retrieval/) reads from.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-05
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("vector", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chunk_id", "provider", "model", name="uq_document_embeddings_chunk_provider_model"),
    )
    op.create_index("ix_document_embeddings_chunk_id", "document_embeddings", ["chunk_id"])
    op.create_index("ix_document_embeddings_document_id", "document_embeddings", ["document_id"])
    op.create_index("ix_document_embeddings_content_hash", "document_embeddings", ["content_hash"])
    op.create_index("ix_document_embeddings_provider_model", "document_embeddings", ["provider", "model"])


def downgrade() -> None:
    op.drop_index("ix_document_embeddings_provider_model", table_name="document_embeddings")
    op.drop_index("ix_document_embeddings_content_hash", table_name="document_embeddings")
    op.drop_index("ix_document_embeddings_document_id", table_name="document_embeddings")
    op.drop_index("ix_document_embeddings_chunk_id", table_name="document_embeddings")
    op.drop_table("document_embeddings")
