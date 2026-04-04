"""
Database query layer for the reviews domain.

All queries enforce tenant isolation via the JOIN chain:
  reviews.sku_platform_id
    → sku_platforms.sku_id
    → skus.id  (filtered by org_id AND sku_id at router level)

The SKU ownership check (org_id == current_user.org_id) is performed ONCE
in the router via SKURepository.get_by_id_and_org() before any call here.
Repository functions still embed org_id in JOINs as defence-in-depth.

SQL notes:
  - COUNT(*) FILTER (WHERE ...) requires PostgreSQL 9.4+ (aggregation extension)
  - json_agg(row_to_json(...)) requires PostgreSQL 9.3+
  - f-string SQL: only literal clauses are interpolated, never user strings.
    sentiment is validated as Literal enum by FastAPI before reaching this layer.
"""

from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def fetch_summary(
    db: AsyncSession,
    org_id: UUID,
    sku_id: UUID,
    date_from: date,
    date_to: date,
) -> list[Row]:
    """Per-platform sentiment breakdown, ordered by review_count DESC."""
    stmt = text("""
        SELECT
            sp.platform_id,
            p.name                                                               AS platform_name,
            COUNT(*)                                                             AS review_count,
            ROUND(AVG(r.rating)::numeric, 2)                                     AS avg_rating,
            COUNT(*) FILTER (WHERE r.sentiment = 'positive')                     AS positive_count,
            COUNT(*) FILTER (WHERE r.sentiment = 'neutral')                      AS neutral_count,
            COUNT(*) FILTER (WHERE r.sentiment = 'negative')                     AS negative_count,
            MAX(r.review_date)                                                   AS last_review_date
        FROM reviews r
        JOIN sku_platforms sp ON sp.id = r.sku_platform_id
        JOIN platforms p      ON p.id  = sp.platform_id
        JOIN skus s           ON s.id  = sp.sku_id
        WHERE s.org_id     = :org_id
          AND s.id         = :sku_id
          AND r.review_date BETWEEN :date_from AND :date_to
        GROUP BY sp.platform_id, p.name
        ORDER BY review_count DESC
    """)
    result = await db.execute(stmt, {
        "org_id": org_id,
        "sku_id": sku_id,
        "date_from": date_from,
        "date_to": date_to,
    })
    return result.all()


async def fetch_history(
    db: AsyncSession,
    org_id: UUID,
    sku_id: UUID,
    platform_id: UUID | None,
    sentiment: str | None,
    date_from: date,
    date_to: date,
    limit: int,
    offset: int,
) -> list[Row]:
    """
    Paginated reviews with optional platform and sentiment filters.

    NOTE: f-string is safe here — only literal SQL clauses are interpolated,
    never user-supplied strings. sentiment is validated as Literal enum in router.
    """
    sentiment_clause = "AND r.sentiment = :sentiment" if sentiment else ""
    platform_clause = "AND sp.platform_id = :platform_id" if platform_id else ""

    stmt = text(f"""
        SELECT
            r.id,
            sp.platform_id,
            p.name     AS platform_name,
            r.review_text,
            r.rating,
            r.sentiment,
            r.sentiment_score,
            r.review_date
        FROM reviews r
        JOIN sku_platforms sp ON sp.id = r.sku_platform_id
        JOIN platforms p      ON p.id  = sp.platform_id
        JOIN skus s           ON s.id  = sp.sku_id
        WHERE s.org_id     = :org_id
          AND s.id         = :sku_id
          AND r.review_date BETWEEN :date_from AND :date_to
          {sentiment_clause}
          {platform_clause}
        ORDER BY r.review_date DESC
        LIMIT :limit OFFSET :offset
    """)

    params: dict = {
        "org_id": org_id,
        "sku_id": sku_id,
        "date_from": date_from,
        "date_to": date_to,
        "limit": limit,
        "offset": offset,
    }
    if sentiment:
        params["sentiment"] = sentiment
    if platform_id:
        params["platform_id"] = platform_id

    result = await db.execute(stmt, params)
    return result.all()


async def fetch_stats(
    db: AsyncSession,
    org_id: UUID,
    sku_id: UUID,
    date_from: date,
    date_to: date,
) -> Row | None:
    """
    Aggregated stats + weekly trend in a single SQL round-trip.

    Uses:
    - COUNT(*) FILTER (WHERE ...) — per-rating and per-sentiment counts
    - CTE + date_trunc('week') — weekly trend aggregation
    - json_agg(row_to_json(...)) — embed weekly rows into result set
    """
    stmt = text("""
        WITH range_data AS (
            SELECT r.rating, r.sentiment, r.review_date
            FROM reviews r
            JOIN sku_platforms sp ON sp.id = r.sku_platform_id
            JOIN skus s           ON s.id  = sp.sku_id
            WHERE s.org_id     = :org_id
              AND s.id         = :sku_id
              AND r.review_date BETWEEN :date_from AND :date_to
        ),
        weekly AS (
            SELECT
                date_trunc('week', review_date::timestamp)::date  AS week_start,
                COUNT(*)                                           AS review_count,
                ROUND(AVG(rating)::numeric, 2)                    AS avg_rating,
                ROUND(
                    COUNT(*) FILTER (WHERE sentiment = 'positive')::numeric
                    / NULLIF(COUNT(*), 0),
                    4
                )                                                  AS positive_share
            FROM range_data
            GROUP BY 1
            ORDER BY 1
        )
        SELECT
            COUNT(*)                                                              AS review_count,
            ROUND(AVG(rating)::numeric, 2)                                        AS avg_rating,
            COUNT(*) FILTER (WHERE rating = 1)                                    AS r1,
            COUNT(*) FILTER (WHERE rating = 2)                                    AS r2,
            COUNT(*) FILTER (WHERE rating = 3)                                    AS r3,
            COUNT(*) FILTER (WHERE rating = 4)                                    AS r4,
            COUNT(*) FILTER (WHERE rating = 5)                                    AS r5,
            ROUND(
                COUNT(*) FILTER (WHERE sentiment = 'positive')::numeric
                / NULLIF(COUNT(*), 0), 4
            )                                                                      AS positive_share,
            ROUND(
                COUNT(*) FILTER (WHERE sentiment = 'neutral')::numeric
                / NULLIF(COUNT(*), 0), 4
            )                                                                      AS neutral_share,
            ROUND(
                COUNT(*) FILTER (WHERE sentiment = 'negative')::numeric
                / NULLIF(COUNT(*), 0), 4
            )                                                                      AS negative_share,
            (SELECT json_agg(row_to_json(w)) FROM weekly w)                        AS weekly_trend
        FROM range_data
    """)

    result = await db.execute(stmt, {
        "org_id": org_id,
        "sku_id": sku_id,
        "date_from": date_from,
        "date_to": date_to,
    })
    row = result.one_or_none()
    if row is None or row.review_count == 0:
        return None
    return row
