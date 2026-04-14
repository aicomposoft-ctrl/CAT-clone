"""
Celery task: collect current price for a Samocat SKU.

Inserts a new price_snapshots row on every run (append-only time series).
Runs every 4 hours via Celery Beat.

(sp_id, external_id, org_id) extracted as primitives within the first DB
session to avoid DetachedInstanceError from lazy relationships after session
close.

Error handling:
  - NO_PRODUCT_ID:              external_id empty → silent skip
  - PARSE_ERROR:                product_id not numeric → log warning, return
  - NOT_FOUND:                  product missing → log info, return
  - RATE_LIMITED / API_UNAVAILABLE → self.retry() (max 3, exponential backoff)
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
from app.scrapers.samocat import SamokatScraper, _parse_product_id
from app.tasks._db import get_db_session

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=3,
    name="samocat.collect_price",
)
def collect_samocat_price(self, sku_platform_id: str) -> None:
    """
    Collect current price snapshot for one Samocat SKUPlatform.

    Args:
        sku_platform_id: UUID string of the sku_platforms row.
    """
    with get_db_session() as db:
        row = (
            db.query(SKUPlatform.id, SKUPlatform.external_id, SKU.org_id)
            .join(SKU, SKU.id == SKUPlatform.sku_id)
            .filter(SKUPlatform.id == uuid.UUID(sku_platform_id))
            .first()
        )

    if row is None:
        logger.warning(
            "collect_samocat_price: sku_platform %s not found — skipping", sku_platform_id
        )
        return

    sp_id, raw_product_id, org_id = row

    if not raw_product_id or not str(raw_product_id).strip():
        logger.info(
            "collect_samocat_price: NO_PRODUCT_ID for sku_platform %s — skipping",
            sku_platform_id,
        )
        return
    product_id = str(raw_product_id).strip()

    scraper = SamokatScraper(proxy_rotator=get_proxy_rotator())

    try:
        price_data = asyncio.run(scraper.collect_price(product_id))
    except ScraperError as exc:
        if exc.code == "NOT_FOUND":
            logger.info(
                "collect_samocat_price: product sku_platform=%s not found on Samocat — skipping",
                sku_platform_id,
            )
            return
        logger.warning(
            "collect_samocat_price: ScraperError code=%s sku_platform=%s",
            exc.code,
            sku_platform_id,
        )
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    with get_db_session() as db:
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

    logger.info("collect_samocat_price: done sku_platform=%s", sku_platform_id)
