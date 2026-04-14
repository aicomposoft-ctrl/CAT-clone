"""
Alembic migration: 0011_create_api_keys_table

Creates the api_keys table required for API key authentication on public
endpoints (Architecture.md § 2 — api-public-endpoints feature).

Table design:
  - key_hash: SHA-256 hex digest of the full key — never the raw key.
    The raw key is shown once at creation and never stored.
  - key_prefix: first 8 chars of the random key portion for display in UI.
  - revoked: soft-delete; no hard deletes to preserve audit trail.
  - expires_at NULL = key never expires.
  - last_used_at: updated fire-and-forget on each successful auth.

Indexes:
  - idx_api_keys_org_id:    listing all keys for an org (management UI)
  - idx_api_keys_key_hash:  hot-path lookup on every public API request
  - idx_api_keys_key_prefix: display/search in the management UI

Usage:
    alembic upgrade head       # applies upgrade()
    alembic downgrade -1       # applies downgrade()
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# Alembic revision identifiers
revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
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
        sa.Column(
            "key_prefix",
            sa.String(16),
            nullable=False,
        ),
        # SHA-256 hex digest is always exactly 64 characters
        sa.Column(
            "key_hash",
            sa.String(64),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "revoked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )

    op.create_index("idx_api_keys_org_id", "api_keys", ["org_id"])
    # Note: key_hash already has a unique index via UniqueConstraint above.
    # A separate non-unique index would be redundant — omitted intentionally.
    op.create_index("idx_api_keys_key_prefix", "api_keys", ["key_prefix"])


def downgrade() -> None:
    op.drop_index("idx_api_keys_key_prefix", table_name="api_keys")
    op.drop_index("idx_api_keys_org_id", table_name="api_keys")
    op.drop_table("api_keys")
