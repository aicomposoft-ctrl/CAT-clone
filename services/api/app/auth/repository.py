"""
Auth repository layer — all DB queries for users, refresh_tokens, and organizations.

Rules:
- All queries use SQLAlchemy select() with explicit filters. No raw SQL strings.
- AsyncSession is passed in from the caller (FastAPI dependency injection).
- org_id is not filtered here (auth queries are identity-lookup, not tenant-scoped);
  tenant scoping is enforced at the service/router layer for all business data.
"""

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Organization, RefreshToken, User

logger = logging.getLogger(__name__)


class UserRepository:
    """Read/write operations on the users table."""

    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> User | None:
        """Return user by email (already normalised to lowercase by caller)."""
        result = await db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: UUID) -> User | None:
        """Return user by primary key."""
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def increment_failed_attempts(
        db: AsyncSession,
        user_id: UUID,
    ) -> int:
        """
        Atomically increment failed_attempts by 1 and return the new count.

        Uses SQL-side arithmetic (failed_attempts + 1) to avoid read-modify-write
        race conditions when concurrent login attempts arrive for the same account.
        """
        result = await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(failed_attempts=User.failed_attempts + 1)
            .returning(User.failed_attempts)
        )
        await db.commit()
        row = result.fetchone()
        new_count = row[0] if row else 0
        logger.debug("auth.repo.failed_attempts_incremented user_id=%s count=%d", user_id, new_count)
        return new_count

    @staticmethod
    async def set_lockout(
        db: AsyncSession,
        user_id: UUID,
        attempts: int,
        locked_until: datetime,
    ) -> None:
        """Record a lockout: store both the final attempt count and the expiry time."""
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(failed_attempts=attempts, locked_until=locked_until)
        )
        await db.commit()
        logger.warning(
            "auth.repo.lockout_set user_id=%s locked_until=%s",
            user_id,
            locked_until.isoformat(),
        )

    @staticmethod
    async def reset_failed_attempts(db: AsyncSession, user_id: UUID) -> None:
        """Clear lockout state after a successful login."""
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(failed_attempts=0, locked_until=None)
        )
        await db.commit()
        logger.debug("auth.repo.failed_attempts_reset user_id=%s", user_id)


class RefreshTokenRepository:
    """CRUD for the refresh_tokens table."""

    @staticmethod
    async def create(
        db: AsyncSession,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshToken:
        """Persist a new refresh token (stored as SHA-256 hash)."""
        token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        db.add(token)
        await db.commit()
        await db.refresh(token)
        logger.debug("auth.repo.refresh_token_created user_id=%s", user_id)
        return token

    @staticmethod
    async def get_by_hash(db: AsyncSession, token_hash: str) -> RefreshToken | None:
        """Look up a refresh token by its SHA-256 hash."""
        result = await db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def revoke(db: AsyncSession, token_hash: str) -> None:
        """Mark a refresh token as revoked. Idempotent — no error if not found."""
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .values(revoked=True)
        )
        await db.commit()
        logger.debug("auth.repo.refresh_token_revoked hash_prefix=%s", token_hash[:8])


class OrganizationRepository:
    """Read operations on the organizations table."""

    @staticmethod
    async def get_by_id(db: AsyncSession, org_id: UUID) -> Organization | None:
        """Return organization by primary key."""
        result = await db.execute(
            select(Organization).where(Organization.id == org_id)
        )
        return result.scalar_one_or_none()
