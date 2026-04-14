"""
SQLAlchemy ORM model for API keys.

Security design (Architecture.md § 2, § 7):
- key_hash stores the SHA-256 hex digest of the full key — never the raw key.
  A DB breach does not expose usable keys.
- key_prefix stores only the first 8 chars of the raw portion for display in
  the management UI — not enough to reconstruct or brute-force the full key.
- revoked: explicit boolean flag; once True the key is permanently disabled.
  There is no un-revoke operation.
- expires_at NULL means the key never expires.
- last_used_at is updated asynchronously (fire-and-forget) on each successful
  authentication — non-blocking on the request path.

Multi-tenant isolation:
- Every row has a non-nullable org_id FK to organizations.
- All queries MUST filter by org_id (enforced in repository.py).
- ON DELETE CASCADE: deleting an org removes all its keys automatically.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


class APIKey(Base):
    """
    API key record — stores only the hash, never the raw key.

    Indexes (Architecture.md § 2):
    - idx_api_keys_org_id:    for listing all keys of an org (management UI)
    - idx_api_keys_key_hash:  for fast lookup on every public API request (hot path)
    - idx_api_keys_key_prefix: for display/search in the management UI
    """

    __tablename__ = "api_keys"
    __table_args__ = (
        Index("idx_api_keys_org_id", "org_id"),
        Index("idx_api_keys_key_hash", "key_hash"),
        Index("idx_api_keys_key_prefix", "key_prefix"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    key_prefix: Mapped[str] = mapped_column(
        String(16),          # 8-char prefix — generous headroom for format changes
        nullable=False,
    )
    key_hash: Mapped[str] = mapped_column(
        String(64),          # SHA-256 hex digest is always 64 characters
        unique=True,
        nullable=False,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("FALSE"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_now_utc,
    )

    def __repr__(self) -> str:
        return (
            f"<APIKey id={self.id} org_id={self.org_id} "
            f"prefix={self.key_prefix!r} revoked={self.revoked}>"
        )
