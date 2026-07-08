"""milestone5 — Portfolio Intelligence.

Adds five new tables. Nothing existing is touched.

  portfolios           a named collection of holdings, denormalized aggregates.
  portfolio_holdings    one open/closed position per (portfolio, ticker).
  holding_snapshots      append-only daily time series per holding.
  watchlists             named ticker lists, no position attached.
  portfolio_activity      append-only buy/sell/import transaction ledger.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolios",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("base_currency", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("total_cost_basis", sa.Float(), nullable=False),
        sa.Column("total_market_value", sa.Float(), nullable=False),
        sa.Column("total_unrealized_gain", sa.Float(), nullable=False),
        sa.Column("total_realized_gain", sa.Float(), nullable=False),
        sa.Column("holding_count", sa.Integer(), nullable=False),
        sa.Column("concentration_hhi", sa.Float(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "portfolio_holdings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("average_cost", sa.Float(), nullable=False),
        sa.Column("realized_gain", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("latest_price", sa.Float(), nullable=True),
        sa.Column("market_value", sa.Float(), nullable=False),
        sa.Column("unrealized_gain", sa.Float(), nullable=False),
        sa.Column("unrealized_gain_pct", sa.Float(), nullable=False),
        sa.Column("day_change_pct", sa.Float(), nullable=True),
        sa.Column("health_score", sa.Float(), nullable=True),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("sentiment_score", sa.Float(), nullable=True),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("intelligence_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_portfolio_holdings_portfolio_id", "portfolio_holdings", ["portfolio_id"])
    op.create_index("ix_portfolio_holdings_ticker", "portfolio_holdings", ["ticker"])

    op.create_table(
        "holding_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("holding_id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("market_value", sa.Float(), nullable=False),
        sa.Column("unrealized_gain", sa.Float(), nullable=False),
        sa.Column("unrealized_gain_pct", sa.Float(), nullable=False),
        sa.Column("health_score", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.ForeignKeyConstraint(["holding_id"], ["portfolio_holdings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_holding_snapshots_holding_id", "holding_snapshots", ["holding_id"])
    op.create_index("ix_holding_snapshots_portfolio_id", "holding_snapshots", ["portfolio_id"])
    op.create_index("ix_holding_snapshots_snapshot_at", "holding_snapshots", ["snapshot_at"])

    op.create_table(
        "watchlists",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("tickers", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "portfolio_activity",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("holding_id", sa.Uuid(), nullable=True),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("activity_type", sa.String(length=30), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("realized_gain", sa.Float(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["holding_id"], ["portfolio_holdings.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_portfolio_activity_portfolio_id", "portfolio_activity", ["portfolio_id"])
    op.create_index("ix_portfolio_activity_created_at", "portfolio_activity", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_portfolio_activity_created_at", table_name="portfolio_activity")
    op.drop_index("ix_portfolio_activity_portfolio_id", table_name="portfolio_activity")
    op.drop_table("portfolio_activity")

    op.drop_table("watchlists")

    op.drop_index("ix_holding_snapshots_snapshot_at", table_name="holding_snapshots")
    op.drop_index("ix_holding_snapshots_portfolio_id", table_name="holding_snapshots")
    op.drop_index("ix_holding_snapshots_holding_id", table_name="holding_snapshots")
    op.drop_table("holding_snapshots")

    op.drop_index("ix_portfolio_holdings_ticker", table_name="portfolio_holdings")
    op.drop_index("ix_portfolio_holdings_portfolio_id", table_name="portfolio_holdings")
    op.drop_table("portfolio_holdings")

    op.drop_table("portfolios")
