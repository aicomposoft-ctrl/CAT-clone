"""Drop idx_distribution_plans_sku_platform_week.

The UNIQUE constraint on (sku_id, platform_id, week_number, year) already
causes PostgreSQL to create an implicit unique index. The explicit non-unique
index on the same columns is a duplicate — it costs write overhead on every
upsert and wastes storage without providing any additional query benefit.

Revision: 0006
Previous: 0005
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index(
        "idx_distribution_plans_sku_platform_week",
        table_name="distribution_plans",
    )


def downgrade() -> None:
    op.create_index(
        "idx_distribution_plans_sku_platform_week",
        "distribution_plans",
        ["sku_id", "platform_id", "week_number", "year"],
    )
