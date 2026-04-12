"""
Celery task: collect current price for a Wildberries SKU.

Inserts a new price_snapshots row on every run (append-only time series),
including the scraper_level provenance field added in migration 0014.
Runs every 4 hours via Celery Beat.

Delegates scraping to ScraperRouter for adaptive fallback (L0 → L1 → L2).
Task signature is unchanged for backward compatibility (R-04).

org_id extracted as a primitive within the first DB session to avoid
DetachedInstanceError from lazy relationships after session close.

Error handling:
  - NO_NM_ID:    external_id is None → silent skip
  - NOT_FOUND:   product missing → log and return
  - RATE_LIMITED / API_UNAVAILABLE / ALL_LEVELS_FAILED → self.retry() (max 3, exponential backoff)
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

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=3,
    name="wb.collect_price",
)
def collect_wb_price(self, sku_platform_id: str) -> None:
    """
    Collect current price snapshot for one WB SKUPlatform.

    Delegates to ScraperRouter for adaptive fallback (L0 → L1 → L2).
    Task signature is unchanged for backward compatibility (R-04).

    Args:
        sku_platform_id: UUID string of the sku_platforms row.
    """
    with get_db_session() as db:
        row = (
            db.query(
                SKUPlatform.id,
                SKUPlatform.external_id,
                SKUPlatform.platform_id,
                SKU.org_id,
            )
            .join(SKU, SKU.id == SKUPlatform.sku_id)
            .filter(SKUPlatform.id == uuid.UUID(sku_platform_id))
            .first()
        )

    if row is None:
        logger.warning("collect_wb_price: sku_platform %s not found — skipping", sku_platform_id)
        return

    sp_id, nm_id, platform_id, org_id = row

    if not nm_id:
        logger.info("collect_wb_price: NO_NM_ID for sku_platform %s — skipping", sku_platform_id)
        return

    with get_db_session() as db:
        router = ScraperRouter(db)
        try:
            price_data = router.collect(
                platform_id=platform_id,
                sku_id=nm_id,
                data_type=DataType.PRICE,
                org_id=org_id,
            )
        except ScraperError as exc:
            if exc.code == "NOT_FOUND":
                logger.info("collect_wb_price: product nm_id=%s not found on WB — skipping", nm_id)
                return
            logger.warning("collect_wb_price: ScraperError code=%s nm_id=%s", exc.code, nm_id)
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
        "collect_wb_price: done nm_id=%s price=%s discount_pct=%s scraper_level=%s",
        nm_id,
        price_data.price,
        price_data.discount_pct,
        scraper_level,
    )
