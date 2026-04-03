"""
Database query layer for the prices domain.

All queries enforce tenant isolation via the JOIN chain:
  price_snapshots.sku_platform_id
    → sku_platforms.sku_id
    → skus.id  (filtered by org_id AND sku_id at router level)

The SKU ownership check (org_id == current_user.org_id) is performed ONCE
in the router via SKURepository.get_by_id_and_org() before any call here.
Repository functions receive sku_id directly and still embed org_id in JOINs
as a defence-in-depth guard.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _date_to_utc_range(
    date_from: date, date_to: date
) -> tuple[datetime, datetime]:
    """Convert inclusive date range to exclusive UTC datetimes for TIMESTAMPTZ comparison."""
    start = datetime.combine(date_from, time.min).replace(tzinfo=timezone.utc)
    end = datetime.combine(date_to + timedelta(days=1), time.min).replace(tzinfo=timezone.utc)
    return start, end


async def fetch_history(
    db: AsyncSession,
    org_id: UUID,
    sku_id: UUID,
    platform_id: UUID | None,
    date_from: date,
    date_to: date,
    limit: int,
) -> list[Row]:
    """Time-series of price snapshots, ordered by collected_at ASC."""
    start, end = _date_to_utc_range(date_from, date_to)

    platform_clause = "AND sp.platform_id = :platform_id" if platform_id else ""

    stmt = text(f"""
        SELECT
            ps.id,
            sp.platform_id,
            p.name         AS platform_name,
            ps.price,
            ps.original_price,
            ps.discount_pct,
            ps.promo_label,
            ps.collected_at
        FROM price_snapshots ps
        JOIN sku_platforms sp ON sp.id = ps.sku_platform_id
        JOIN platforms p      ON p.id  = sp.platform_id
        JOIN skus s           ON s.id  = sp.sku_id
        WHERE s.org_id = :org_id
          AND s.id     = :sku_id
          AND ps.collected_at >= :start
          AND ps.collected_at <  :end
          {platform_clause}
        ORDER BY ps.collected_at ASC
        LIMIT :limit
    """)

    params: dict = {
        "org_id": org_id,
        "sku_id": sku_id,
        "start": start,
        "end": end,
        "limit": limit,
    }
    if platform_id:
        params["platform_id"] = platform_id

    result = await db.execute(stmt, params)
    return result.all()


async def fetch_latest(
    db: AsyncSession,
    org_id: UUID,
    sku_id: UUID,
) -> list[Row]:
    """
    Most recent price snapshot per platform for a SKU.

    Uses PostgreSQL DISTINCT ON — not portable to SQLite.
    Tests must run against PostgreSQL (Docker fixture).
    """
    stmt = text("""
        SELECT DISTINCT ON (sp.platform_id)
            sp.platform_id,
            p.name         AS platform_name,
            ps.price,
            ps.original_price,
            ps.discount_pct,
            ps.promo_label,
            ps.collected_at
        FROM price_snapshots ps
        JOIN sku_platforms sp ON sp.id = ps.sku_platform_id
        JOIN platforms p      ON p.id  = sp.platform_id
        JOIN skus s           ON s.id  = sp.sku_id
        WHERE s.org_id = :org_id
          AND s.id     = :sku_id
        ORDER BY sp.platform_id, ps.collected_at DESC
    """)
    result = await db.execute(stmt, {"org_id": org_id, "sku_id": sku_id})
    return result.all()


async def fetch_stats(
    db: AsyncSession,
    org_id: UUID,
    sku_id: UUID,
    platform_id: UUID | None,
    date_from: date,
    date_to: date,
) -> Row | None:
    """
    Aggregated price statistics for a period via single SQL round-trip.

    Uses PERCENTILE_CONT (PostgreSQL 9.4+) for median.
    Uses CTE + ROW_NUMBER() to identify first/last price in one pass.
    """
    start, end = _date_to_utc_range(date_from, date_to)
    platform_clause = "AND sp.platform_id = :platform_id" if platform_id else ""

    stmt = text(f"""
        WITH ordered AS (
            SELECT
                ps.price,
                ps.discount_pct,
                ROW_NUMBER() OVER (ORDER BY ps.collected_at ASC)  AS rn_asc,
                ROW_NUMBER() OVER (ORDER BY ps.collected_at DESC) AS rn_desc
            FROM price_snapshots ps
            JOIN sku_platforms sp ON sp.id = ps.sku_platform_id
            JOIN skus s           ON s.id  = sp.sku_id
            WHERE s.org_id = :org_id
              AND s.id     = :sku_id
              AND ps.collected_at >= :start
              AND ps.collected_at <  :end
              {platform_clause}
        )
        SELECT
            COUNT(*)                                                  AS snapshot_count,
            MIN(price)                                                AS price_min,
            MAX(price)                                                AS price_max,
            ROUND(AVG(price)::numeric, 2)                             AS price_avg,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price)       AS price_median,
            MAX(CASE WHEN rn_asc  = 1 THEN price END)                 AS first_price,
            MAX(CASE WHEN rn_desc = 1 THEN price END)                 AS last_price,
            ROUND(AVG(discount_pct)::numeric, 2)                      AS discount_avg
        FROM ordered
    """)

    params: dict = {
        "org_id": org_id,
        "sku_id": sku_id,
        "start": start,
        "end": end,
    }
    if platform_id:
        params["platform_id"] = platform_id

    result = await db.execute(stmt, params)
    row = result.one_or_none()
    if row is None or row.snapshot_count == 0:
        return None
    return row


async def fetch_anomalies(
    db: AsyncSession,
    org_id: UUID,
    sku_id: UUID,
    platform_id: UUID | None,
    date_from: date,
    date_to: date,
    threshold: float,
    direction: str,
) -> list[Row]:
    """
    Price anomalies: consecutive snapshots where |change_pct| >= threshold.

    Uses LAG() window function — single query, no Python loops.
    direction: "up" | "down" | "both"

    NOTE: f-string is safe here — only literal SQL clauses are interpolated,
    never user-supplied strings. direction is validated to enum in router.
    """
    start, end = _date_to_utc_range(date_from, date_to)
    platform_clause = "AND sp.platform_id = :platform_id" if platform_id else ""

    direction_filter = {
        "down": "AND ps2.price_after < ps2.price_before",
        "up":   "AND ps2.price_after > ps2.price_before",
        "both": "",
    }[direction]

    stmt = text(f"""
        WITH price_series AS (
            SELECT
                ps.collected_at::date           AS date,
                sp.platform_id,
                p.name                          AS platform_name,
                ps.price,
                LAG(ps.price) OVER (
                    PARTITION BY ps.sku_platform_id
                    ORDER BY ps.collected_at
                )                               AS price_prev
            FROM price_snapshots ps
            JOIN sku_platforms sp ON sp.id = ps.sku_platform_id
            JOIN platforms p      ON p.id  = sp.platform_id
            JOIN skus s           ON s.id  = sp.sku_id
            WHERE s.org_id = :org_id
              AND s.id     = :sku_id
              AND ps.collected_at >= :start
              AND ps.collected_at <  :end
              {platform_clause}
        ),
        ps2 AS (
            SELECT
                date,
                platform_id,
                platform_name,
                price_prev                              AS price_before,
                price                                   AS price_after,
                (price - price_prev)                    AS change_abs,
                (price - price_prev) / price_prev * 100 AS change_pct
            FROM price_series
            WHERE price_prev IS NOT NULL
              AND price_prev != 0
        )
        SELECT
            date,
            platform_id,
            platform_name,
            price_before,
            price_after,
            change_abs,
            change_pct
        FROM ps2
        WHERE ABS(change_pct) >= :threshold
          {direction_filter}
        ORDER BY date ASC, ABS(change_pct) DESC
    """)

    params: dict = {
        "org_id": org_id,
        "sku_id": sku_id,
        "start": start,
        "end": end,
        "threshold": threshold,
    }
    if platform_id:
        params["platform_id"] = platform_id

    result = await db.execute(stmt, params)
    return result.all()
