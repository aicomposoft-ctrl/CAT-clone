"""
Lenta orchestrator tasks — dispatch per-SKU tasks for all Lenta platforms.

Two orchestrators:
  collect_lenta_content_all  — daily at 05:00 UTC
    Dispatches: collect_lenta_content + collect_lenta_stock + collect_lenta_reviews
    for every active, monitored sku_platform WHERE platform.name = "Lenta"
    Tasks for each sku_platform_id are dispatched as a Celery group so they
    run concurrently in the worker pool.

  collect_lenta_prices_all   — every 4 hours
    Dispatches: collect_lenta_price
    for every active, monitored sku_platform WHERE platform.name = "Lenta"

The orchestrator selects only sku_platform IDs (not full ORM objects) to keep
memory flat regardless of catalog size.  Full ORM objects are fetched inside
each individual task, which also re-enforces org_id scoping.

Cross-org query rationale (same pattern as samocat_orchestrator.py):
  The orchestrator returns IDs from all orgs — this is safe because:
  1. Each task re-queries (sp_id, sku_id, external_id, org_id) and uses
     org_id for S3 namespacing and content_scores writes.
  2. content_scores upsert is keyed on sku_platform_id, which is already
     bound to exactly one org_id via FK — cross-tenant collision impossible.
  3. PostgreSQL RLS policies provide a final backstop.
  4. The orchestrator does NOT write to the DB — read-only ID dispatch.
"""

from __future__ import annotations

import logging

from celery import group

from app.celery_app import celery_app
from app.models import Platform, SKU, SKUPlatform
from app.tasks._db import get_db_session
from app.tasks.lenta_content_task import collect_lenta_content
from app.tasks.lenta_price_task import collect_lenta_price
from app.tasks.lenta_reviews_task import collect_lenta_reviews
from app.tasks.lenta_stock_task import collect_lenta_stock

logger = logging.getLogger(__name__)

# seed.py uses Cyrillic "Лента"; migrations use Latin "Lenta" — match both.
_LT_PLATFORM_NAMES = ("Lenta", "Лента")


def _load_lenta_sku_platform_ids(db) -> list[str]:
    """
    Return UUID strings of all active, monitored Lenta sku_platforms.
    Selects only the ID column to keep memory flat at any catalog size.
    """
    rows = (
        db.query(SKUPlatform.id)
        .join(Platform, Platform.id == SKUPlatform.platform_id)
        .join(SKU, SKU.id == SKUPlatform.sku_id)
        .filter(
            Platform.name.in_(_LT_PLATFORM_NAMES),
            Platform.is_active.is_(True),
            SKUPlatform.is_monitored.is_(True),
        )
        .all()
    )
    return [str(row.id) for row in rows]


@celery_app.task(name="lenta.collect_content_all")
def collect_lenta_content_all() -> None:
    """
    Daily orchestrator: dispatch content + stock + review tasks for all Lenta platforms.
    Runs at 05:00 UTC via Celery Beat (offset 1h after Samocat at 04:00).

    For each sku_platform_id, all three tasks are dispatched as a group so they
    execute concurrently in the worker pool rather than sequentially.
    """
    with get_db_session() as db:
        sp_ids = _load_lenta_sku_platform_ids(db)

    logger.info(
        "collect_lenta_content_all: dispatching %d Lenta sku_platforms", len(sp_ids)
    )

    if sp_ids:
        group(
            task
            for sp_id in sp_ids
            for task in (
                collect_lenta_content.s(sp_id),
                collect_lenta_stock.s(sp_id),
                collect_lenta_reviews.s(sp_id),
            )
        ).delay()

    logger.info("collect_lenta_content_all: dispatched 3×%d tasks", len(sp_ids))


@celery_app.task(name="lenta.collect_prices_all")
def collect_lenta_prices_all() -> None:
    """
    Every-4h orchestrator: dispatch price tasks for all Lenta platforms.
    Runs at 03:00, 07:00, 11:00, 15:00, 19:00, 23:00 UTC via Celery Beat
    (offset from Samocat/Ozon price tasks to avoid coincident DB write spikes).
    """
    with get_db_session() as db:
        sp_ids = _load_lenta_sku_platform_ids(db)

    logger.info(
        "collect_lenta_prices_all: dispatching %d Lenta sku_platforms", len(sp_ids)
    )

    if sp_ids:
        group(collect_lenta_price.s(sp_id) for sp_id in sp_ids).delay()

    logger.info("collect_lenta_prices_all: dispatched %d price tasks", len(sp_ids))
