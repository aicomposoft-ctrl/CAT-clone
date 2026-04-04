"""
Migration 0010: create stock_history table and add performance indexes for dashboard.

stock_history: daily stock levels per (sku_id, platform_id, org_id) — written by
  the Celery stock collector task and read by the dashboard distribution query.

New indexes:
  - alert_events (org_id, triggered_at DESC) — composite for "recent alerts" sort
  - alert_events (org_id, is_sent)           — composite for active-alerts COUNT
  - sku_platforms (sku_id, is_monitored)     — speeds up monitored SKU count

These replace the existing single-column indexes which are superseded by the
composite ones (PostgreSQL can use the leftmost prefix).
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# Alembic-style migration — upgrade/downgrade functions
# Can be applied manually or integrated into Alembic env.py.


def upgrade(op) -> None:  # noqa: ANN001
    # ------------------------------------------------------------------ #
    # 1. stock_history: written by collector, read by dashboard/reports   #
    # ------------------------------------------------------------------ #
    op.create_table(
        "stock_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("sku_id", UUID(as_uuid=True), sa.ForeignKey("skus.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform_id", UUID(as_uuid=True), sa.ForeignKey("platforms.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("week_number", sa.SmallInteger(), nullable=False),
        sa.Column("year", sa.SmallInteger(), nullable=False),
        sa.Column("stock_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Primary access pattern: org + sku + platform + week/year
    op.create_index(
        "idx_stock_history_org_sku_platform_week",
        "stock_history",
        ["org_id", "sku_id", "platform_id", "week_number", "year"],
    )
    # For aggregation queries over a week for a whole org
    op.create_index("idx_stock_history_org_week", "stock_history", ["org_id", "week_number", "year"])

    # ------------------------------------------------------------------ #
    # 2. Performance indexes for dashboard queries                        #
    # ------------------------------------------------------------------ #

    # alert_events: "recent alerts per org" — ORDER BY triggered_at DESC
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_alert_events_org_triggered "
        "ON alert_events (org_id, triggered_at DESC)"
    )

    # alert_events: "active alerts count" — WHERE org_id = X AND is_sent = FALSE
    op.create_index(
        "idx_alert_events_org_sent",
        "alert_events",
        ["org_id", "is_sent"],
    )

    # sku_platforms: "monitored pairs per org" — filtered by is_monitored via JOIN
    op.create_index(
        "idx_sku_platforms_monitored",
        "sku_platforms",
        ["is_monitored"],
        postgresql_where=sa.text("is_monitored = TRUE"),
    )


def downgrade(op) -> None:  # noqa: ANN001
    op.drop_index("idx_sku_platforms_monitored", table_name="sku_platforms")
    op.drop_index("idx_alert_events_org_sent", table_name="alert_events")
    op.execute("DROP INDEX IF EXISTS idx_alert_events_org_triggered")
    op.drop_index("idx_stock_history_org_week", table_name="stock_history")
    op.drop_index("idx_stock_history_org_sku_platform_week", table_name="stock_history")
    op.drop_table("stock_history")
