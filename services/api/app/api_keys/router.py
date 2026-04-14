"""
HTTP routes for the api_keys management domain.

Endpoints:
  POST   /api/v1/api-keys/     — create API key (admin, manager)
  GET    /api/v1/api-keys/     — list API keys (admin, manager)
  DELETE /api/v1/api-keys/{key_id} — revoke API key (admin, manager)

All routes require JWT auth with admin or manager role.
The raw key is returned only on POST (creation). GET never returns the full key.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api_keys import service
from app.api_keys.schemas import APIKeyCreateRequest, APIKeyCreateResponse, APIKeyListResponse
from app.auth.models import User
from app.core.deps import get_db, require_role

logger = logging.getLogger(__name__)

router = APIRouter(tags=["api-keys"])


@router.post(
    "/",
    response_model=APIKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create API key",
)
async def create_api_key(
    body: APIKeyCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "manager")),
) -> APIKeyCreateResponse:
    """
    Create a new API key for the authenticated user's organisation.

    The full plaintext key is returned exactly once in the `key` field.
    It cannot be recovered after this response — store it immediately.
    Requires admin or manager role.
    """
    return await service.create_api_key(db=db, request=body, current_user=current_user)


@router.get(
    "/",
    response_model=APIKeyListResponse,
    summary="List API keys",
)
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "manager")),
) -> APIKeyListResponse:
    """
    Return all API keys for the authenticated user's organisation.

    Includes revoked keys for audit purposes.
    The raw key is never returned — only the display prefix.
    Requires admin or manager role.
    """
    return await service.list_api_keys(db=db, current_user=current_user)


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke API key",
)
async def revoke_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "manager")),
) -> None:
    """
    Revoke an API key by setting revoked=True.

    Returns 404 for both "not found" and "wrong org" cases to prevent key enumeration.
    Requires admin or manager role.
    """
    try:
        await service.revoke_api_key(db=db, key_id=key_id, current_user=current_user)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API_KEY_NOT_FOUND")
