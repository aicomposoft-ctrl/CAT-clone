"""
Migration 0005: add lookup indexes for stock distribution plan uploads.

Two performance-critical indexes missing from the initial schema:

1. idx_skus_org_barcode (org_id, barcode)
   Accelerates lookup_skus_by_barcode() called on every CSV import.
   Without this, the query is a full table scan — O(n) per import file.

2. idx_platforms_name_lower (LOWER(name))
   Accelerates the case-insensitive platform lookup in lookup_platforms_by_name().
   Without this, func.lower(Platform.name).in_(names) forces a full table scan.
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Composite index on (org_id, barcode) for tenant-scoped barcode lookups.
    # Covers: WHERE barcode = ANY(:barcodes) AND org_id = :org_id AND is_active = TRUE
    op.create_index(
        "idx_skus_org_barcode",
        "skus",
        ["org_id", "barcode"],
        unique=False,
    )

    # Functional index on LOWER(name) for case-insensitive platform lookups.
    # Covers: WHERE LOWER(name) = ANY(:lower_names)
    op.create_index(
        "idx_platforms_name_lower",
        "platforms",
        [sa.text("LOWER(name)")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_platforms_name_lower", table_name="platforms")
    op.drop_index("idx_skus_org_barcode", table_name="skus")
