"""
Catalog routers for CAT API.

Mounts:
  /api/v1/skus           — SKU CRUD + bulk upload
  /api/v1/brands         — Brand management (org-scoped)
  /api/v1/platforms      — Platform catalog (shared, read-only)
  /api/v1/sku-platforms  — SKU ↔ Platform linking

All routes delegate to catalog.service. This module only:
  - validates HTTP shapes via Pydantic
  - calls service methods
  - maps domain exceptions (ValueError → 409, LookupError → 404) to HTTPException
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.catalog import service as catalog_service
from app.catalog.schemas import (
    BrandCreateRequest,
    BrandListResponse,
    BrandResponse,
    BrandUpdateRequest,
    BulkUploadResponse,
    PlatformListResponse,
    SKUCreateRequest,
    SKUListFilters,
    SKUListResponse,
    SKUPlatformCreateRequest,
    SKUPlatformResponse,
    SKUResponse,
    SKUUpdateRequest,
)
from app.core.deps import get_current_user, get_db, require_role

logger = logging.getLogger(__name__)

sku_router = APIRouter()
brand_router = APIRouter()
platform_router = APIRouter()
sku_platform_router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _domain_error(exc: Exception) -> HTTPException:
    msg = str(exc)
    if isinstance(exc, LookupError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    if isinstance(exc, ValueError):
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
        if msg in (
            "SKU_ARTICLE_DUPLICATE",
            "BRAND_NAME_DUPLICATE",
            "SKU_PLATFORM_DUPLICATE",
        ):
            code = status.HTTP_409_CONFLICT
        return HTTPException(status_code=code, detail=msg)
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="INTERNAL_ERROR")


# ---------------------------------------------------------------------------
# Brand endpoints
# ---------------------------------------------------------------------------

@brand_router.post("", response_model=BrandResponse, status_code=status.HTTP_201_CREATED)
async def create_brand(
    body: BrandCreateRequest,
    user: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
) -> BrandResponse:
    try:
        return await catalog_service.create_brand(db, user.org_id, body)
    except (ValueError, LookupError) as exc:
        raise _domain_error(exc) from exc


@brand_router.get("", response_model=BrandListResponse)
async def list_brands(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BrandListResponse:
    # user is AuthContext (get_current_user returns AuthContext; User annotation
    # is kept for backward compat). client_id is None when no client context is
    # active — list_brands returns all-org brands in that case.
    client_id = getattr(user, "client_id", None)
    return await catalog_service.list_brands(db, user.org_id, client_id=client_id)


@brand_router.patch("/{brand_id}", response_model=BrandResponse)
async def update_brand(
    brand_id: UUID,
    body: BrandUpdateRequest,
    user: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
) -> BrandResponse:
    """Assign (or unassign) a brand to a client via client_id."""
    try:
        return await catalog_service.update_brand(db, user.org_id, brand_id, body)
    except LookupError as exc:
        raise _domain_error(exc) from exc


# ---------------------------------------------------------------------------
# SKU endpoints
# ---------------------------------------------------------------------------

@sku_router.get("", response_model=SKUListResponse)
async def list_skus(
    brand_id: Optional[UUID] = Query(default=None),
    include_inactive: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SKUListResponse:
    filters = SKUListFilters(brand_id=brand_id, include_inactive=include_inactive)
    return await catalog_service.list_skus(db, user.org_id, filters, limit, cursor)


@sku_router.get("/{sku_id}", response_model=SKUResponse)
async def get_sku(
    sku_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SKUResponse:
    try:
        return await catalog_service.get_sku(db, user.org_id, sku_id)
    except LookupError as exc:
        raise _domain_error(exc) from exc


@sku_router.post("", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
async def create_sku(
    body: SKUCreateRequest,
    user: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
) -> SKUResponse:
    try:
        return await catalog_service.create_sku(db, user.org_id, body)
    except (ValueError, LookupError) as exc:
        raise _domain_error(exc) from exc


@sku_router.post(
    "/bulk-upload",
    response_model=BulkUploadResponse,
    status_code=status.HTTP_200_OK,
)
async def bulk_upload_skus(
    file: UploadFile = File(...),
    user: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
) -> BulkUploadResponse:
    content = await file.read()
    try:
        result = await catalog_service.bulk_upload_skus(
            db,
            user.org_id,
            content,
            file.filename or "",
            file.content_type or "",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    if result.failed > 0 and result.imported > 0:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=status.HTTP_207_MULTI_STATUS,
            content=result.model_dump(),
        )
    return result


@sku_router.patch("/{sku_id}", response_model=SKUResponse)
async def update_sku(
    sku_id: UUID,
    body: SKUUpdateRequest,
    user: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
) -> SKUResponse:
    try:
        return await catalog_service.update_sku(db, user.org_id, sku_id, body)
    except (ValueError, LookupError) as exc:
        raise _domain_error(exc) from exc


@sku_router.delete("/{sku_id}", response_model=SKUResponse)
async def delete_sku(
    sku_id: UUID,
    user: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
) -> SKUResponse:
    try:
        return await catalog_service.delete_sku(db, user.org_id, sku_id)
    except LookupError as exc:
        raise _domain_error(exc) from exc


# ---------------------------------------------------------------------------
# Platform endpoints
# ---------------------------------------------------------------------------

@platform_router.get("", response_model=PlatformListResponse)
async def list_platforms(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlatformListResponse:
    return await catalog_service.list_platforms(db)


# ---------------------------------------------------------------------------
# SKUPlatform endpoints
# ---------------------------------------------------------------------------

@sku_platform_router.get("", response_model=list[SKUPlatformResponse])
async def list_sku_platforms(
    sku_id: UUID = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SKUPlatformResponse]:
    return await catalog_service.list_sku_platforms(db, user.org_id, sku_id)


@sku_platform_router.post("", response_model=SKUPlatformResponse, status_code=status.HTTP_201_CREATED)
async def create_sku_platform(
    body: SKUPlatformCreateRequest,
    user: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
) -> SKUPlatformResponse:
    try:
        return await catalog_service.create_sku_platform(db, user.org_id, body)
    except (ValueError, LookupError) as exc:
        raise _domain_error(exc) from exc


@sku_platform_router.delete("/{sp_id}", status_code=status.HTTP_200_OK)
async def delete_sku_platform(
    sp_id: UUID,
    user: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await catalog_service.delete_sku_platform(db, user.org_id, sp_id)
    except LookupError as exc:
        raise _domain_error(exc) from exc
    return {"message": "Unlinked successfully"}
