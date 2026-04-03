"""
HTTP routes for the prices domain.

Endpoints (all GET, all roles):
  GET /api/v1/prices/history   — time series of price snapshots
  GET /api/v1/prices/latest    — most recent price per platform
  GET /api/v1/prices/stats     — aggregated statistics over a period
  GET /api/v1/prices/anomalies — significant price changes (LAG-based)

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
from app.prices import service
from app.prices.service import _validate_date_range
from app.prices.schemas import (
    PriceAnomaliesResponse,
    PriceHistoryResponse,
    PriceLatestResponse,
    PriceStats,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_RATE_LIMIT_PRICES = 60  # req/min per user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _enforce_rate_limit(user_id: UUID) -> None:
    """
    Sliding-window rate limit: 60 req/min per user.

    Uses Redis sorted sets (same pattern as alerts POST /check).
    No-op when REDIS_URL is not set — dev/test environments work without Redis.
    """
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        return
    try:
        from redis.asyncio import from_url as async_redis_from_url

        redis = await async_redis_from_url(redis_url, decode_responses=True)
        key = f"rate:prices:{user_id}"
        now_ms = int(time.time() * 1000)
        window_ms = 60 * 1000

        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, 0, now_ms - window_ms)
        pipe.zcard(key)
        pipe.zadd(key, {str(now_ms): now_ms})
        pipe.expire(key, 60)
        results = await pipe.execute()

        count_after_trim = results[1]
        if count_after_trim >= _RATE_LIMIT_PRICES:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="RATE_LIMIT_EXCEEDED",
                headers={"Retry-After": "60"},
            )
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

    Returns None on success. Raises HTTP 404 on mismatch or missing SKU
    to avoid leaking existence of other orgs' data.
    """
    sku = await SKURepository.get_by_id_and_org(
        db, sku_id=sku_id, org_id=current_user.org_id
    )
    if sku is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SKU_NOT_FOUND")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/history", response_model=PriceHistoryResponse)
async def get_price_history(
    sku_id: UUID,
    platform_id: Optional[UUID] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(500, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PriceHistoryResponse:
    """Time series of price snapshots for a SKU, ordered by collected_at ASC."""
    await _enforce_rate_limit(current_user.id)
    await _require_sku_access(sku_id, db, current_user)

    try:
        date_from, date_to = _validate_date_range(date_from, date_to)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return await service.get_price_history(
        db=db,
        org_id=current_user.org_id,
        sku_id=sku_id,
        platform_id=platform_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


@router.get("/latest", response_model=PriceLatestResponse)
async def get_latest_prices(
    sku_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PriceLatestResponse:
    """Most recent price per platform for a SKU, ordered by price ASC."""
    await _enforce_rate_limit(current_user.id)
    await _require_sku_access(sku_id, db, current_user)

    return await service.get_latest_prices(
        db=db, org_id=current_user.org_id, sku_id=sku_id
    )


@router.get("/stats", response_model=PriceStats)
async def get_price_stats(
    sku_id: UUID,
    platform_id: Optional[UUID] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PriceStats:
    """Aggregated price statistics (min/max/avg/median/change%) for a period."""
    await _enforce_rate_limit(current_user.id)
    await _require_sku_access(sku_id, db, current_user)

    try:
        date_from, date_to = _validate_date_range(date_from, date_to)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return await service.get_price_stats(
        db=db,
        org_id=current_user.org_id,
        sku_id=sku_id,
        platform_id=platform_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/anomalies", response_model=PriceAnomaliesResponse)
async def get_price_anomalies(
    sku_id: UUID,
    platform_id: Optional[UUID] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    threshold: float = Query(10.0, ge=0.0, le=100.0),
    direction: Literal["up", "down", "both"] = Query("both"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PriceAnomaliesResponse:
    """Price anomalies: consecutive snapshots where |change%| >= threshold."""
    await _enforce_rate_limit(current_user.id)
    await _require_sku_access(sku_id, db, current_user)

    try:
        date_from, date_to = _validate_date_range(date_from, date_to)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return await service.get_price_anomalies(
        db=db,
        org_id=current_user.org_id,
        sku_id=sku_id,
        platform_id=platform_id,
        date_from=date_from,
        date_to=date_to,
        threshold=threshold,
        direction=direction,
    )
