"""
Migration 0003: create content_scores, price_snapshots, reviews tables.

These tables are written by Celery collector tasks and read by:
  - ML processor (content scoring)
  - FastAPI (reports, alerts, dashboard)

content_scores: daily upsert per (sku_platform_id, scored_at)
  - content task fills: collected_title, collected_description, collected_composition, collected_image_url
  - stock task fills: in_stock, warehouse_qty (partial-row contract — ML must guard on NOT NULL)

price_snapshots: append-only time series (one row per price check)

reviews: deduplication via UNIQUE (sku_platform_id, external_review_id)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


def upgrade() -> None:
    op.create_table(
        "content_scores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("sku_platform_id", UUID(as_uuid=True), sa.ForeignKey("sku_platforms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scored_at", sa.Date(), nullable=False),
        # Content fields (populated by content task)
        sa.Column("collected_title", sa.String(500), nullable=True),
        sa.Column("collected_description", sa.Text(), nullable=True),
        sa.Column("collected_composition", sa.Text(), nullable=True),
        sa.Column("collected_image_url", sa.Text(), nullable=True),
        # Stock fields (populated by stock task — partial-row contract)
        sa.Column("in_stock", sa.Boolean(), nullable=True),
        sa.Column("warehouse_qty", sa.Integer(), nullable=True),
        # Scoring fields (populated by ML processor)
        sa.Column("image_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("description_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("composition_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("content_total", sa.Numeric(5, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        "uq_content_scores_sp_date",
        "content_scores",
        ["sku_platform_id", "scored_at"],
    )
    op.create_index("idx_content_scores_sp", "content_scores", ["sku_platform_id"])
    op.create_index("idx_content_scores_date", "content_scores", ["scored_at"])

    op.create_table(
        "price_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("sku_platform_id", UUID(as_uuid=True), sa.ForeignKey("sku_platforms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("original_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("discount_pct", sa.Numeric(5, 2), nullable=False, server_default="0.00"),
        sa.Column("promo_label", sa.String(255), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_price_snapshots_sp", "price_snapshots", ["sku_platform_id"])
    op.create_index("idx_price_snapshots_collected_at", "price_snapshots", ["collected_at"])

    op.create_table(
        "reviews",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("sku_platform_id", UUID(as_uuid=True), sa.ForeignKey("sku_platforms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_review_id", sa.String(255), nullable=False),
        sa.Column("review_text", sa.Text(), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("review_date", sa.Date(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        "uq_reviews_sp_ext_id",
        "reviews",
        ["sku_platform_id", "external_review_id"],
    )
    op.create_index("idx_reviews_sp", "reviews", ["sku_platform_id"])
    op.create_index("idx_reviews_date", "reviews", ["review_date"])


def downgrade() -> None:
    op.drop_table("reviews")
    op.drop_table("price_snapshots")
    op.drop_table("content_scores")
