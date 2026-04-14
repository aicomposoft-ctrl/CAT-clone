"""
HTTP routes for the reviews domain.

Endpoints (all GET, all roles):
  GET /api/v1/reviews/summary   — per-platform sentiment breakdown
  GET /api/v1/reviews/history   — paginated reviews with optional filters
  GET /api/v1/reviews/stats     — aggregated stats + weekly trend

Tenant isolation gate: every handler calls _require_sku_access() before
delegating to the service layer. This validates that the requested sku_id
belongs to the current user's org. If not → HTTP 404 (not 403, to avoid
leaking existence of other orgs' SKUs).

Rate limiting: 60 req/min per user via Redis sliding window.
Graceful degradation: limit not enforced when REDIS_URL is unset (dev/test).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.catalog.repository import SKURepository
from app.core.deps import get_current_user, get_db
from app.reviews import service
from app.reviews.service import validate_date_range
from app.reviews.schemas import (
    ReviewHistoryResponse,
    ReviewStats,
    ReviewSummaryResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_RATE_LIMIT_REVIEWS = 60  # req/min per user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _enforce_rate_limit(user_id: UUID) -> None:
    """
    Sliding-window rate limit: 60 req/min per user.

    Uses Redis sorted sets. No-op when REDIS_URL is not set.
    """
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        return
    try:
        from redis.asyncio import from_url as async_redis_from_url

        redis = await async_redis_from_url(redis_url, decode_responses=True)
        try:
            key = f"rate:reviews:{user_id}"
            now_ms = int(time.time() * 1000)
            window_ms = 60 * 1000

            pipe = redis.pipeline()
            pipe.zremrangebyscore(key, 0, now_ms - window_ms)
            pipe.zadd(key, {str(now_ms): now_ms})
            pipe.zcard(key)
            pipe.expire(key, 60)
            results = await pipe.execute()

            count_in_window = results[2]
            if count_in_window > _RATE_LIMIT_REVIEWS:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="RATE_LIMIT_EXCEEDED",
                    headers={"Retry-After": "60"},
                )
        finally:
            await redis.aclose()
    except HTTPException:
        raise
    except Exception:
        logger.warning("Rate limiter unavailable — allowing request", exc_info=True)


async def _require_sku_access(
    sku_id: UUID,
    db: AsyncSession,
    current_user: User,
) -> None:
    """
    Validate that sku_id belongs to current_user.org_id.
    Raises HTTP 404 on mismatch to avoid leaking existence of other orgs' data.
    """
    sku = await SKURepository.get_by_id_and_org(
        db, sku_id=sku_id, org_id=current_user.org_id
    )
    if sku is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SKU_NOT_FOUND")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/sentiment", summary="Org-wide sentiment breakdown by brand")
async def get_org_sentiment(
    platform_id: Optional[UUID] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Aggregate sentiment (positive/neutral/negative %) per brand for the whole org.
    No sku_id required — covers all SKUs in the org.
    """
    await _enforce_rate_limit(current_user.id)

    try:
        date_from_resolved, date_to_resolved = validate_date_range(date_from, date_to)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    from sqlalchemy import text

    # Build parameterized SQL without f-string interpolation of user-controlled values.
    # platform_id filter is added as a separate clause; the value is always bound via :platform_id.
    # Org-scope is enforced via s.org_id = :org_id (derived from JWT, never from request params).
    base_sql = """
        SELECT
            b.id                                                           AS brand_id,
            b.name                                                         AS brand_name,
            COUNT(*)                                                       AS total_reviews,
            COUNT(*) FILTER (WHERE r.sentiment = 'positive')               AS positive_count,
            COUNT(*) FILTER (WHERE r.sentiment = 'neutral')                AS neutral_count,
            COUNT(*) FILTER (WHERE r.sentiment = 'negative')               AS negative_count
        FROM reviews r
        JOIN sku_platforms sp ON sp.id = r.sku_platform_id
        JOIN skus s           ON s.id  = sp.sku_id
        JOIN brands b         ON b.id  = s.brand_id
        WHERE s.org_id = :org_id
          AND r.review_date BETWEEN :date_from AND :date_to
    """
    params: dict = {
        "org_id": str(current_user.org_id),
        "date_from": date_from_resolved,
        "date_to": date_to_resolved,
    }
    if platform_id:
        base_sql += " AND sp.platform_id = :platform_id"
        params["platform_id"] = str(platform_id)

    base_sql += " GROUP BY b.id, b.name ORDER BY total_reviews DESC"
    stmt = text(base_sql)

    rows = (await db.execute(stmt, params)).fetchall()

    items = []
    for row in rows:
        total = row.total_reviews or 1
        items.append({
            "brand_id": str(row.brand_id),
            "brand_name": row.brand_name,
            "total_reviews": row.total_reviews,
            "positive_pct": round(row.positive_count / total * 100, 1),
            "neutral_pct": round(row.neutral_count / total * 100, 1),
            "negative_pct": round(row.negative_count / total * 100, 1),
        })

    return {"items": items, "date_from": date_from_resolved, "date_to": date_to_resolved}


@router.get("/summary", response_model=ReviewSummaryResponse)
async def get_review_summary(
    sku_id: UUID,
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReviewSummaryResponse:
    """Per-platform sentiment breakdown for a SKU over a date range."""
    await _enforce_rate_limit(current_user.id)
    await _require_sku_access(sku_id, db, current_user)

    try:
        date_from, date_to = validate_date_range(date_from, date_to)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return await service.get_review_summary(
        db=db,
        org_id=current_user.org_id,
        sku_id=sku_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/history", response_model=ReviewHistoryResponse)
async def get_review_history(
    sku_id: UUID,
    platform_id: Optional[UUID] = Query(None),
    sentiment: Optional[Literal["positive", "neutral", "negative"]] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReviewHistoryResponse:
    """Paginated reviews with optional sentiment and platform filters, ordered by date DESC."""
    await _enforce_rate_limit(current_user.id)
    await _require_sku_access(sku_id, db, current_user)

    try:
        date_from, date_to = validate_date_range(date_from, date_to)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return await service.get_review_history(
        db=db,
        org_id=current_user.org_id,
        sku_id=sku_id,
        platform_id=platform_id,
        sentiment=sentiment,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


@router.get("/stats", response_model=ReviewStats)
async def get_review_stats(
    sku_id: UUID,
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReviewStats:
    """Aggregated rating + sentiment statistics with weekly trend."""
    await _enforce_rate_limit(current_user.id)
    await _require_sku_access(sku_id, db, current_user)

    try:
        date_from, date_to = validate_date_range(date_from, date_to)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return await service.get_review_stats(
        db=db,
        org_id=current_user.org_id,
        sku_id=sku_id,
        date_from=date_from,
        date_to=date_to,
    )
