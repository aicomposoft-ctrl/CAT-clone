"""
Alembic migration: 0013_add_brands_client_id

Adds client_id FK column to the brands table to support multi-client scoping.

Design:
  - client_id is nullable — NULL means "unassigned / org-level brand".
    Existing orgs and brands are completely unaffected (backward compatible).
  - ON DELETE SET NULL: deleting a client unassigns its brands rather than
    cascading deletion, preserving brand/SKU data for org-level access.
  - idx_brands_client_id: supports JOIN-based client-scoped queries that
    cascade from brands through skus → all downstream analytics domains.

Usage:
    alembic upgrade head       # applies upgrade()
    alembic downgrade -1       # applies downgrade()
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# Alembic revision identifiers
revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "brands",
        sa.Column(
            "client_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    op.create_index("idx_brands_client_id", "brands", ["client_id"])


def downgrade() -> None:
    op.drop_index("idx_brands_client_id", table_name="brands")
    op.drop_column("brands", "client_id")
