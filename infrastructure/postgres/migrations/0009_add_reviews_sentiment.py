"""
Migration 0009: add sentiment columns to reviews table.

The reviews table was created in migration 0003 without sentiment fields.
This migration adds them and two supporting indexes:

  sentiment VARCHAR(20)    — "positive" | "neutral" | "negative" | NULL (unscored)
  sentiment_score DECIMAL(4,3) — argmax probability from rubert-base-cased-sentiment

Both columns are nullable so that reviews collected before this migration
remain valid rows. The score_pending_reviews Celery task (processor service)
will backfill all NULLs after deployment.

Indexes:
  idx_reviews_sentiment_null  — partial index for fast "find unscored" query in Celery task
  idx_reviews_sp_sentiment    — composite for summary/history API queries
"""

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.add_column(
        "reviews",
        sa.Column(
            "sentiment",
            sa.String(20),
            sa.CheckConstraint("sentiment IN ('positive', 'neutral', 'negative')"),
            nullable=True,
        ),
    )
    op.add_column(
        "reviews",
        sa.Column("sentiment_score", sa.Numeric(4, 3), nullable=True),
    )

    # Partial index: only unscored rows — used by Celery task WHERE sentiment IS NULL
    op.execute(
        "CREATE INDEX idx_reviews_sentiment_null ON reviews (id) WHERE sentiment IS NULL"
    )

    # Composite index: covers summary GROUP BY and history filter queries
    op.execute(
        "CREATE INDEX idx_reviews_sp_sentiment ON reviews (sku_platform_id, sentiment, review_date)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_reviews_sp_sentiment")
    op.execute("DROP INDEX IF EXISTS idx_reviews_sentiment_null")
    op.drop_column("reviews", "sentiment_score")
    op.drop_column("reviews", "sentiment")
