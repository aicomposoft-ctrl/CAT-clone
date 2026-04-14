"""
Clients repository layer — all DB queries for the clients table.

Rules:
- All queries use SQLAlchemy select() with explicit filters. No raw SQL strings.
- AsyncSession is passed in from the caller (FastAPI dependency injection).
- Every query MUST be scoped by org_id (multi-tenant isolation rule).
- Static methods only — no instance state, consistent with auth/repository.py pattern.
"""

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.models import Client

logger = logging.getLogger(__name__)


class ClientRepository:
    """Read/write operations on the clients table."""

    @staticmethod
    async def get_by_id_and_org(
        db: AsyncSession,
        client_id: UUID,
        org_id: UUID,
    ) -> Client | None:
        """
        Return a client by PK scoped to org_id.

        Returns both active and inactive clients — use get_active_by_id_and_org
        when only active clients are acceptable (e.g. JWT context validation).
        """
        result = await db.execute(
            select(Client).where(
                Client.id == client_id,
                Client.org_id == org_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_active_by_id_and_org(
        db: AsyncSession,
        client_id: UUID,
        org_id: UUID,
    ) -> Client | None:
        """
        Return an active client by PK scoped to org_id.

        Used when a client_id claim is extracted from a JWT — only active clients
        constitute a valid context (Pseudocode.md § get_current_user).
        Returns None for inactive clients, triggering 401 INVALID_CLIENT_CONTEXT.
        """
        result = await db.execute(
            select(Client).where(
                Client.id == client_id,
                Client.org_id == org_id,
                Client.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_slug_and_org(
        db: AsyncSession,
        slug: str,
        org_id: UUID,
    ) -> Client | None:
        """
        Return a client by slug scoped to org_id (active clients only).

        Used for slug uniqueness check during client creation — the DB partial
        unique index uq_clients_org_slug enforces this at DB level too, but
        the service layer checks first to raise a clean SLUG_CONFLICT error.
        """
        result = await db.execute(
            select(Client).where(
                Client.slug == slug,
                Client.org_id == org_id,
                Client.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_org(
        db: AsyncSession,
        org_id: UUID,
        include_inactive: bool = False,
    ) -> list[Client]:
        """
        Return all clients for an org, ordered by name.

        Args:
            org_id:           Tenant scope — always required.
            include_inactive: If True, include deactivated clients (admin view).
                              Default is False (standard management UI).
        """
        query = select(Client).where(Client.org_id == org_id)
        if not include_inactive:
            query = query.where(Client.is_active.is_(True))
        query = query.order_by(Client.name)
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, client: Client) -> Client:
        """
        Persist a new Client record and return the saved instance.

        The caller constructs the Client ORM object; this method handles
        the add/commit/refresh cycle so the returned object has DB-generated
        fields (id, created_at, updated_at).
        """
        db.add(client)
        await db.commit()
        await db.refresh(client)
        logger.debug(
            "clients.repo.created client_id=%s org_id=%s slug=%s",
            client.id,
            client.org_id,
            client.slug,
        )
        return client

    @staticmethod
    async def update(db: AsyncSession, client: Client) -> Client:
        """
        Commit pending changes to an existing Client and return the refreshed instance.

        The caller mutates the ORM object fields directly before calling this method.
        Commit triggers the onupdate lambda on updated_at automatically.
        """
        await db.commit()
        await db.refresh(client)
        logger.debug(
            "clients.repo.updated client_id=%s org_id=%s",
            client.id,
            client.org_id,
        )
        return client

    @staticmethod
    async def get_brand_counts_by_org(
        db: AsyncSession,
        org_id: UUID,
    ) -> dict[UUID, int]:
        """
        Return brand counts keyed by client_id for all clients in an org.

        Single grouped COUNT query — avoids N+1 when populating brand_count
        for each client in list_clients(). Only counts brands explicitly assigned
        to a client (client_id IS NOT NULL) within the org.

        SECURITY: filters by org_id so brands from other orgs are never counted.
        """
        from app.catalog.models import Brand  # noqa: PLC0415

        result = await db.execute(
            select(Brand.client_id, func.count().label("cnt"))
            .where(
                Brand.org_id == org_id,
                Brand.client_id.isnot(None),
            )
            .group_by(Brand.client_id)
        )
        return {row.client_id: row.cnt for row in result}

    @staticmethod
    async def get_brand_count(db: AsyncSession, client_id: UUID, org_id: UUID) -> int:
        """
        Return the number of brands assigned to a single client within an org.

        SECURITY: must filter by org_id — a client_id UUID is org-scoped but
        the query must enforce this explicitly to prevent cross-tenant count leaks.
        """
        from app.catalog.models import Brand  # noqa: PLC0415

        result = await db.execute(
            select(func.count()).where(
                Brand.client_id == client_id,
                Brand.org_id == org_id,
            )
        )
        return int(result.scalar_one())
