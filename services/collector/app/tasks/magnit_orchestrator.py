"""
Magnit orchestrator tasks — dispatch per-SKU tasks for all Magnit platforms.

collect_magnit_content_all  — daily at 07:00 UTC
  Dispatches: content + stock + reviews for every active monitored sku_platform
  WHERE platform.name IN ('Магнит', 'Magnit')

collect_magnit_prices_all   — every 4 hours
  Dispatches: price task for every active monitored sku_platform
"""

from __future__ import annotations

import logging

from celery import group

from app.celery_app import celery_app
from app.models import Platform, SKU, SKUPlatform
from app.tasks._db import get_db_session
from app.tasks.magnit_content_task import collect_magnit_content
from app.tasks.magnit_price_task import collect_magnit_price
from app.tasks.magnit_reviews_task import collect_magnit_reviews
from app.tasks.magnit_stock_task import collect_magnit_stock

logger = logging.getLogger(__name__)

_MG_PLATFORM_NAMES = ("Магнит", "Magnit")


def _load_ids(db) -> list[str]:
    rows = (
        db.query(SKUPlatform.id)
        .join(Platform, Platform.id == SKUPlatform.platform_id)
        .join(SKU, SKU.id == SKUPlatform.sku_id)
        .filter(
            Platform.name.in_(_MG_PLATFORM_NAMES),
            Platform.is_active.is_(True),
            SKUPlatform.is_monitored.is_(True),
        )
        .all()
    )
    return [str(row.id) for row in rows]


@celery_app.task(name="magnit.collect_content_all")
def collect_magnit_content_all() -> None:
    """Daily orchestrator: dispatch content + stock + review tasks for all Magnit platforms."""
    with get_db_session() as db:
        sp_ids = _load_ids(db)

    logger.info("collect_magnit_content_all: dispatching %d platforms", len(sp_ids))

    if sp_ids:
        group(
            task
            for sp_id in sp_ids
            for task in (
                collect_magnit_content.s(sp_id),
                collect_magnit_stock.s(sp_id),
                collect_magnit_reviews.s(sp_id),
            )
        ).delay()

    logger.info("collect_magnit_content_all: dispatched 3×%d tasks", len(sp_ids))


@celery_app.task(name="magnit.collect_prices_all")
def collect_magnit_prices_all() -> None:
    """Every-4h orchestrator: dispatch price tasks for all Magnit platforms."""
    with get_db_session() as db:
        sp_ids = _load_ids(db)

    logger.info("collect_magnit_prices_all: dispatching %d platforms", len(sp_ids))

    if sp_ids:
        group(collect_magnit_price.s(sp_id) for sp_id in sp_ids).delay()

    logger.info("collect_magnit_prices_all: dispatched %d price tasks", len(sp_ids))
