"""
Celery task: collect current price for an Ozon SKU.

Delegates to ScraperRouter for adaptive L1→L2→L3 fallback.
Inserts a new price_snapshots row on every run (append-only time series).

Error handling:
  - NO_ITEM_ID:                  external_id empty → silent skip
  - NOT_FOUND:                   product missing → log info, return
  - RATE_LIMITED / API_UNAVAILABLE / PARSE_ERROR → self.retry() (max 3)
  - ALL_LEVELS_FAILED → self.retry() (max 3)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import redis as redis_lib

from app.celery_app import REDIS_URL, celery_app
from app.core.base_scraper import DataType, PriceData, ScraperError
from app.core.scraper_router import ScraperRouter
from app.models import PriceSnapshot, SKUPlatform, SKU
from app.tasks._db import get_db_session

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
            db.query(SKUPlatform.id, SKUPlatform.external_id, SKUPlatform.platform_id, SKU.org_id)
            .join(SKU, SKU.id == SKUPlatform.sku_id)
            .filter(SKUPlatform.id == uuid.UUID(sku_platform_id))
            .first()
        )

    if row is None:
        logger.warning(
            "collect_ozon_price: sku_platform %s not found — skipping", sku_platform_id
        )
        return

    sp_id, raw_item_id, platform_id, org_id = row

    if not raw_item_id or not str(raw_item_id).strip():
        logger.info(
            "collect_ozon_price: NO_ITEM_ID for sku_platform %s — skipping", sku_platform_id
        )
        return
    item_id = str(raw_item_id).strip()

    with get_db_session() as db:
        _redis = redis_lib.from_url(REDIS_URL, decode_responses=False)
        router = ScraperRouter(db, redis_client=_redis)
        try:
            price_data: PriceData = router.collect(
                platform_id=platform_id,
                sku_id=item_id,
                data_type=DataType.PRICE,
                org_id=org_id,
            )
        except ScraperError as exc:
            if exc.code == "NOT_FOUND":
                logger.info(
                    "collect_ozon_price: product sku_platform=%s not found — skipping",
                    sku_platform_id,
                )
                return
            logger.warning(
                "collect_ozon_price: ScraperError code=%s item_id=%s", exc.code, item_id
            )
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)

        db.add(
            PriceSnapshot(
                id=uuid.uuid4(),
                sku_platform_id=sp_id,
                price=price_data.price,
                original_price=price_data.original_price,
                discount_pct=price_data.discount_pct,
                promo_label=price_data.promo_label,
                collected_at=datetime.now(tz=timezone.utc),
            )
        )

    logger.info(
        "collect_ozon_price: done item_id=%s price=%s", item_id, price_data.price
    )
