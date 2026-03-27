"""
WB orchestrator tasks — dispatch per-SKU tasks for all WB platforms.

Two orchestrators:
  collect_wb_content_all  — daily at 02:00 UTC
    Dispatches: collect_wb_content + collect_wb_stock + collect_wb_reviews
    for every active, monitored sku_platform WHERE platform.name = "Wildberries"

  collect_wb_prices_all   — every 4 hours
    Dispatches: collect_wb_price
    for every active, monitored sku_platform WHERE platform.name = "Wildberries"

The orchestrator selects only sku_platform IDs (not full ORM objects) to keep
memory flat regardless of catalog size. Full ORM objects fetched per task.
"""

from __future__ import annotations

import logging

from app.celery_app import celery_app
from app.models import Platform, SKUPlatform
from app.tasks._db import get_db_session
from app.tasks.wb_content_task import collect_wb_content
from app.tasks.wb_price_task import collect_wb_price
from app.tasks.wb_reviews_task import collect_wb_reviews
from app.tasks.wb_stock_task import collect_wb_stock

logger = logging.getLogger(__name__)

_WB_PLATFORM_NAME = "Wildberries"


def _load_wb_sku_platform_ids(db) -> list[str]:
    """
    Return UUID strings of all active, monitored WB sku_platforms.
    Selects only the ID column to keep memory flat.
    """
    rows = (
        db.query(SKUPlatform.id)
        .join(Platform, Platform.id == SKUPlatform.platform_id)
        .filter(
            Platform.name == _WB_PLATFORM_NAME,
            Platform.is_active.is_(True),
            SKUPlatform.is_monitored.is_(True),
        )
        .all()
    )
    return [str(row.id) for row in rows]


@celery_app.task(name="wb.collect_content_all")
def collect_wb_content_all() -> None:
    """
    Daily orchestrator: dispatch content + stock + review tasks for all WB platforms.
    Runs at 02:00 UTC via Celery Beat.
    """
    with get_db_session() as db:
        sp_ids = _load_wb_sku_platform_ids(db)

    logger.info("collect_wb_content_all: dispatching %d WB sku_platforms", len(sp_ids))

    for sp_id in sp_ids:
        collect_wb_content.delay(sp_id)
        collect_wb_stock.delay(sp_id)
        collect_wb_reviews.delay(sp_id)

    logger.info("collect_wb_content_all: dispatched 3×%d tasks", len(sp_ids))


@celery_app.task(name="wb.collect_prices_all")
def collect_wb_prices_all() -> None:
    """
    Every-4h orchestrator: dispatch price tasks for all WB platforms.
    Runs at 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC via Celery Beat.
    """
    with get_db_session() as db:
        sp_ids = _load_wb_sku_platform_ids(db)

    logger.info("collect_wb_prices_all: dispatching %d WB sku_platforms", len(sp_ids))

    for sp_id in sp_ids:
        collect_wb_price.delay(sp_id)

    logger.info("collect_wb_prices_all: dispatched %d price tasks", len(sp_ids))
