"""
HTTP routes for the content scores domain.

Endpoints:
  GET /api/v1/content/scores           — paginated scores list (all roles)
  GET /api/v1/content/scores/{id}/drilldown — drill-down with history (all roles)
"""

import logging
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.deps import get_current_user, get_db
from app.content import service
from app.content.schemas import ContentScoreDrilldown, ContentScorePage

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/scores",
    response_model=ContentScorePage,
    summary="List content scores",
)
async def list_content_scores(
    platform_id: Optional[UUID] = Query(None),
    brand_id: Optional[UUID] = Query(None),
    score_max: Optional[float] = Query(None, ge=0, le=100),
    score_min: Optional[float] = Query(None, ge=0, le=100),
    scored_at: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContentScorePage:
    """
    Return paginated content scores for the authenticated user's org.

    Defaults to the latest score per (SKU, platform) pair.
    Pass scored_at to query a specific date.
    """
    return await service.get_content_scores(
        db,
        current_user.org_id,
        platform_id=platform_id,
        brand_id=brand_id,
        score_max=score_max,
        score_min=score_min,
        scored_at=scored_at,
        page=page,
        size=size,
    )


@router.get(
    "/scores/{sku_platform_id}/drilldown",
    response_model=ContentScoreDrilldown,
    summary="Content score drill-down with history",
)
async def get_content_drilldown(
    sku_platform_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContentScoreDrilldown:
    """
    Return the latest score for a (SKU, platform) pair with:
    - reference material for side-by-side comparison
    - 30-day content_total history
    """
    result = await service.get_content_drilldown(db, current_user.org_id, sku_platform_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CONTENT_SCORE_NOT_FOUND",
        )
    return result
