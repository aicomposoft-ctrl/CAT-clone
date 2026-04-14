"""
API key repository layer — all DB queries for the api_keys table.

Rules:
- All queries use SQLAlchemy select() + await db.execute(). No db.query() (legacy sync API).
- All write operations (create, update) are committed inside the method.
- org_id is always included in lookup filters to enforce multi-tenant isolation.
- update_last_used is designed to be fire-and-forget: it commits independently
  and should be wrapped in asyncio.create_task() by the caller (deps.py).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api_keys.models import APIKey

logger = logging.getLogger(__name__)


class APIKeyRepository:
    """Read/write operations on the api_keys table."""

    @staticmethod
    async def get_by_hash(db: AsyncSession, key_hash: str) -> APIKey | None:
        """
        Look up an API key by its SHA-256 hash.

        This is the hot path — called on every public API request.
        The api_keys.key_hash column has a unique index for O(log n) lookup.
        Returns None if no matching key exists (same response as revoked/expired
        to prevent enumeration — callers handle the distinction).
        """
        result = await db.execute(
            select(APIKey).where(APIKey.key_hash == key_hash)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id_and_org(
        db: AsyncSession,
        key_id: UUID,
        org_id: UUID,
    ) -> APIKey | None:
        """
        Look up an API key by its primary key scoped to an organisation.

        The org_id filter is mandatory — it ensures a user cannot revoke
        another organisation's key even if they know the UUID.
        Returns None for both "not found" and "wrong org" cases to prevent
        key enumeration (Pseudocode.md § revoke_api_key).
        """
        result = await db.execute(
            select(APIKey).where(
                APIKey.id == key_id,
                APIKey.org_id == org_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_org(db: AsyncSession, org_id: UUID) -> list[APIKey]:
        """
        Return all API keys belonging to an organisation, ordered newest-first.

        Includes revoked keys — the UI shows revoked status so users can audit
        which keys existed. Callers may filter revoked=True if needed.
        """
        result = await db.execute(
            select(APIKey)
            .where(APIKey.org_id == org_id)
            .order_by(APIKey.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, api_key: APIKey) -> APIKey:
        """
        Persist a new APIKey row and return the refreshed ORM instance.

        The caller is responsible for constructing the APIKey with all required
        fields (org_id, name, key_prefix, key_hash, created_by, expires_at).
        The key_hash must already be the SHA-256 hex digest of the full key —
        the raw key is NEVER passed to or stored by this method.
        """
        db.add(api_key)
        await db.commit()
        await db.refresh(api_key)
        logger.debug(
            "api_keys.repo.created org_id=%s prefix=%s",
            api_key.org_id,
            api_key.key_prefix,
        )
        return api_key

    @staticmethod
    async def update_last_used(db: AsyncSession, key_id: UUID) -> None:
        """
        Stamp last_used_at with the current UTC time for the given key.

        Designed for fire-and-forget use via asyncio.create_task() — any
        exception here is non-fatal and must NOT propagate to the request.
        Uses a SQL-side UPDATE to avoid a round-trip SELECT + ORM flush.
        """
        await db.execute(
            update(APIKey)
            .where(APIKey.id == key_id)
            .values(last_used_at=datetime.now(tz=timezone.utc))
        )
        await db.commit()
        logger.debug("api_keys.repo.last_used_updated key_id=%s", key_id)
