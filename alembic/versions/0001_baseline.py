"""baseline — stamps pre-existing schema as migrated.

Existing tables (users, refresh_tokens, workspaces, workspace_research) were
originally created via SQLAlchemy create_all(). This migration is a no-op that
marks those tables as part of the Alembic migration history so the Phase 1
migration can build on top of them cleanly.

DO NOT add create_table() calls here — the tables already exist in all
environments. If running against a fresh database, start from revision 0002
(Alembic will run 0001 first, which is safe because create_table is absent).

Revision ID: 0001
Revises:
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa  # noqa: F401

revision: str = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Intentionally empty — existing tables were created by SQLAlchemy create_all().
    # This revision exists solely to anchor the migration chain.
    pass


def downgrade() -> None:
    pass
