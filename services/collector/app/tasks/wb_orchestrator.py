"""
WB orchestrator tasks — dispatch per-SKU tasks for all WB platforms.

Two orchestrators:
  collect_wb_content_all  — daily at 02:00 UTC
    Dispatches: collect_wb_content + collect_wb_stock + collect_wb_reviews
    for every active sku_platform WHERE platform.name = "Wildberries"

  collect_wb_prices_all   — every 4 hours
    Dispatches: collect_wb_price
    for every active sku_platform WHERE platform.name = "Wildberries"

These tasks are triggered by Celery Beat (configured in docker-compose / beat schedule).
Each per-SKU task is sent with .delay() and runs independently — orchestrator does not
wait for individual task completion.
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


def _load_wb_sku_platforms(db) -> list[SKUPlatform]:
    """Load all monitored WB sku_platforms via a single JOIN query."""
    return (
        db.query(SKUPlatform)
        .join(Platform, Platform.id == SKUPlatform.platform_id)
        .filter(
            Platform.name == _WB_PLATFORM_NAME,
            SKUPlatform.is_monitored.is_(True),
        )
        .all()
    )


@celery_app.task(name="wb.collect_content_all")
def collect_wb_content_all() -> None:
    """
    Daily orchestrator: dispatch content + stock + review tasks for all WB platforms.
    Runs at 02:00 UTC via Celery Beat.
    """
    with get_db_session() as db:
        sku_platforms = _load_wb_sku_platforms(db)
        sp_ids = [str(sp.id) for sp in sku_platforms]

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
        sku_platforms = _load_wb_sku_platforms(db)
        sp_ids = [str(sp.id) for sp in sku_platforms]

    logger.info("collect_wb_prices_all: dispatching %d WB sku_platforms", len(sp_ids))

    for sp_id in sp_ids:
        collect_wb_price.delay(sp_id)

    logger.info("collect_wb_prices_all: dispatched %d price tasks", len(sp_ids))
