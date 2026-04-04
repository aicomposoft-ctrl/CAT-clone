"""
Database query layer for the content scores domain.

All queries enforce org-level tenant isolation via JOIN chain:
  content_scores → sku_platforms → skus → skus.org_id

Never pass org_id from frontend; always derive from JWT via current_user.org_id.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def fetch_scores_page(
    db: AsyncSession,
    org_id: UUID,
    *,
    platform_id: Optional[UUID] = None,
    brand_id: Optional[UUID] = None,
    score_max: Optional[float] = None,
    score_min: Optional[float] = None,
    scored_at: Optional[date] = None,
    page: int = 1,
    size: int = 50,
) -> tuple[list[Row], int]:
    """
    Return paginated content scores for an org with optional filters.

    Returns (rows, total_count).
    """
    filters = ["s.org_id = :org_id", "sp.is_monitored = TRUE", "s.is_active = TRUE"]
    params: dict = {"org_id": str(org_id), "limit": size, "offset": (page - 1) * size}

    if platform_id:
        filters.append("sp.platform_id = :platform_id")
        params["platform_id"] = str(platform_id)
    if brand_id:
        filters.append("s.brand_id = :brand_id")
        params["brand_id"] = str(brand_id)
    if score_max is not None:
        filters.append("(cs.content_total IS NULL OR cs.content_total <= :score_max)")
        params["score_max"] = score_max
    if score_min is not None:
        filters.append("cs.content_total >= :score_min")
        params["score_min"] = score_min
    if scored_at:
        filters.append("cs.scored_at = :scored_at")
        params["scored_at"] = scored_at
    else:
        # Default: latest score per sku_platform
        filters.append("""
            cs.scored_at = (
                SELECT MAX(cs2.scored_at)
                FROM content_scores cs2
                WHERE cs2.sku_platform_id = cs.sku_platform_id
            )
        """)

    where_clause = " AND ".join(filters)

    count_stmt = text(f"""
        SELECT COUNT(*)
        FROM content_scores cs
        JOIN sku_platforms sp ON sp.id = cs.sku_platform_id
        JOIN skus s           ON s.id  = sp.sku_id
        WHERE {where_clause}
    """)

    data_stmt = text(f"""
        SELECT
            cs.id,
            cs.sku_platform_id,
            s.id           AS sku_id,
            s.name         AS sku_name,
            s.article,
            b.id           AS brand_id,
            b.name         AS brand_name,
            p.id           AS platform_id,
            p.name         AS platform_name,
            sp.url         AS platform_url,
            cs.scored_at,
            cs.content_total,
            cs.image_score,
            cs.description_score,
            cs.composition_score,
            cs.collected_image_url,
            cs.created_at
        FROM content_scores cs
        JOIN sku_platforms sp ON sp.id  = cs.sku_platform_id
        JOIN skus s           ON s.id   = sp.sku_id
        JOIN brands b         ON b.id   = s.brand_id
        JOIN platforms p      ON p.id   = sp.platform_id
        WHERE {where_clause}
        ORDER BY cs.content_total ASC NULLS LAST, cs.scored_at DESC
        LIMIT :limit OFFSET :offset
    """)

    count_result = await db.execute(count_stmt, params)
    total = count_result.scalar_one()

    data_result = await db.execute(data_stmt, params)
    rows = data_result.fetchall()

    return rows, total


async def fetch_drilldown(
    db: AsyncSession,
    org_id: UUID,
    sku_platform_id: UUID,
) -> Optional[Row]:
    """
    Return full drill-down data for a single (SKU, platform) pair:
    latest score + reference material + 30-day history.
    """
    stmt = text("""
        SELECT
            cs.id,
            cs.sku_platform_id,
            s.id                    AS sku_id,
            s.name                  AS sku_name,
            s.article,
            b.id                    AS brand_id,
            b.name                  AS brand_name,
            p.id                    AS platform_id,
            p.name                  AS platform_name,
            sp.url                  AS platform_url,
            cs.scored_at,
            cs.content_total,
            cs.image_score,
            cs.description_score,
            cs.composition_score,
            cs.collected_image_url,
            cs.collected_description,
            cs.collected_composition,
            cs.collected_title,
            cs.created_at,
            s.reference_image_url,
            s.reference_description,
            s.reference_composition
        FROM content_scores cs
        JOIN sku_platforms sp ON sp.id = cs.sku_platform_id
        JOIN skus s           ON s.id  = sp.sku_id
        JOIN brands b         ON b.id  = s.brand_id
        JOIN platforms p      ON p.id  = sp.platform_id
        WHERE cs.sku_platform_id = :sku_platform_id
          AND s.org_id           = :org_id
        ORDER BY cs.scored_at DESC
        LIMIT 1
    """)

    result = await db.execute(stmt, {"sku_platform_id": str(sku_platform_id), "org_id": str(org_id)})
    return result.fetchone()


async def fetch_history(
    db: AsyncSession,
    org_id: UUID,
    sku_platform_id: UUID,
    days: int = 30,
) -> list[Row]:
    """Return content_total trend for the last N days."""
    stmt = text("""
        SELECT cs.scored_at, cs.content_total
        FROM content_scores cs
        JOIN sku_platforms sp ON sp.id = cs.sku_platform_id
        JOIN skus s           ON s.id  = sp.sku_id
        WHERE cs.sku_platform_id = :sku_platform_id
          AND s.org_id           = :org_id
          AND cs.scored_at      >= CURRENT_DATE - INTERVAL '1 day' * :days
        ORDER BY cs.scored_at ASC
    """)

    result = await db.execute(
        stmt,
        {"sku_platform_id": str(sku_platform_id), "org_id": str(org_id), "days": days},
    )
    return result.fetchall()
