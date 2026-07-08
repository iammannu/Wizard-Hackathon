"""phase1 — Living Investment Thesis tables and workspace thesis columns.

Adds three new tables (thesis_versions, confidence_snapshots, thesis_claims)
and five nullable columns to the workspaces table.

ALL operations are additive:
  - New tables are created fresh.
  - Existing workspace rows gain nullable/defaulted columns — zero downtime.
  - No existing column is dropped, renamed, or changed in type.

Downgrade removes the three new tables and drops the five new workspace columns.
Existing workspace rows revert to the original schema cleanly.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. thesis_versions ─────────────────────────────────────────────────────
    op.create_table(
        "thesis_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("research_id", sa.Uuid(), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("triggered_by", sa.String(length=50), nullable=False, server_default="user_query"),
        sa.Column("trigger_query", sa.Text(), nullable=False, server_default=""),
        sa.Column("signal", sa.String(length=20), nullable=False, server_default="neutral"),
        sa.Column("recommendation", sa.Text(), nullable=False, server_default=""),
        sa.Column("explanation", sa.Text(), nullable=False, server_default=""),
        sa.Column("conviction_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("bull_case", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("bear_case", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("key_risks", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("key_assumptions", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("invalidation_conditions", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("known_unknowns", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("evidence_source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_coverage", sa.String(length=20), nullable=False, server_default="none"),
        sa.Column("evidence_providers", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("agent_signals", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("active_agents", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("lifecycle_stage", sa.String(length=30), nullable=False, server_default="forming"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("previous_version_id", sa.Uuid(), nullable=True),
        sa.Column("diff", sa.Text(), nullable=True),
        sa.Column("is_major_change", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("change_type", sa.String(length=30), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["research_id"], ["workspace_research.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["previous_version_id"], ["thesis_versions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_thesis_versions_workspace_id", "thesis_versions", ["workspace_id"])

    # ── 2. confidence_snapshots ────────────────────────────────────────────────
    op.create_table(
        "confidence_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("thesis_version_id", sa.Uuid(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("conviction_score", sa.Float(), nullable=False),
        sa.Column("signal", sa.String(length=20), nullable=False),
        sa.Column("data_quality", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("signal_agreement", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("evidence_boost", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("evidence_sources", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "snapshot_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["thesis_version_id"], ["thesis_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_confidence_snapshots_workspace_id", "confidence_snapshots", ["workspace_id"])
    op.create_index("ix_confidence_snapshots_snapshot_at", "confidence_snapshots", ["snapshot_at"])

    # ── 3. thesis_claims ───────────────────────────────────────────────────────
    op.create_table(
        "thesis_claims",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("thesis_version_id", sa.Uuid(), nullable=False),
        sa.Column("claim_type", sa.String(length=40), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("source_agent", sa.String(length=50), nullable=True),
        sa.Column("claim_confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("first_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_confirmed_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("appearance_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("memory_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["thesis_version_id"], ["thesis_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_thesis_claims_workspace_id", "thesis_claims", ["workspace_id"])

    # ── 4. workspaces — five new nullable columns ──────────────────────────────
    # render_as_batch in env.py handles SQLite's lack of native ALTER TABLE ADD COLUMN
    # with constraints. These are all nullable/defaulted so existing rows remain valid.
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.add_column(
            sa.Column(
                "current_thesis_version_id", sa.Uuid(), nullable=True, server_default=None
            )
        )
        batch_op.add_column(
            sa.Column(
                "thesis_version_count", sa.Integer(), nullable=False, server_default="0"
            )
        )
        batch_op.add_column(
            sa.Column(
                "thesis_lifecycle_stage",
                sa.String(length=30),
                nullable=False,
                server_default="forming",
            )
        )
        batch_op.add_column(
            sa.Column("conviction_score", sa.Float(), nullable=False, server_default="0.0")
        )
        batch_op.add_column(
            sa.Column(
                "thesis_signal", sa.String(length=20), nullable=False, server_default="neutral"
            )
        )
        # FK on current_thesis_version_id cannot be added inline in SQLite batch mode;
        # it is enforced at the application layer by versioner.py.


def downgrade() -> None:
    # Remove new workspace columns first (they reference thesis_versions)
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.drop_column("thesis_signal")
        batch_op.drop_column("conviction_score")
        batch_op.drop_column("thesis_lifecycle_stage")
        batch_op.drop_column("thesis_version_count")
        batch_op.drop_column("current_thesis_version_id")

    # Drop tables in reverse dependency order
    op.drop_index("ix_thesis_claims_workspace_id", table_name="thesis_claims")
    op.drop_table("thesis_claims")

    op.drop_index("ix_confidence_snapshots_snapshot_at", table_name="confidence_snapshots")
    op.drop_index("ix_confidence_snapshots_workspace_id", table_name="confidence_snapshots")
    op.drop_table("confidence_snapshots")

    op.drop_index("ix_thesis_versions_workspace_id", table_name="thesis_versions")
    op.drop_table("thesis_versions")
