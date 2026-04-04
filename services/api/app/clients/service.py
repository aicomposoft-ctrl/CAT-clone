"""
Clients service layer — business logic for client management.

Design rules:
- No HTTP concerns here — service functions raise ValueError or KeyError.
  The router layer catches these and converts them to HTTPException.
- No direct DB session management — db: AsyncSession is always injected by caller.
- org_id is always passed explicitly (not derived inside service functions) to
  maintain clear data-flow and testability.
- Role enforcement (admin, manager) is done in the router via require_role().
  Service functions trust that the caller has already authorised the action.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.models import Client
from app.clients.repository import ClientRepository
from app.clients.schemas import (
    ClientCreateRequest,
    ClientListResponse,
    ClientResponse,
    ClientUpdateRequest,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _build_response(client: Client, brand_count: int) -> ClientResponse:
    """Construct a ClientResponse from an ORM instance and a precomputed brand count."""
    return ClientResponse(
        id=client.id,
        name=client.name,
        slug=client.slug,
        contact_email=client.contact_email,
        logo_url=client.logo_url,
        is_active=client.is_active,
        brand_count=brand_count,
        created_at=client.created_at,
    )


# ---------------------------------------------------------------------------
# Service functions
# ---------------------------------------------------------------------------


async def create_client(
    db: AsyncSession,
    request: ClientCreateRequest,
    org_id: UUID,
) -> ClientResponse:
    """
    Create a new client within an org.

    Raises:
        ValueError("SLUG_CONFLICT"): A client with the same slug already exists
            and is active within the org. The DB partial unique index is the
            authoritative constraint; this check provides a clean error message.

    Args:
        db:      Async DB session.
        request: Validated create request (name, slug, optional contact fields).
        org_id:  Tenant scope — the org the client belongs to.

    Returns:
        ClientResponse for the newly created client (brand_count = 0).
    """
    existing = await ClientRepository.get_by_slug_and_org(db, request.slug, org_id)
    if existing is not None:
        raise ValueError("SLUG_CONFLICT")

    client = Client(
        org_id=org_id,
        name=request.name,
        slug=request.slug,
        contact_email=request.contact_email,
        logo_url=str(request.logo_url) if request.logo_url else None,
    )
    saved = await ClientRepository.create(db, client)

    logger.info(
        "clients.service.created client_id=%s org_id=%s slug=%s",
        saved.id,
        org_id,
        saved.slug,
    )

    return _build_response(saved, brand_count=0)


async def list_clients(
    db: AsyncSession,
    org_id: UUID,
    include_inactive: bool = False,
) -> ClientListResponse:
    """
    Return all clients for an org with their brand counts.

    Args:
        db:               Async DB session.
        org_id:           Tenant scope.
        include_inactive: Include deactivated clients if True (admin view only).

    Returns:
        ClientListResponse with items list and total count.
    """
    clients = await ClientRepository.list_by_org(db, org_id, include_inactive=include_inactive)

    items: list[ClientResponse] = []
    for client in clients:
        brand_count = await ClientRepository.get_brand_count(db, client.id)
        items.append(_build_response(client, brand_count))

    return ClientListResponse(items=items, total=len(items))


async def get_client(
    db: AsyncSession,
    client_id: UUID,
    org_id: UUID,
) -> ClientResponse:
    """
    Return a single client by ID, scoped to org.

    Raises:
        KeyError("CLIENT_NOT_FOUND"): Client does not exist or belongs to a
            different org. Using KeyError (not a 403-style error) because the
            distinction between "not found" and "wrong org" is not surfaced to
            the caller (prevents enumeration).

    Args:
        db:        Async DB session.
        client_id: Target client UUID.
        org_id:    Tenant scope.

    Returns:
        ClientResponse with current brand_count.
    """
    client = await ClientRepository.get_by_id_and_org(db, client_id, org_id)
    if client is None:
        raise KeyError("CLIENT_NOT_FOUND")

    brand_count = await ClientRepository.get_brand_count(db, client.id)
    return _build_response(client, brand_count)


async def update_client(
    db: AsyncSession,
    client_id: UUID,
    org_id: UUID,
    request: ClientUpdateRequest,
) -> ClientResponse:
    """
    Apply a partial update to a client record.

    Only name, contact_email, and logo_url can be updated — slug is immutable
    (used in JWT claims and report filenames; see Architecture.md § 3, § 6).
    Fields absent from the request (None) are not modified.

    Raises:
        KeyError("CLIENT_NOT_FOUND"): Client does not exist in this org.

    Args:
        db:        Async DB session.
        client_id: Target client UUID.
        org_id:    Tenant scope.
        request:   Partial update payload.

    Returns:
        Updated ClientResponse.
    """
    client = await ClientRepository.get_by_id_and_org(db, client_id, org_id)
    if client is None:
        raise KeyError("CLIENT_NOT_FOUND")

    if request.name is not None:
        client.name = request.name
    if request.contact_email is not None:
        client.contact_email = str(request.contact_email)
    if request.logo_url is not None:
        client.logo_url = request.logo_url

    updated = await ClientRepository.update(db, client)

    logger.info(
        "clients.service.updated client_id=%s org_id=%s",
        client_id,
        org_id,
    )

    brand_count = await ClientRepository.get_brand_count(db, updated.id)
    return _build_response(updated, brand_count)


async def deactivate_client(
    db: AsyncSession,
    client_id: UUID,
    org_id: UUID,
) -> None:
    """
    Soft-delete a client by setting is_active=False.

    Does NOT delete the client record or any associated brands/data. Brands
    assigned to this client retain their client_id FK but the client becomes
    inaccessible for context switching (get_active_by_id_and_org returns None).

    Raises:
        KeyError("CLIENT_NOT_FOUND"): Client does not exist in this org.

    Args:
        db:        Async DB session.
        client_id: Target client UUID.
        org_id:    Tenant scope.
    """
    client = await ClientRepository.get_by_id_and_org(db, client_id, org_id)
    if client is None:
        raise KeyError("CLIENT_NOT_FOUND")

    client.is_active = False
    await ClientRepository.update(db, client)

    logger.info(
        "clients.service.deactivated client_id=%s org_id=%s",
        client_id,
        org_id,
    )
