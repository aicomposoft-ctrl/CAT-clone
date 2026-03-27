"""
Celery task: collect current price for a Wildberries SKU.

Inserts a new price_snapshots row on every run (append-only time series).
Runs every 4 hours via Celery Beat.

Error handling:
  - NO_NM_ID:    external_id is None → silent skip
  - NOT_FOUND:   product missing → log and return
  - RATE_LIMITED / API_UNAVAILABLE → retry (max 3, exponential backoff)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from app.celery_app import celery_app
from app.core.base_scraper import ScraperError
from app.core.proxy import get_proxy_rotator
from app.models import PriceSnapshot, SKUPlatform, SKU
from app.scrapers.wildberries import WildberriesScraper
from app.tasks._db import get_db_session

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=3,
    name="wb.collect_price",
)
def collect_wb_price(self, sku_platform_id: str) -> None:
    """
    Collect current price snapshot for one WB SKUPlatform.

    Args:
        sku_platform_id: UUID string of the sku_platforms row.
    """
    with get_db_session() as db:
        sp = (
            db.query(SKUPlatform)
            .join(SKU, SKU.id == SKUPlatform.sku_id)
            .filter(SKUPlatform.id == uuid.UUID(sku_platform_id))
            .first()
        )

    if sp is None:
        logger.warning("collect_wb_price: sku_platform %s not found — skipping", sku_platform_id)
        return

    nm_id = sp.external_id
    if not nm_id:
        logger.info("collect_wb_price: NO_NM_ID for sku_platform %s — skipping", sku_platform_id)
        return

    scraper = WildberriesScraper(proxy_rotator=get_proxy_rotator())

    try:
        price_data = asyncio.run(scraper.collect_price(nm_id))
    except ScraperError as exc:
        if exc.code == "NOT_FOUND":
            logger.info("collect_wb_price: product nm_id=%s not found on WB — skipping", nm_id)
            return
        logger.warning("collect_wb_price: ScraperError code=%s nm_id=%s", exc.code, nm_id)
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    with get_db_session() as db:
        db.add(
            PriceSnapshot(
                id=uuid.uuid4(),
                sku_platform_id=sp.id,
                price=price_data.price,
                original_price=price_data.original_price,
                discount_pct=price_data.discount_pct,
                promo_label=price_data.promo_label,
                collected_at=datetime.now(tz=timezone.utc),
            )
        )

    logger.info(
        "collect_wb_price: done nm_id=%s price=%s discount_pct=%s",
        nm_id,
        price_data.price,
        price_data.discount_pct,
    )
