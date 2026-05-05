"""
Alembic migration: 0019_reviews_unique_constraint

Adds unique constraint uq_reviews_sp_ext_id on reviews(sku_platform_id, external_review_id).
Required for ON CONFLICT upsert in magnit.collect_reviews (and all other platform
review tasks). Without this constraint the INSERT ... ON CONFLICT statement raises
ProgrammingError at runtime.

The constraint was added manually to the running DB on 2026-05-04 to unblock
Magnit reviews collection. This migration ensures it survives docker compose down -v.
"""

from alembic import op

revision = "0019"
down_revision = "0018"


def upgrade() -> None:
    from sqlalchemy import text
    conn = op.get_bind()
    exists = conn.execute(
        text("SELECT 1 FROM pg_constraint WHERE conname = 'uq_reviews_sp_ext_id'")
    ).fetchone()
    if not exists:
        op.create_unique_constraint(
            "uq_reviews_sp_ext_id",
            "reviews",
            ["sku_platform_id", "external_review_id"],
        )


def downgrade() -> None:
    op.drop_constraint("uq_reviews_sp_ext_id", "reviews", type_="unique")
