"""
HTTP routes for the stock domain.

Thin layer: validates HTTP concerns (file size, content-type, role),
delegates immediately to service functions, maps domain errors to HTTPException.

Endpoints:
  POST   /api/v1/stock/distribution-plan   — upload CSV (admin, manager)
  GET    /api/v1/stock/distribution-plan   — paginated listing (all roles)
  DELETE /api/v1/stock/distribution-plan/{id} — delete single plan (admin, manager)
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.deps import get_current_user, get_db, require_role
from app.stock import service
from app.stock.schemas import (
    DistributionPlanPage,
    DistributionPlanRow,
    DistributionPlanUploadResponse,
)
from app.stock.service import ServiceValidationError

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB
_ALLOWED_CONTENT_TYPES = {"text/csv", "application/csv", "application/octet-stream"}


@router.post(
    "/distribution-plan",
    response_model=DistributionPlanUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload distribution plan CSV",
)
async def upload_distribution_plan(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "manager")),
) -> DistributionPlanUploadResponse:
    """
    Import a distribution plan from a CSV file.

    Returns the count of imported rows plus any row-level errors.
    HTTP 422 is returned only for file-level failures (wrong type, empty, bad header).
    Row-level errors are returned in the response body with HTTP 200.
    """
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="INVALID_CONTENT_TYPE: expected text/csv",
        )

    raw_bytes = await file.read()

    if not raw_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="EMPTY_FILE",
        )

    if len(raw_bytes) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="FILE_TOO_LARGE: maximum 5 MB",
        )

    try:
        return await service.upload_distribution_plan(
            db=db,
            raw_bytes=raw_bytes,
            org_id=current_user.org_id,
        )
    except ServiceValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception:
        logger.exception("Unexpected error in distribution plan upload")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="INTERNAL_ERROR",
        )


@router.get(
    "/distribution-plan",
    response_model=DistributionPlanPage,
    summary="List distribution plans",
)
async def list_distribution_plans(
    platform_id: UUID | None = Query(None),
    week_number: int | None = Query(None, ge=1, le=53),
    year: int | None = Query(None, ge=2000, le=2100),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DistributionPlanPage:
    """Return paginated distribution plans for the authenticated user's org."""
    try:
        items, total = await service.list_distribution_plans(
            db=db,
            org_id=current_user.org_id,
            platform_id=platform_id,
            week_number=week_number,
            year=year,
            page=page,
            size=size,
        )
        return DistributionPlanPage(items=items, total=total, page=page, size=size)
    except Exception:
        logger.exception("Error listing distribution plans")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="INTERNAL_ERROR",
        )


@router.delete(
    "/distribution-plan/{plan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a distribution plan row",
)
async def delete_distribution_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "manager")),
) -> None:
    """
    Delete a distribution plan row.

    Returns 404 when the plan does not exist OR belongs to a different org
    (prevents leaking existence of cross-tenant plan IDs).
    """
    deleted = await service.delete_distribution_plan(
        db=db,
        plan_id=plan_id,
        org_id=current_user.org_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PLAN_NOT_FOUND",
        )
