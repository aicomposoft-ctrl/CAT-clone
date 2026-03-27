"""
Reference upload routes for CAT API.

Mounted on /api/v1/skus/{sku_id}/reference via main.py:
  POST   /api/v1/skus/{sku_id}/reference/image       — upload reference image → 202
  PATCH  /api/v1/skus/{sku_id}/reference/text        — set description + composition → 202
  GET    /api/v1/skus/{sku_id}/reference/image-url   — get presigned URL → 200

All business logic delegated to reference_service.
Domain errors mapped: LookupError → 404, ValueError → 422, RuntimeError → 503.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.catalog import reference_service
from app.catalog.reference_schemas import (
    PresignedUrlResponse,
    ReferenceImageUploadResponse,
    ReferenceTextRequest,
    ReferenceTextUploadResponse,
)
from app.core.deps import get_current_user, get_db, require_role
from app.core.minio_client import MinioClient

logger = logging.getLogger(__name__)

reference_router = APIRouter()


def _get_minio() -> MinioClient:
    """FastAPI dependency — builds MinioClient from environment."""
    return MinioClient.from_env()


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="INTERNAL_ERROR")


@reference_router.post(
    "/{sku_id}/reference/image",
    response_model=ReferenceImageUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_reference_image(
    sku_id: UUID,
    file: UploadFile = File(...),
    user: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
    minio: MinioClient = Depends(_get_minio),
) -> ReferenceImageUploadResponse:
    """
    Upload a reference image (JPEG/PNG/WebP, max 10 MB) for a SKU.

    Returns a presigned URL for immediate viewing and enqueues CLIP embedding computation.
    """
    # Read with a hard cap before any processing to prevent DoS via large uploads.
    # Nginx also enforces client_max_body_size; this is defence-in-depth.
    _MAX_BYTES = 10 * 1024 * 1024 + 1  # 10 MB + 1 to detect over-limit
    content = await file.read(_MAX_BYTES)
    if len(content) == _MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="FILE_TOO_LARGE",
        )
    try:
        return await reference_service.upload_reference_image(
            db,
            minio,
            user.org_id,
            sku_id,
            content,
            file.filename or "",
            file.content_type or "",
        )
    except (LookupError, ValueError, RuntimeError) as exc:
        raise _map_error(exc) from exc


@reference_router.patch(
    "/{sku_id}/reference/text",
    response_model=ReferenceTextUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_reference_text(
    sku_id: UUID,
    body: ReferenceTextRequest,
    user: User = Depends(require_role("admin", "manager")),
    db: AsyncSession = Depends(get_db),
) -> ReferenceTextUploadResponse:
    """
    Set reference description and/or composition text for a SKU.

    Enqueues multilingual-e5 embedding computation for updated fields.
    Partial updates are supported — send only the fields you want to update.
    """
    try:
        return await reference_service.upload_reference_text(
            db, user.org_id, sku_id, body
        )
    except LookupError as exc:
        raise _map_error(exc) from exc


@reference_router.get(
    "/{sku_id}/reference/image-url",
    response_model=PresignedUrlResponse,
    status_code=status.HTTP_200_OK,
)
async def get_reference_image_url(
    sku_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    minio: MinioClient = Depends(_get_minio),
) -> PresignedUrlResponse:
    """
    Get a presigned URL (valid 1 hour) for the SKU's reference image.

    Available to all authenticated roles including viewer.
    Returns 404 if no reference image has been uploaded yet.
    """
    try:
        return await reference_service.get_presigned_url(db, minio, user.org_id, sku_id)
    except (LookupError, RuntimeError) as exc:
        raise _map_error(exc) from exc
