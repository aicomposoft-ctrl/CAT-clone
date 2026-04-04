"""
Alembic migration: 0012_create_clients_table

Creates the clients table for multi-client support.
Clients are sub-tenants within an organisation — used by agencies managing
multiple brand clients on behalf of a single org account.

Table design:
  - org_id: FK to organizations with CASCADE — client is deleted when org is deleted.
  - slug: URL-safe identifier, unique per org (partial unique index WHERE is_active = TRUE).
    Inactive clients release their slug so it can be reused.
  - contact_email / logo_url: optional metadata for the client record.
  - is_active: soft-delete; deactivated clients retain data but are hidden from UI.

Indexes:
  - uq_clients_org_slug (partial): enforces slug uniqueness only among active clients.
  - idx_clients_org_id: listing all clients for an org (management UI, hot path).

Usage:
    alembic upgrade head       # applies upgrade()
    alembic downgrade -1       # applies downgrade()
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# Alembic revision identifiers
revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("logo_url", sa.String(500), nullable=True),
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

    # Partial unique index: slug is unique within org only among active clients.
    # Inactive clients release their slug so it can be reused by a new active client.
    op.create_index(
        "uq_clients_org_slug",
        "clients",
        ["org_id", "slug"],
        unique=True,
        postgresql_where=sa.text("is_active = TRUE"),
    )

    # Regular index for all client lookups scoped to an org (management UI, hot path).
    op.create_index("idx_clients_org_id", "clients", ["org_id"])


def downgrade() -> None:
    op.drop_index("idx_clients_org_id", table_name="clients")
    op.drop_index("uq_clients_org_slug", table_name="clients")
    op.drop_table("clients")
