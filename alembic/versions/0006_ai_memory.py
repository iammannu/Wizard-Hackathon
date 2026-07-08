"""milestone3 — AI Memory.

Adds four new tables. Nothing existing is touched — ThesisClaim.memory_id
(already present as a bare nullable UUID column since Phase 1, see
app/models/thesis.py's module docstring) is populated at the application
layer by app/memory/consolidator.py; no FK constraint is added for it here
since it was deliberately left generic ("MemoryEntry" wasn't yet a concrete
table when that column was created).

  conversation_memories   one append-only row per completed research session
                           (raw extraction output, before consolidation).
  workspace_memories       atomic, semantically-searchable memory scoped to
                           a workspace — what consolidator.py dedupes/
                           reinforces and retriever.py searches by default.
  company_memories         same atomic shape, scoped to a ticker instead of
                           a workspace — durable cross-workspace knowledge.
  thesis_memories           promotion target for ThesisClaim.memory_id —
                           confirmed/refuted claims and investment decisions.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-06
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_memories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("research_id", sa.Uuid(), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("extracted_items", sa.Text(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["research_id"], ["workspace_research.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversation_memories_workspace_id", "conversation_memories", ["workspace_id"])

    op.create_table(
        "workspace_memories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("memory_type", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tickers", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source_citations", sa.Text(), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("embedding_model", sa.String(length=60), nullable=True),
        sa.Column("first_research_id", sa.Uuid(), nullable=True),
        sa.Column("last_research_id", sa.Uuid(), nullable=True),
        sa.Column("reinforcement_count", sa.Integer(), nullable=False),
        sa.Column("contradiction_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workspace_memories_workspace_id", "workspace_memories", ["workspace_id"])
    op.create_index("ix_workspace_memories_memory_type", "workspace_memories", ["memory_type"])
    op.create_index("ix_workspace_memories_status", "workspace_memories", ["status"])

    op.create_table(
        "company_memories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("memory_type", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source_citations", sa.Text(), nullable=False),
        sa.Column("source_workspace_ids", sa.Text(), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("embedding_model", sa.String(length=60), nullable=True),
        sa.Column("reinforcement_count", sa.Integer(), nullable=False),
        sa.Column("contradiction_count", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("last_confirmed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_company_memories_ticker", "company_memories", ["ticker"])
    op.create_index("ix_company_memories_memory_type", "company_memories", ["memory_type"])

    op.create_table(
        "thesis_memories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("thesis_claim_id", sa.Uuid(), nullable=True),
        sa.Column("thesis_version_id", sa.Uuid(), nullable=True),
        sa.Column("memory_type", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("decision_signal", sa.String(length=20), nullable=True),
        sa.Column("conviction_at_decision", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_citations", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thesis_claim_id"], ["thesis_claims.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["thesis_version_id"], ["thesis_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_thesis_memories_workspace_id", "thesis_memories", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_thesis_memories_workspace_id", table_name="thesis_memories")
    op.drop_table("thesis_memories")

    op.drop_index("ix_company_memories_memory_type", table_name="company_memories")
    op.drop_index("ix_company_memories_ticker", table_name="company_memories")
    op.drop_table("company_memories")

    op.drop_index("ix_workspace_memories_status", table_name="workspace_memories")
    op.drop_index("ix_workspace_memories_memory_type", table_name="workspace_memories")
    op.drop_index("ix_workspace_memories_workspace_id", table_name="workspace_memories")
    op.drop_table("workspace_memories")

    op.drop_index("ix_conversation_memories_workspace_id", table_name="conversation_memories")
    op.drop_table("conversation_memories")
