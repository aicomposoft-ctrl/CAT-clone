"""
Ozon orchestrator tasks — dispatch per-SKU tasks for all Ozon platforms.

Two orchestrators:
  collect_ozon_content_all  — daily at 03:00 UTC
    Dispatches: collect_ozon_content + collect_ozon_stock + collect_ozon_reviews
    for every active, monitored sku_platform WHERE platform.name = "Ozon"

  collect_ozon_prices_all   — every 4 hours
    Dispatches: collect_ozon_price
    for every active, monitored sku_platform WHERE platform.name = "Ozon"

The orchestrator selects only sku_platform IDs (not full ORM objects) to keep
memory flat regardless of catalog size.  Full ORM objects are fetched inside
each individual task, which also re-enforces org_id scoping.

Cross-org query rationale (same pattern as wb_orchestrator.py):
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

from app.celery_app import celery_app
from app.models import Platform, SKU, SKUPlatform
from app.tasks._db import get_db_session
from app.tasks.ozon_content_task import collect_ozon_content
from app.tasks.ozon_price_task import collect_ozon_price
from app.tasks.ozon_reviews_task import collect_ozon_reviews
from app.tasks.ozon_stock_task import collect_ozon_stock

logger = logging.getLogger(__name__)

_OZ_PLATFORM_NAME = "Ozon"


def _load_ozon_sku_platform_ids(db) -> list[str]:
    """
    Return UUID strings of all active, monitored Ozon sku_platforms.
    Selects only the ID column to keep memory flat at any catalog size.
    """
    rows = (
        db.query(SKUPlatform.id)
        .join(Platform, Platform.id == SKUPlatform.platform_id)
        .join(SKU, SKU.id == SKUPlatform.sku_id)
        .filter(
            Platform.name == _OZ_PLATFORM_NAME,
            Platform.is_active.is_(True),
            SKUPlatform.is_monitored.is_(True),
        )
        .all()
    )
    return [str(row.id) for row in rows]


@celery_app.task(name="ozon.collect_content_all")
def collect_ozon_content_all() -> None:
    """
    Daily orchestrator: dispatch content + stock + review tasks for all Ozon platforms.
    Runs at 03:00 UTC via Celery Beat (offset from WB at 02:00 to spread load).
    """
    with get_db_session() as db:
        sp_ids = _load_ozon_sku_platform_ids(db)

    logger.info("collect_ozon_content_all: dispatching %d Ozon sku_platforms", len(sp_ids))

    for sp_id in sp_ids:
        collect_ozon_content.delay(sp_id)
        collect_ozon_stock.delay(sp_id)
        collect_ozon_reviews.delay(sp_id)

    logger.info("collect_ozon_content_all: dispatched 3×%d tasks", len(sp_ids))


@celery_app.task(name="ozon.collect_prices_all")
def collect_ozon_prices_all() -> None:
    """
    Every-4h orchestrator: dispatch price tasks for all Ozon platforms.
    Runs at 01:00, 05:00, 09:00, 13:00, 17:00, 21:00 UTC via Celery Beat
    (offset by 1h from WB price tasks to avoid coincident DB write spikes).
    """
    with get_db_session() as db:
        sp_ids = _load_ozon_sku_platform_ids(db)

    logger.info("collect_ozon_prices_all: dispatching %d Ozon sku_platforms", len(sp_ids))

    for sp_id in sp_ids:
        collect_ozon_price.delay(sp_id)

    logger.info("collect_ozon_prices_all: dispatched %d price tasks", len(sp_ids))
