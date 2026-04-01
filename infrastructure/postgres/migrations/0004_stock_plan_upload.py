"""
Migration 0004: create distribution_plans table.

Creates the distribution_plans table for the stock domain.
Tenant isolation is enforced by application-level JOINs through skus.org_id —
the table itself has no org_id column.

UNIQUE constraint on (sku_id, platform_id, week_number, year) enables safe
idempotent re-uploads via ON CONFLICT DO UPDATE (UPSERT).

The covering index (idx_distribution_plans_sku_platform_week) accelerates
the mandatory tenant-scoped JOIN path and filtered list queries.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "distribution_plans",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "sku_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("skus.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "platform_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platforms.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("group_name", sa.String(100), nullable=False),
        sa.Column("plan_tt_count", sa.Integer(), nullable=False),
        sa.Column("week_number", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
    )

    op.create_unique_constraint(
        "uq_distribution_plans_key",
        "distribution_plans",
        ["sku_id", "platform_id", "week_number", "year"],
    )

    op.create_index(
        "idx_distribution_plans_sku_platform_week",
        "distribution_plans",
        ["sku_id", "platform_id", "week_number", "year"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_distribution_plans_sku_platform_week",
        table_name="distribution_plans",
    )
    op.drop_constraint(
        "uq_distribution_plans_key",
        "distribution_plans",
        type_="unique",
    )
    op.drop_table("distribution_plans")
