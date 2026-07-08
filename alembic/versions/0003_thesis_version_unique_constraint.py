"""phase1 hardening — enforce one version_number per workspace.

create_thesis_version() computes version_number as workspace.thesis_version_count + 1
in application code with no DB-level guard. Two concurrent research calls on the
same workspace (double-submit, retried request, multiple tabs) could otherwise
both compute the same next version_number and both succeed, leaving two rows
claiming to be e.g. version 2 — silently corrupting the version timeline.

This is a pure hardening migration: a UNIQUE INDEX, no table rewrite needed on
SQLite or Postgres. Additive and safe — it only rejects writes that were
already a bug.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-03
"""
from alembic import op

revision: str = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_thesis_versions_workspace_version",
        "thesis_versions",
        ["workspace_id", "version_number"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_thesis_versions_workspace_version", table_name="thesis_versions")
