"""
Dashboard summary endpoint.

GET /api/v1/dashboard/summary — aggregated KPIs for the authenticated org.

Returns:
  - avg_content_score: org-wide average content_total (last 24h)
  - active_alerts_count: unacknowledged (is_sent=False) alert events
  - distribution_coverage_pct: fact/plan ratio across all SKU-platforms
  - monitored_sku_count: count of active sku_platform rows
  - trends: delta vs 7 days ago for each KPI
  - red_zone: top-5 lowest-scoring SKU-platform pairs
  - recent_alerts: last 5 alert events
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.deps import get_current_user, get_db
from app.dashboard.schemas import DashboardSummary

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/summary", response_model=DashboardSummary, summary="Dashboard KPI summary")
async def get_dashboard_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardSummary:
    """Aggregate KPI data for the Dashboard Overview page."""
    org_id = current_user.org_id
    return await _build_summary(db, org_id)


async def _build_summary(db: AsyncSession, org_id: UUID) -> DashboardSummary:
    # 1. Average content score (latest score per sku_platform, last 7 days)
    avg_stmt = text("""
        SELECT
            ROUND(AVG(cs.content_total)::numeric, 1)  AS avg_score,
            COUNT(*)                                   AS scored_count
        FROM content_scores cs
        JOIN sku_platforms sp ON sp.id = cs.sku_platform_id
        JOIN skus s           ON s.id  = sp.sku_id
        WHERE s.org_id = :org_id
          AND s.is_active = TRUE
          AND sp.is_monitored = TRUE
          AND cs.scored_at = (
              SELECT MAX(cs2.scored_at)
              FROM content_scores cs2
              WHERE cs2.sku_platform_id = cs.sku_platform_id
          )
    """)
    avg_row = (await db.execute(avg_stmt, {"org_id": str(org_id)})).fetchone()
    avg_content_score = float(avg_row.avg_score) if avg_row and avg_row.avg_score else 0.0

    # 2. Active (unsent) alert events count
    alerts_stmt = text("""
        SELECT COUNT(*) AS cnt
        FROM alert_events ae
        WHERE ae.org_id = :org_id
          AND ae.is_sent = FALSE
    """)
    alerts_row = (await db.execute(alerts_stmt, {"org_id": str(org_id)})).fetchone()
    active_alerts_count = int(alerts_row.cnt) if alerts_row else 0

    # 3. Distribution coverage
    dist_stmt = text("""
        SELECT
            COALESCE(SUM(dp.plan_tt_count), 0)     AS total_plan,
            COALESCE(
                SUM(
                    (SELECT COALESCE(SUM(sh.stock_count), 0)
                     FROM stock_history sh
                     WHERE sh.sku_id     = dp.sku_id
                       AND sh.platform_id = dp.platform_id
                       AND sh.org_id     = :org_id
                       AND sh.week_number = dp.week_number
                       AND sh.year       = dp.year
                     LIMIT 1)
                ), 0
            )                                        AS total_fact
        FROM distribution_plans dp
        JOIN skus s ON s.id = dp.sku_id
        WHERE s.org_id = :org_id
          AND dp.year  = EXTRACT(YEAR FROM CURRENT_DATE)::int
          AND dp.week_number = EXTRACT(WEEK FROM CURRENT_DATE)::int
    """)
    dist_row = (await db.execute(dist_stmt, {"org_id": str(org_id)})).fetchone()
    if dist_row and dist_row.total_plan and dist_row.total_plan > 0:
        distribution_coverage_pct = round(
            float(dist_row.total_fact) / float(dist_row.total_plan) * 100, 1
        )
    else:
        distribution_coverage_pct = 0.0

    # 4. Monitored SKU count (active sku_platform pairs)
    monitored_stmt = text("""
        SELECT COUNT(*) AS cnt
        FROM sku_platforms sp
        JOIN skus s ON s.id = sp.sku_id
        WHERE s.org_id = :org_id
          AND s.is_active = TRUE
          AND sp.is_monitored = TRUE
    """)
    monitored_row = (await db.execute(monitored_stmt, {"org_id": str(org_id)})).fetchone()
    monitored_sku_count = int(monitored_row.cnt) if monitored_row else 0

    # 5. Red zone: top-5 lowest content_total
    red_zone_stmt = text("""
        SELECT
            cs.sku_platform_id,
            s.name         AS sku_name,
            s.article,
            p.name         AS platform_name,
            cs.content_total,
            cs.scored_at
        FROM content_scores cs
        JOIN sku_platforms sp ON sp.id = cs.sku_platform_id
        JOIN skus s           ON s.id  = sp.sku_id
        JOIN platforms p      ON p.id  = sp.platform_id
        WHERE s.org_id = :org_id
          AND s.is_active = TRUE
          AND cs.scored_at = (
              SELECT MAX(cs2.scored_at)
              FROM content_scores cs2
              WHERE cs2.sku_platform_id = cs.sku_platform_id
          )
        ORDER BY cs.content_total ASC NULLS LAST
        LIMIT 5
    """)
    red_zone_rows = (await db.execute(red_zone_stmt, {"org_id": str(org_id)})).fetchall()

    # 6. Recent alerts: last 5
    recent_alerts_stmt = text("""
        SELECT
            ae.id,
            ae.alert_type,
            ae.triggered_at,
            ae.value_before,
            ae.value_after,
            ae.is_sent,
            s.name  AS sku_name,
            p.name  AS platform_name
        FROM alert_events ae
        JOIN sku_platforms sp ON sp.id = ae.sku_platform_id
        JOIN skus s           ON s.id  = sp.sku_id
        JOIN platforms p      ON p.id  = sp.platform_id
        WHERE ae.org_id = :org_id
        ORDER BY ae.triggered_at DESC
        LIMIT 5
    """)
    recent_alerts_rows = (
        await db.execute(recent_alerts_stmt, {"org_id": str(org_id)})
    ).fetchall()

    from app.dashboard.schemas import DashboardAlert, DashboardRedZoneItem

    red_zone = [
        DashboardRedZoneItem(
            sku_platform_id=row.sku_platform_id,
            sku_name=row.sku_name,
            article=row.article,
            platform_name=row.platform_name,
            content_total=float(row.content_total) if row.content_total else None,
            scored_at=row.scored_at,
        )
        for row in red_zone_rows
    ]

    recent_alerts = [
        DashboardAlert(
            id=row.id,
            alert_type=row.alert_type,
            sku_name=row.sku_name,
            platform_name=row.platform_name,
            value_before=float(row.value_before) if row.value_before else None,
            value_after=float(row.value_after) if row.value_after else None,
            triggered_at=row.triggered_at,
            is_sent=row.is_sent,
        )
        for row in recent_alerts_rows
    ]

    return DashboardSummary(
        avg_content_score=avg_content_score,
        active_alerts_count=active_alerts_count,
        distribution_coverage_pct=distribution_coverage_pct,
        monitored_sku_count=monitored_sku_count,
        red_zone=red_zone,
        recent_alerts=recent_alerts,
    )
