"""
Celery task: collect current price for an Ozon SKU.

Inserts a new price_snapshots row on every run (append-only time series).
Runs every 4 hours via Celery Beat.

(sp_id, external_id, org_id) extracted as primitives within the first DB
session to avoid DetachedInstanceError from lazy relationships after session close.

Error handling:
  - NO_ITEM_ID:                  external_id empty → silent skip
  - PARSE_ERROR:                 item_id not numeric → log warning, return
  - NOT_FOUND:                   product missing → log info, return
  - RATE_LIMITED / API_UNAVAILABLE → self.retry() (max 3, exponential backoff)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from app.celery_app import celery_app
from app.core.base_scraper import DataType, ScraperError
from app.core.scraper_router import ScraperRouter
from app.models import PriceSnapshot, SKUPlatform, SKU
from app.tasks._db import get_db_session
from app.tasks._redis import get_redis_client
from app.tasks._retry_policy import should_retry_scrape_error

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=3,
    name="ozon.collect_price",
)
def collect_ozon_price(self, sku_platform_id: str) -> None:
    """
    Collect current price snapshot for one Ozon SKUPlatform.

    Args:
        sku_platform_id: UUID string of the sku_platforms row.
    """
    with get_db_session() as db:
        row = (
            db.query(
                SKUPlatform.id,
                SKUPlatform.external_id,
                SKUPlatform.url,
                SKUPlatform.platform_id,
                SKU.org_id,
            )
            .join(SKU, SKU.id == SKUPlatform.sku_id)
            .filter(SKUPlatform.id == uuid.UUID(sku_platform_id))
            .first()
        )

    if row is None:
        logger.warning(
            "collect_ozon_price: sku_platform %s not found — skipping", sku_platform_id
        )
        return

    sp_id, item_id, page_url, platform_id, org_id = row

    if not item_id:
        logger.info("collect_ozon_price: NO_ITEM_ID for sku_platform %s — skipping", sku_platform_id)
        return

    with get_db_session() as db:
        router = ScraperRouter(db, redis_client=get_redis_client())
        try:
            price_data = router.collect(
                platform_id=platform_id,
                sku_id=item_id,
                data_type=DataType.PRICE,
                org_id=org_id,
                page_url=page_url,
            )
        except ScraperError as exc:
            if exc.code == "NOT_FOUND":
                logger.info("collect_ozon_price: product item_id=%s not found on Ozon — skipping", item_id)
                return
            logger.warning("collect_ozon_price: ScraperError code=%s item_id=%s", exc.code, item_id)
            if not should_retry_scrape_error(exc):
                raise
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)

        scraper_level: int | None = getattr(price_data, "scraper_level", None)
        db.add(
            PriceSnapshot(
                id=uuid.uuid4(),
                sku_platform_id=sp_id,
                price=price_data.price,
                original_price=price_data.original_price,
                discount_pct=price_data.discount_pct,
                promo_label=price_data.promo_label,
                scraper_level=scraper_level,
                collected_at=datetime.now(tz=timezone.utc),
            )
        )

    logger.info(
        "collect_ozon_price: done item_id=%s price=%s discount_pct=%s scraper_level=%s",
        item_id,
        price_data.price,
        price_data.discount_pct,
        scraper_level,
    )
