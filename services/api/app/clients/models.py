"""
SQLAlchemy ORM model for the clients domain.

Clients are sub-tenants within an Organisation — used by agencies managing
multiple brand clients on a single org account.

Multi-tenant design:
  - Every Client is scoped to exactly one org via org_id (FK + index).
  - slug is unique within an org, but only among active clients (partial unique
    index — see migration 0012). The ORM model does NOT enforce this at Python
    level; the DB index is the authority.
  - client_id = NULL on a Brand means "unassigned / org-level brand" — existing
    data is unaffected by this feature (Architecture.md § 2, backward compat).

NOTE: `server_default` values for UUIDs and timestamps use PostgreSQL-specific
functions (gen_random_uuid(), NOW()). These are defined in the Alembic migration
for production use. The ORM models rely on Python-side `default=` for both
PostgreSQL and SQLite (tests).
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


class Client(Base):
    """
    A client managed by an agency org.

    slug: URL-safe, unique identifier within the org (used in report filenames
    and client-context JWT claim). Pattern: ^[a-z0-9-]+$
    is_active: soft-delete — deactivated clients retain all historical data
    but are excluded from the active client list and context switch.
    """

    __tablename__ = "clients"
    __table_args__ = (
        # Partial unique index enforced at DB level — slug is unique per org
        # only among active clients. Inactive clients release their slug.
        # Mirrors migration 0012: uq_clients_org_slug WHERE is_active = TRUE.
        Index("idx_clients_org_id", "org_id"),
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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_now_utc,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_now_utc,
        onupdate=lambda: datetime.now(tz=timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<Client id={self.id} slug={self.slug!r} org_id={self.org_id} is_active={self.is_active}>"
