"""
SQLAlchemy ORM models for authentication: Organization, User, RefreshToken.

Multi-tenant design: every User is scoped to an org_id.
All queries against users and refresh_tokens MUST filter by org_id
(either directly or via a JOIN through user.org_id).

NOTE: `server_default` values for UUIDs and timestamps use PostgreSQL-specific
functions (gen_random_uuid(), NOW()). These are defined in the Alembic migration
for production use. The ORM models rely on Python-side `default=` for both
PostgreSQL and SQLite (tests).
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


class Organization(Base):
    """
    Top-level tenant unit. Every user and SKU belongs to exactly one org.

    slug: URL-safe, unique identifier used in URLs and API keys.
    plan: subscription tier — "basic" | "pro".
    """

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    plan: Mapped[str] = mapped_column(
        String(50), nullable=False, default="basic", server_default="basic"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_now_utc,
    )

    # Relationships
    users: Mapped[list["User"]] = relationship("User", back_populates="organization", lazy="raise")

    def __repr__(self) -> str:
        return f"<Organization id={self.id} slug={self.slug!r} plan={self.plan!r}>"


class User(Base):
    """
    Application user scoped to an Organization.

    role: "admin" | "manager" | "viewer" — enforced at DB level via CHECK constraint.
    failed_attempts + locked_until: brute-force lockout (5 attempts → 15 min lock).
    password_hash: bcrypt, cost factor 12 — never store plaintext passwords.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('admin', 'manager', 'viewer')",
            name="ck_users_role",
        ),
        Index("idx_users_email", "email"),
        Index("idx_users_org_id", "org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="viewer",
        server_default="viewer",
    )
    failed_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    locked_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="users", lazy="raise")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="raise",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} role={self.role!r} org_id={self.org_id}>"


class RefreshToken(Base):
    """
    Hashed refresh token record stored in DB to enable explicit revocation.

    token_hash: SHA256 hex digest of the raw JWT string — never store the
    raw token. A DB breach does not expose valid tokens.
    revoked: set to True on logout or suspicious activity detection.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("idx_refresh_tokens_user_id", "user_id"),
        Index("idx_refresh_tokens_token_hash", "token_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),  # SHA256 hex digest is always 64 characters
        unique=True,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
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

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens", lazy="raise")

    def __repr__(self) -> str:
        return f"<RefreshToken id={self.id} user_id={self.user_id} revoked={self.revoked}>"
