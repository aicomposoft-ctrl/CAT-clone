"""
Public read-only endpoints for external integrations (Power BI, 3rd-party tools).

All routes authenticate via X-API-Key header (get_org_by_api_key dependency).
All DB queries are scoped to org.id — org is resolved from the API key, never
from client-supplied parameters.

Multi-tenant isolation rule: org_id ALWAYS comes from `org.id` (the Organization
object returned by the API key dependency). Never accept org_id from query params.

Endpoints:
  GET /api/v1/public/skus                       — paginated SKUs with latest content scores
  GET /api/v1/public/skus/{sku_id}/content-score — single SKU detailed score
  GET /api/v1/public/stock                       — stock distribution (latest in_stock per platform)
  GET /api/v1/public/prices                      — latest price per SKU x platform
  GET /api/v1/public/reviews/summary             — sentiment summary grouped by brand
  GET /api/v1/public/alerts                      — triggered alert events (recent N days)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Organization
from app.core.deps import get_db, get_org_by_api_key
from app.public.schemas import (
    PublicAlertItem,
    PublicAlertResponse,
    PublicPriceItem,
    PublicPriceResponse,
    PublicReviewsSummary,
    PublicReviewsSummaryResponse,
    PublicSKUItem,
    PublicSKUListResponse,
    PublicStockItem,
    PublicStockResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["public"])

# ---------------------------------------------------------------------------
# Severity and message helpers for alert events
# ---------------------------------------------------------------------------

_ALERT_SEVERITY: dict[str, str] = {
    "content_drop": "critical",
    "oos": "warning",
}

_ALERT_MESSAGE: dict[str, str] = {
    "content_drop": "Content score dropped below threshold",
    "oos": "Product is out of stock",
}


def _alert_severity(alert_type: str) -> str:
    return _ALERT_SEVERITY.get(alert_type, "warning")


def _alert_message(alert_type: str) -> str:
    return _ALERT_MESSAGE.get(alert_type, f"Alert triggered: {alert_type}")


# ---------------------------------------------------------------------------
# GET /skus — paginated SKU list with latest content scores
# ---------------------------------------------------------------------------


@router.get(
    "/skus",
    response_model=PublicSKUListResponse,
    summary="List SKUs with latest content scores",
)
async def list_skus(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(50, ge=1, le=500, description="Items per page (max 500)"),
    brand_id: Optional[UUID] = Query(None, description="Filter by brand UUID"),
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_org_by_api_key),
) -> PublicSKUListResponse:
    """
    Return a paginated list of SKUs with their latest content scores.

    Latest score is resolved per SKU using DISTINCT ON (sku_id) ordered by
    scored_at DESC — takes the most recent score record across all platforms.

    Multi-tenant: all rows are filtered by skus.org_id = org.id.
    """
    offset = (page - 1) * page_size

    brand_filter = "AND s.brand_id = :brand_id" if brand_id else ""

    # Subquery: latest content_score per sku (across all platforms)
    # Uses DISTINCT ON (s.id) to get the newest scored_at row per sku.
    # platform_count is computed via a separate subquery for accuracy.
    base_sql = f"""
        WITH latest_score AS (
            SELECT DISTINCT ON (s.id)
                s.id                    AS sku_id,
                s.name                  AS sku_name,
                s.article               AS external_id,
                b.name                  AS brand_name,
                cs.content_total,
                cs.image_score,
                cs.description_score,
                cs.composition_score    AS completeness_score,
                cs.scored_at::timestamptz AS scored_at
            FROM skus s
            JOIN brands b              ON b.id = s.brand_id
            LEFT JOIN sku_platforms sp ON sp.sku_id = s.id AND sp.is_monitored = TRUE
            LEFT JOIN content_scores cs ON cs.sku_platform_id = sp.id
            WHERE s.org_id = :org_id
              AND s.is_active = TRUE
              {brand_filter}
            ORDER BY s.id, cs.scored_at DESC NULLS LAST
        ),
        platform_counts AS (
            SELECT sp2.sku_id, COUNT(*) AS platform_count
            FROM sku_platforms sp2
            JOIN skus s2 ON s2.id = sp2.sku_id
            WHERE s2.org_id = :org_id
              AND sp2.is_monitored = TRUE
            GROUP BY sp2.sku_id
        )
        SELECT
            ls.sku_id,
            ls.sku_name,
            ls.external_id,
            ls.brand_name,
            ls.content_total,
            ls.image_score,
            ls.description_score,
            ls.completeness_score,
            ls.scored_at,
            COALESCE(pc.platform_count, 0) AS platform_count
        FROM latest_score ls
        LEFT JOIN platform_counts pc ON pc.sku_id = ls.sku_id
    """

    params: dict = {"org_id": str(org.id)}
    if brand_id:
        params["brand_id"] = str(brand_id)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM ({base_sql}) counted"), params
    )
    total = count_result.scalar_one()

    data_result = await db.execute(
        text(f"{base_sql} ORDER BY ls.sku_name ASC LIMIT :limit OFFSET :offset"),
        {**params, "limit": page_size, "offset": offset},
    )
    rows = data_result.fetchall()

    items = [
        PublicSKUItem(
            sku_id=row.sku_id,
            sku_name=row.sku_name,
            external_id=row.external_id,
            brand_name=row.brand_name,
            content_total=float(row.content_total) if row.content_total is not None else None,
            image_score=float(row.image_score) if row.image_score is not None else None,
            description_score=float(row.description_score) if row.description_score is not None else None,
            completeness_score=float(row.completeness_score) if row.completeness_score is not None else None,
            scored_at=row.scored_at,
            platform_count=int(row.platform_count),
        )
        for row in rows
    ]

    return PublicSKUListResponse(items=items, total=total, page=page, page_size=page_size)


# ---------------------------------------------------------------------------
# GET /skus/{sku_id}/content-score — single SKU detailed score
# ---------------------------------------------------------------------------


@router.get(
    "/skus/{sku_id}/content-score",
    response_model=PublicSKUItem,
    summary="Get latest content score for a single SKU",
)
async def get_sku_content_score(
    sku_id: UUID,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_org_by_api_key),
) -> PublicSKUItem:
    """
    Return the latest content score for a single SKU.

    Returns 404 if the SKU does not exist or belongs to a different org.
    Multi-tenant: sku ownership verified via skus.org_id = org.id.
    """
    stmt = text("""
        SELECT DISTINCT ON (s.id)
            s.id                    AS sku_id,
            s.name                  AS sku_name,
            s.article               AS external_id,
            b.name                  AS brand_name,
            cs.content_total,
            cs.image_score,
            cs.description_score,
            cs.composition_score    AS completeness_score,
            cs.scored_at::timestamptz AS scored_at,
            (
                SELECT COUNT(*)
                FROM sku_platforms sp2
                WHERE sp2.sku_id = s.id AND sp2.is_monitored = TRUE
            ) AS platform_count
        FROM skus s
        JOIN brands b              ON b.id = s.brand_id
        LEFT JOIN sku_platforms sp ON sp.sku_id = s.id AND sp.is_monitored = TRUE
        LEFT JOIN content_scores cs ON cs.sku_platform_id = sp.id
        WHERE s.id     = :sku_id
          AND s.org_id = :org_id
          AND s.is_active = TRUE
        ORDER BY s.id, cs.scored_at DESC NULLS LAST
        LIMIT 1
    """)

    result = await db.execute(stmt, {"sku_id": str(sku_id), "org_id": str(org.id)})
    row = result.fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SKU_NOT_FOUND",
        )

    return PublicSKUItem(
        sku_id=row.sku_id,
        sku_name=row.sku_name,
        external_id=row.external_id,
        brand_name=row.brand_name,
        content_total=float(row.content_total) if row.content_total is not None else None,
        image_score=float(row.image_score) if row.image_score is not None else None,
        description_score=float(row.description_score) if row.description_score is not None else None,
        completeness_score=float(row.completeness_score) if row.completeness_score is not None else None,
        scored_at=row.scored_at,
        platform_count=int(row.platform_count),
    )


# ---------------------------------------------------------------------------
# GET /stock — latest in_stock status per SKU x platform
# ---------------------------------------------------------------------------


@router.get(
    "/stock",
    response_model=PublicStockResponse,
    summary="Get stock distribution (latest in_stock per SKU x platform)",
)
async def get_stock(
    sku_id: Optional[UUID] = Query(None, description="Filter by SKU UUID"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(50, ge=1, le=500, description="Items per page (max 500)"),
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_org_by_api_key),
) -> PublicStockResponse:
    """
    Return the latest in_stock status per (SKU x platform) pair.

    Stock data is sourced from content_scores.in_stock (populated by collector).
    Uses DISTINCT ON (sku_platform_id) to get the most recent row per pair.

    Multi-tenant: enforced via skus.org_id = org.id JOIN.
    """
    offset = (page - 1) * page_size
    sku_filter = "AND s.id = :sku_id" if sku_id else ""

    base_sql = f"""
        WITH latest_stock AS (
            SELECT DISTINCT ON (cs.sku_platform_id)
                s.id                        AS sku_id,
                s.name                      AS sku_name,
                p.id                        AS platform_id,
                p.name                      AS platform_name,
                cs.in_stock,
                NULL::text                  AS stock_status,
                cs.scored_at::timestamptz   AS last_checked_at
            FROM content_scores cs
            JOIN sku_platforms sp ON sp.id  = cs.sku_platform_id
            JOIN skus s           ON s.id   = sp.sku_id
            JOIN platforms p      ON p.id   = sp.platform_id
            WHERE s.org_id = :org_id
              AND cs.in_stock IS NOT NULL
              {sku_filter}
            ORDER BY cs.sku_platform_id, cs.scored_at DESC
        )
        SELECT * FROM latest_stock
    """

    params: dict = {"org_id": str(org.id)}
    if sku_id:
        params["sku_id"] = str(sku_id)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM ({base_sql}) counted"), params
    )
    total = count_result.scalar_one()

    data_result = await db.execute(
        text(f"{base_sql} ORDER BY sku_name ASC, platform_name ASC LIMIT :limit OFFSET :offset"),
        {**params, "limit": page_size, "offset": offset},
    )
    rows = data_result.fetchall()

    items = [
        PublicStockItem(
            sku_id=row.sku_id,
            sku_name=row.sku_name,
            platform_id=row.platform_id,
            platform_name=row.platform_name,
            in_stock=bool(row.in_stock),
            stock_status=row.stock_status,
            last_checked_at=row.last_checked_at,
        )
        for row in rows
    ]

    return PublicStockResponse(items=items, total=total)


# ---------------------------------------------------------------------------
# GET /prices — latest price snapshot per SKU x platform
# ---------------------------------------------------------------------------


@router.get(
    "/prices",
    response_model=PublicPriceResponse,
    summary="Get latest prices per SKU x platform",
)
async def get_prices(
    sku_id: Optional[UUID] = Query(None, description="Filter by SKU UUID"),
    platform_id: Optional[UUID] = Query(None, description="Filter by platform UUID"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(50, ge=1, le=500, description="Items per page (max 500)"),
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_org_by_api_key),
) -> PublicPriceResponse:
    """
    Return the latest price snapshot per (SKU x platform) pair.

    Uses DISTINCT ON (sku_platform_id) ordered by collected_at DESC to get
    the most recent price for each monitored platform.

    currency defaults to "RUB" — price_snapshots has no currency column.
    Multi-tenant: enforced via skus.org_id = org.id JOIN.
    """
    sku_filter = "AND s.id = :sku_id" if sku_id else ""
    platform_filter = "AND sp.platform_id = :platform_id" if platform_id else ""

    stmt_sql = f"""
        SELECT DISTINCT ON (ps.sku_platform_id)
            s.id            AS sku_id,
            s.name          AS sku_name,
            p.id            AS platform_id,
            p.name          AS platform_name,
            ps.price,
            'RUB'::text     AS currency,
            ps.discount_pct,
            ps.collected_at AS snapshot_at
        FROM price_snapshots ps
        JOIN sku_platforms sp ON sp.id  = ps.sku_platform_id
        JOIN skus s           ON s.id   = sp.sku_id
        JOIN platforms p      ON p.id   = sp.platform_id
        WHERE s.org_id = :org_id
          {sku_filter}
          {platform_filter}
        ORDER BY ps.sku_platform_id, ps.collected_at DESC
    """

    params: dict = {"org_id": str(org.id)}
    if sku_id:
        params["sku_id"] = str(sku_id)
    if platform_id:
        params["platform_id"] = str(platform_id)

    offset = (page - 1) * page_size
    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM ({stmt_sql}) counted"), params
    )
    total = count_result.scalar_one()

    result = await db.execute(
        text(f"{stmt_sql} ORDER BY sku_name ASC, platform_name ASC LIMIT :limit OFFSET :offset"),
        {**params, "limit": page_size, "offset": offset},
    )
    rows = result.fetchall()

    items = [
        PublicPriceItem(
            sku_id=row.sku_id,
            sku_name=row.sku_name,
            platform_id=row.platform_id,
            platform_name=row.platform_name,
            price=float(row.price) if row.price is not None else None,
            currency=row.currency,
            discount_pct=float(row.discount_pct) if row.discount_pct is not None else None,
            snapshot_at=row.snapshot_at,
        )
        for row in rows
    ]

    return PublicPriceResponse(items=items, total=total)


# ---------------------------------------------------------------------------
# GET /reviews/summary — sentiment summary grouped by brand
# ---------------------------------------------------------------------------


@router.get(
    "/reviews/summary",
    response_model=PublicReviewsSummaryResponse,
    summary="Get sentiment summary grouped by brand",
)
async def get_reviews_summary(
    brand_id: Optional[UUID] = Query(None, description="Filter by brand UUID"),
    platform_id: Optional[UUID] = Query(None, description="Filter by platform UUID"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page (max 200)"),
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_org_by_api_key),
) -> PublicReviewsSummaryResponse:
    """
    Return aggregated sentiment summary grouped by brand.

    Percentages are derived from counts: positive_pct = positive_count / total * 100.
    avg_rating is None when no reviews exist for that brand.

    Multi-tenant: enforced via skus.org_id = org.id JOIN.
    """
    brand_filter = "AND s.brand_id = :brand_id" if brand_id else ""
    platform_filter = "AND sp.platform_id = :platform_id" if platform_id else ""

    stmt_sql = f"""
        SELECT
            b.id                                                           AS brand_id,
            b.name                                                         AS brand_name,
            COUNT(r.id)                                                    AS total_reviews,
            ROUND(AVG(r.rating)::numeric, 2)                               AS avg_rating,
            ROUND(
                COUNT(r.id) FILTER (WHERE r.sentiment = 'positive')::numeric
                / NULLIF(COUNT(r.id), 0) * 100,
                2
            )                                                              AS positive_pct,
            ROUND(
                COUNT(r.id) FILTER (WHERE r.sentiment = 'negative')::numeric
                / NULLIF(COUNT(r.id), 0) * 100,
                2
            )                                                              AS negative_pct,
            ROUND(
                COUNT(r.id) FILTER (WHERE r.sentiment = 'neutral')::numeric
                / NULLIF(COUNT(r.id), 0) * 100,
                2
            )                                                              AS neutral_pct
        FROM brands b
        JOIN skus s           ON s.brand_id = b.id
        JOIN sku_platforms sp ON sp.sku_id  = s.id
        LEFT JOIN reviews r   ON r.sku_platform_id = sp.id
        WHERE s.org_id = :org_id
          {brand_filter}
          {platform_filter}
        GROUP BY b.id, b.name
        ORDER BY b.name ASC
    """

    params: dict = {"org_id": str(org.id)}
    if brand_id:
        params["brand_id"] = str(brand_id)
    if platform_id:
        params["platform_id"] = str(platform_id)

    offset = (page - 1) * page_size
    result = await db.execute(
        text(f"{stmt_sql} LIMIT :limit OFFSET :offset"),
        {**params, "limit": page_size, "offset": offset},
    )
    rows = result.fetchall()

    items = [
        PublicReviewsSummary(
            brand_id=row.brand_id,
            brand_name=row.brand_name,
            total_reviews=int(row.total_reviews),
            avg_rating=float(row.avg_rating) if row.avg_rating is not None else None,
            positive_pct=float(row.positive_pct) if row.positive_pct is not None else None,
            negative_pct=float(row.negative_pct) if row.negative_pct is not None else None,
            neutral_pct=float(row.neutral_pct) if row.neutral_pct is not None else None,
        )
        for row in rows
    ]

    return PublicReviewsSummaryResponse(items=items, total=len(items))


# ---------------------------------------------------------------------------
# GET /alerts — triggered alert events (last N days)
# ---------------------------------------------------------------------------


@router.get(
    "/alerts",
    response_model=PublicAlertResponse,
    summary="Get triggered alert events for the last N days",
)
async def get_alerts(
    days: int = Query(30, ge=1, le=365, description="Number of days to look back (default 30)"),
    severity: Optional[str] = Query(None, description="Filter by severity: 'critical' or 'warning'"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(50, ge=1, le=500, description="Items per page (max 500)"),
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_org_by_api_key),
) -> PublicAlertResponse:
    """
    Return triggered alert events from the last N days.

    severity is derived from alert_type:
      - content_drop -> "critical"
      - oos           -> "warning"

    Filtering by severity='critical' returns only content_drop events.
    Filtering by severity='warning'  returns only oos events.

    sku_name and platform_name are resolved by JOINing through sku_platforms.
    Multi-tenant: enforced via alert_events.org_id = org.id.
    """
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)

    # Map severity filter back to alert_type values
    alert_type_filter = ""
    params: dict = {"org_id": str(org.id), "since": since}

    if severity == "critical":
        alert_type_filter = "AND ae.alert_type = 'content_drop'"
    elif severity == "warning":
        alert_type_filter = "AND ae.alert_type = 'oos'"

    stmt_sql = f"""
        SELECT
            ae.id               AS alert_id,
            ae.alert_type,
            s.id                AS sku_id,
            s.name              AS sku_name,
            p.name              AS platform_name,
            ae.triggered_at
        FROM alert_events ae
        JOIN sku_platforms sp ON sp.id = ae.sku_platform_id
        JOIN skus s           ON s.id  = sp.sku_id
        JOIN platforms p      ON p.id  = sp.platform_id
        WHERE ae.org_id = :org_id
          AND ae.triggered_at >= :since
          {alert_type_filter}
        ORDER BY ae.triggered_at DESC
    """

    offset = (page - 1) * page_size
    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM ({stmt_sql}) counted"), params
    )
    total = count_result.scalar_one()

    result = await db.execute(
        text(f"{stmt_sql} LIMIT :limit OFFSET :offset"),
        {**params, "limit": page_size, "offset": offset},
    )
    rows = result.fetchall()

    items = [
        PublicAlertItem(
            alert_id=row.alert_id,
            alert_type=row.alert_type,
            sku_id=row.sku_id,
            sku_name=row.sku_name,
            platform_name=row.platform_name,
            severity=_alert_severity(row.alert_type),
            message=_alert_message(row.alert_type),
            triggered_at=row.triggered_at,
        )
        for row in rows
    ]

    return PublicAlertResponse(items=items, total=total)
