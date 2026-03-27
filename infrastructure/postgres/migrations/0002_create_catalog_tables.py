"""
Alembic migration: 0002_create_catalog_tables

Creates four tables for the catalog domain:
  - brands        (tenant-scoped; client/competitor)
  - skus          (tenant-scoped; soft-delete via is_active)
  - platforms     (global shared catalog; no org_id)
  - sku_platforms (many-to-many SKU ↔ Platform; tenant isolation via sku JOIN)

Partial unique index on (org_id, article) WHERE article IS NOT NULL allows
multiple SKUs without an article but enforces uniqueness when article is set.

Usage:
    alembic upgrade head
    alembic downgrade -1
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # brands
    # ------------------------------------------------------------------
    op.create_table(
        "brands",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "type",
            sa.String(50),
            nullable=False,
            server_default="client",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "type IN ('client', 'competitor')",
            name="ck_brands_type",
        ),
        sa.UniqueConstraint("org_id", "name", name="uq_brands_org_name"),
    )
    op.create_index("idx_brands_org_id", "brands", ["org_id"])

    # ------------------------------------------------------------------
    # platforms
    # ------------------------------------------------------------------
    op.create_table(
        "platforms",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("type", sa.String(50), nullable=True),
        sa.Column("scraper_module", sa.String(100), nullable=True),
        sa.Column(
            "schedule_cron",
            sa.String(50),
            nullable=False,
            server_default="0 2 * * *",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
    )

    # ------------------------------------------------------------------
    # skus
    # ------------------------------------------------------------------
    op.create_table(
        "skus",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("article", sa.String(100), nullable=True),
        sa.Column("rpc", sa.String(100), nullable=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("barcode", sa.String(50), nullable=True),
        sa.Column("category", sa.String(255), nullable=True),
        sa.Column("sub_category", sa.String(255), nullable=True),
        sa.Column("reference_image_url", sa.Text, nullable=True),
        sa.Column("reference_description", sa.Text, nullable=True),
        sa.Column("reference_composition", sa.Text, nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("idx_skus_org_id", "skus", ["org_id"])
    op.create_index("idx_skus_brand_id", "skus", ["brand_id"])
    op.create_index("idx_skus_active", "skus", ["org_id", "is_active"])
    # Partial unique: article unique per org only when not null
    op.execute(
        """
        CREATE UNIQUE INDEX uq_skus_org_article
        ON skus (org_id, article)
        WHERE article IS NOT NULL
        """
    )

    # ------------------------------------------------------------------
    # sku_platforms
    # ------------------------------------------------------------------
    op.create_table(
        "sku_platforms",
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
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column(
            "is_monitored",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("sku_id", "platform_id", name="uq_sku_platforms_sku_platform"),
    )
    op.create_index("idx_sku_platforms_sku", "sku_platforms", ["sku_id"])
    # Supports queries filtering/joining by platform (e.g. orchestrator: all WB platforms)
    op.create_index("idx_sku_platforms_platform", "sku_platforms", ["platform_id"])
    # Composite index for cursor pagination: ORDER BY (created_at DESC, id DESC) WHERE org_id = ?
    op.execute(
        "CREATE INDEX idx_skus_org_cursor ON skus (org_id, created_at DESC, id DESC)"
    )


def downgrade() -> None:
    op.drop_index("idx_sku_platforms_platform", table_name="sku_platforms")
    op.drop_index("idx_sku_platforms_sku", table_name="sku_platforms")
    op.drop_table("sku_platforms")

    op.execute("DROP INDEX IF EXISTS uq_skus_org_article")
    op.execute("DROP INDEX IF EXISTS idx_skus_org_cursor")
    op.drop_index("idx_skus_active", table_name="skus")
    op.drop_index("idx_skus_brand_id", table_name="skus")
    op.drop_index("idx_skus_org_id", table_name="skus")
    op.drop_table("skus")

    op.drop_table("platforms")

    op.drop_index("idx_brands_org_id", table_name="brands")
    op.drop_table("brands")
