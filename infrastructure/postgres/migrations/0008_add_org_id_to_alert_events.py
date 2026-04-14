"""
Migration 0008: add org_id to alert_events.

Denormalises org_id from alert_configs into alert_events so tenant
isolation can be enforced via a direct column filter rather than a
JOIN through alert_configs on every query.

For existing rows (if any), org_id is back-filled from the parent
alert_config. For a fresh database this is a no-op.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: add nullable so existing rows are accepted.
    op.add_column(
        "alert_events",
        sa.Column("org_id", UUID(as_uuid=True), nullable=True),
    )

    # Step 2: back-fill from alert_configs for any existing rows.
    op.execute(
        """
        UPDATE alert_events ae
        SET org_id = ac.org_id
        FROM alert_configs ac
        WHERE ae.config_id = ac.id
        """
    )

    # Step 3: enforce NOT NULL now that all rows have a value.
    op.alter_column("alert_events", "org_id", nullable=False)

    # Step 4: FK constraint and index for direct tenant lookups.
    op.create_foreign_key(
        "fk_alert_events_org_id",
        "alert_events",
        "organizations",
        ["org_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("idx_alert_events_org_id", "alert_events", ["org_id"])


def downgrade() -> None:
    op.drop_index("idx_alert_events_org_id", table_name="alert_events")
    op.drop_constraint("fk_alert_events_org_id", "alert_events", type_="foreignkey")
    op.drop_column("alert_events", "org_id")
