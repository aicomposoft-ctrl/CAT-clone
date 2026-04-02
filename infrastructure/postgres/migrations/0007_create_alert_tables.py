"""
Migration 0007: create alert_configs and alert_events tables.

alert_configs:
  One row per alert rule. Org-scoped (org_id required).
  sku_id / platform_id NULL = applies to all SKUs / all platforms for this org.
  alert_type: 'content_drop' | 'oos'
  threshold: used for content_drop (fire when content_total < threshold).
             NULL is valid for 'oos' (no numeric threshold needed).
  email_recipients: JSON array of email strings, e.g. '["a@x.com","b@x.com"]'
  is_active: soft-disable without deleting the config.

alert_events:
  One row per triggered alert. Append-only; never updated except is_sent + sent_at.
  value_before / value_after: content_total or NULL (for oos alerts).
  De-duplication: UNIQUE (config_id, sku_platform_id, scored_at) prevents sending
  the same alert twice for the same SKU×Platform on the same day.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


def upgrade() -> None:
    op.create_table(
        "alert_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sku_id", UUID(as_uuid=True), sa.ForeignKey("skus.id", ondelete="CASCADE"), nullable=True),
        sa.Column("platform_id", UUID(as_uuid=True), sa.ForeignKey("platforms.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("threshold", sa.Numeric(10, 2), nullable=True),
        sa.Column("email_recipients", sa.Text(), nullable=False),  # JSON array as text
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "alert_type IN ('content_drop', 'oos')",
            name="ck_alert_configs_type",
        ),
    )
    op.create_index("idx_alert_configs_org_id", "alert_configs", ["org_id"])
    op.create_index("idx_alert_configs_active", "alert_configs", ["org_id", "is_active"])

    op.create_table(
        "alert_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("config_id", UUID(as_uuid=True), sa.ForeignKey("alert_configs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sku_platform_id", UUID(as_uuid=True), sa.ForeignKey("sku_platforms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scored_at", sa.Date(), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("value_before", sa.Numeric(10, 2), nullable=True),
        sa.Column("value_after", sa.Numeric(10, 2), nullable=True),
        sa.Column("is_sent", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_alert_events_no_duplicate",
        "alert_events",
        ["config_id", "sku_platform_id", "scored_at"],
    )
    op.create_index("idx_alert_events_config", "alert_events", ["config_id"])
    op.create_index("idx_alert_events_pending", "alert_events", ["is_sent", "triggered_at"])


def downgrade() -> None:
    op.drop_table("alert_events")
    op.drop_table("alert_configs")
