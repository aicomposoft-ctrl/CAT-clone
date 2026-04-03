"""
Migration 0009: add single-column index on sku_platforms.sku_id

The existing UNIQUE constraint on (sku_id, platform_id) provides a composite
B-tree index, but PostgreSQL cannot use it efficiently for queries that filter
on sku_id alone (stats and anomalies endpoints scan all platforms for a SKU).

A dedicated single-column index on sku_id allows index-only scans for the
JOIN pattern:
  price_snapshots → sku_platforms (WHERE sku_id = ?) → skus (WHERE org_id = ?)

This migration is idempotent — the index is skipped if it already exists.
"""

from alembic import op


def upgrade() -> None:
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sku_platforms_sku_id
        ON sku_platforms (sku_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_sku_platforms_sku_id")
