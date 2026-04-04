"""
HTTP routes for the clients management domain.

Endpoints:
  POST   /api/v1/clients/             — create client (admin only)
  GET    /api/v1/clients/             — list clients (any authenticated user)
  GET    /api/v1/clients/{client_id}  — get client detail (any authenticated user)
  PATCH  /api/v1/clients/{client_id}  — update client (admin, manager)
  DELETE /api/v1/clients/{client_id}  — deactivate client (admin only)

All routes require JWT authentication. Role enforcement is via require_role().
Service layer raises ValueError (→ 409), KeyError (→ 404), PermissionError (→ 403).

NOTE: get_current_user returns User (not AuthContext — that is introduced in Task C).
org_id is extracted directly from current_user.org_id.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import service
from app.clients.schemas import (
    ClientCreateRequest,
    ClientListResponse,
    ClientResponse,
    ClientUpdateRequest,
)
from app.core.deps import get_current_user, get_db, require_role
from app.core.security import AuthContext

logger = logging.getLogger(__name__)

router = APIRouter(tags=["clients"])


@router.post(
    "/",
    response_model=ClientResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create client",
)
async def create_client(
    body: ClientCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthContext = Depends(require_role("admin")),
) -> ClientResponse:
    """
    Create a new client within the authenticated user's organisation.

    slug must be unique among active clients in the org (^[a-z0-9-]+$).
    Returns 409 if the slug is already taken.
    Requires admin role.
    """
    try:
        return await service.create_client(
            db=db,
            request=body,
            org_id=current_user.org_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )


@router.get(
    "/",
    response_model=ClientListResponse,
    summary="List clients",
)
async def list_clients(
    db: AsyncSession = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
) -> ClientListResponse:
    """
    Return all active clients for the authenticated user's organisation.

    Includes brand_count per client for display in the management UI.
    Returns active clients only (include_inactive=False).
    Any authenticated user may list clients.
    """
    try:
        return await service.list_clients(
            db=db,
            org_id=current_user.org_id,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )


@router.get(
    "/{client_id}",
    response_model=ClientResponse,
    summary="Get client",
)
async def get_client(
    client_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
) -> ClientResponse:
    """
    Return a single client by ID, scoped to the authenticated user's org.

    Returns 404 for both "not found" and "wrong org" cases to prevent enumeration.
    Any authenticated user may view client details.
    """
    try:
        return await service.get_client(
            db=db,
            client_id=client_id,
            org_id=current_user.org_id,
        )
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CLIENT_NOT_FOUND",
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )


@router.patch(
    "/{client_id}",
    response_model=ClientResponse,
    summary="Update client",
)
async def update_client(
    client_id: UUID,
    body: ClientUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthContext = Depends(require_role("admin", "manager")),
) -> ClientResponse:
    """
    Apply a partial update to a client record.

    slug is not updatable. Only name, contact_email, and logo_url may be changed.
    Returns 404 if the client is not found in the authenticated user's org.
    Requires admin or manager role.
    """
    try:
        return await service.update_client(
            db=db,
            client_id=client_id,
            org_id=current_user.org_id,
            request=body,
        )
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CLIENT_NOT_FOUND",
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )


@router.delete(
    "/{client_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate client",
)
async def deactivate_client(
    client_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AuthContext = Depends(require_role("admin")),
) -> None:
    """
    Soft-delete a client by marking is_active=False.

    Does not delete the client record or any associated data.
    Brands assigned to this client retain their client_id FK.
    The deactivated client will no longer be available for context switching.
    Returns 404 if the client is not found in the authenticated user's org.
    Requires admin role.
    """
    try:
        await service.deactivate_client(
            db=db,
            client_id=client_id,
            org_id=current_user.org_id,
        )
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CLIENT_NOT_FOUND",
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )
