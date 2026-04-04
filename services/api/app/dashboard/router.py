"""
Dashboard summary endpoint.

GET /api/v1/dashboard/summary — aggregated KPIs for the authenticated org.

Returns:
  - avg_content_score: org-wide average content_total (latest score per sku_platform)
  - active_alerts_count: unacknowledged (is_sent=False) alert events
  - distribution_coverage_pct: fact/plan ratio across all SKU-platforms (current week)
  - monitored_sku_count: count of active sku_platform rows
  - red_zone: top-5 lowest-scoring SKU-platform pairs
  - recent_alerts: last 5 alert events

Performance: all 6 DB queries are issued concurrently via asyncio.gather.
Correlated subqueries replaced with DISTINCT ON for O(n log n) index scans.
"""

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.deps import get_current_user, get_db
from app.dashboard.schemas import DashboardAlert, DashboardRedZoneItem, DashboardSummary

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/summary", response_model=DashboardSummary, summary="Dashboard KPI summary")
async def get_dashboard_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardSummary:
    """Aggregate KPI data for the Dashboard Overview page."""
    return await _build_summary(db, current_user.org_id)


async def _build_summary(db: AsyncSession, org_id: UUID) -> DashboardSummary:
    p = {"org_id": str(org_id)}

    # 1. Average content score — DISTINCT ON replaces correlated subquery
    avg_stmt = text("""
        SELECT ROUND(AVG(latest.content_total)::numeric, 1) AS avg_score
        FROM (
            SELECT DISTINCT ON (cs.sku_platform_id) cs.content_total
            FROM content_scores cs
            JOIN sku_platforms sp ON sp.id = cs.sku_platform_id
            JOIN skus s           ON s.id  = sp.sku_id
            WHERE s.org_id      = :org_id
              AND s.is_active   = TRUE
              AND sp.is_monitored = TRUE
            ORDER BY cs.sku_platform_id, cs.scored_at DESC
        ) latest
    """)

    # 2. Active (unsent) alert events count
    alerts_stmt = text("""
        SELECT COUNT(*) AS cnt
        FROM alert_events ae
        WHERE ae.org_id  = :org_id
          AND ae.is_sent = FALSE
    """)

    # 3. Distribution coverage — LEFT JOIN replaces correlated SUM() subquery
    dist_stmt = text("""
        SELECT
            COALESCE(SUM(dp.plan_tt_count), 0)   AS total_plan,
            COALESCE(SUM(sh.stock_count), 0)     AS total_fact
        FROM distribution_plans dp
        JOIN skus s ON s.id = dp.sku_id
        LEFT JOIN stock_history sh
               ON sh.sku_id       = dp.sku_id
              AND sh.platform_id  = dp.platform_id
              AND sh.org_id       = :org_id
              AND sh.week_number  = dp.week_number
              AND sh.year         = dp.year
        WHERE s.org_id      = :org_id
          AND dp.year        = EXTRACT(YEAR FROM CURRENT_DATE)::int
          AND dp.week_number = EXTRACT(WEEK FROM CURRENT_DATE)::int
    """)

    # 4. Monitored SKU count
    monitored_stmt = text("""
        SELECT COUNT(*) AS cnt
        FROM sku_platforms sp
        JOIN skus s ON s.id = sp.sku_id
        WHERE s.org_id      = :org_id
          AND s.is_active   = TRUE
          AND sp.is_monitored = TRUE
    """)

    # 5. Red zone: top-5 lowest content_total — DISTINCT ON replaces correlated subquery
    red_zone_stmt = text("""
        SELECT
            latest.sku_platform_id,
            latest.sku_name,
            latest.article,
            latest.platform_name,
            latest.content_total,
            latest.scored_at
        FROM (
            SELECT DISTINCT ON (cs.sku_platform_id)
                cs.sku_platform_id,
                s.name   AS sku_name,
                s.article,
                p.name   AS platform_name,
                cs.content_total,
                cs.scored_at
            FROM content_scores cs
            JOIN sku_platforms sp ON sp.id = cs.sku_platform_id
            JOIN skus s           ON s.id  = sp.sku_id
            JOIN platforms p      ON p.id  = sp.platform_id
            WHERE s.org_id      = :org_id
              AND s.is_active   = TRUE
            ORDER BY cs.sku_platform_id, cs.scored_at DESC
        ) latest
        ORDER BY latest.content_total ASC NULLS LAST
        LIMIT 5
    """)

    # 6. Recent alerts: last 5 — composite index (org_id, triggered_at DESC) used
    recent_alerts_stmt = text("""
        SELECT
            ae.id,
            ae.alert_type,
            ae.triggered_at,
            ae.value_before,
            ae.value_after,
            ae.is_sent,
            s.name  AS sku_name,
            pl.name AS platform_name
        FROM alert_events ae
        JOIN sku_platforms sp ON sp.id = ae.sku_platform_id
        JOIN skus s           ON s.id  = sp.sku_id
        JOIN platforms pl     ON pl.id = sp.platform_id
        WHERE ae.org_id = :org_id
        ORDER BY ae.triggered_at DESC
        LIMIT 5
    """)

    # Fire all 6 queries concurrently
    (
        avg_result,
        alerts_result,
        dist_result,
        monitored_result,
        red_zone_result,
        recent_alerts_result,
    ) = await asyncio.gather(
        db.execute(avg_stmt, p),
        db.execute(alerts_stmt, p),
        db.execute(dist_stmt, p),
        db.execute(monitored_stmt, p),
        db.execute(red_zone_stmt, p),
        db.execute(recent_alerts_stmt, p),
    )

    avg_row = avg_result.fetchone()
    avg_content_score = float(avg_row.avg_score) if avg_row and avg_row.avg_score else None

    alerts_row = alerts_result.fetchone()
    active_alerts_count = int(alerts_row.cnt) if alerts_row else 0

    dist_row = dist_result.fetchone()
    if dist_row and dist_row.total_plan and dist_row.total_plan > 0:
        raw_pct = float(dist_row.total_fact) / float(dist_row.total_plan) * 100
        distribution_coverage_pct = round(min(raw_pct, 100.0), 1)
    else:
        distribution_coverage_pct = None

    monitored_row = monitored_result.fetchone()
    monitored_sku_count = int(monitored_row.cnt) if monitored_row else 0

    red_zone = [
        DashboardRedZoneItem(
            sku_platform_id=row.sku_platform_id,
            sku_name=row.sku_name,
            article=row.article,
            platform_name=row.platform_name,
            content_total=float(row.content_total) if row.content_total is not None else None,
            scored_at=row.scored_at,
        )
        for row in red_zone_result.fetchall()
    ]

    recent_alerts = [
        DashboardAlert(
            id=row.id,
            alert_type=row.alert_type,
            sku_name=row.sku_name,
            platform_name=row.platform_name,
            value_before=float(row.value_before) if row.value_before is not None else None,
            value_after=float(row.value_after) if row.value_after is not None else None,
            triggered_at=row.triggered_at,
            is_sent=row.is_sent,
        )
        for row in recent_alerts_result.fetchall()
    ]

    return DashboardSummary(
        avg_content_score=avg_content_score,
        active_alerts_count=active_alerts_count,
        distribution_coverage_pct=distribution_coverage_pct,
        monitored_sku_count=monitored_sku_count,
        red_zone=red_zone,
        recent_alerts=recent_alerts,
    )
