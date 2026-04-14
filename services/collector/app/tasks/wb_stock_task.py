"""
Celery task: collect stock availability for a Wildberries SKU.

Upserts stock fields (in_stock, warehouse_qty, scraper_level) into
content_scores for today.

Partial-row contract: if no content_scores row exists yet for today, this task
creates one with only stock fields set. Content fields remain NULL.
ML scoring pipeline MUST filter WHERE collected_description IS NOT NULL.

Delegates scraping to ScraperRouter for adaptive fallback (L0 → L1 → L2).
Task signature is unchanged for backward compatibility (R-04).

org_id extracted as a primitive within the first DB session to avoid
DetachedInstanceError from lazy relationships after session close.

Error handling:
  - NO_NM_ID:    external_id is None → silent skip
  - NOT_FOUND:   product missing → log and return, no write
  - API_UNAVAILABLE / ALL_LEVELS_FAILED → self.retry() (max 3, exponential backoff), no write on failure
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone

import redis as redis_lib

from app.celery_app import REDIS_URL, celery_app
from app.core.base_scraper import DataType, ScraperError
from app.core.scraper_router import ScraperRouter
from app.models import ContentScore, SKUPlatform, SKU
from app.tasks._db import get_db_session

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=3,
    name="wb.collect_stock",
)
def collect_wb_stock(self, sku_platform_id: str) -> None:
    """
    Collect stock availability for one WB SKUPlatform.

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
        logger.warning("collect_wb_stock: sku_platform %s not found — skipping", sku_platform_id)
        return

    sp_id, nm_id, platform_id, org_id = row

    if not nm_id:
        logger.info("collect_wb_stock: NO_NM_ID for sku_platform %s — skipping", sku_platform_id)
        return

    with get_db_session() as db:
        _redis = redis_lib.from_url(REDIS_URL, decode_responses=False)
        router = ScraperRouter(db, redis_client=_redis)
        try:
            stock_data = router.collect(
                platform_id=platform_id,
                sku_id=nm_id,
                data_type=DataType.STOCK,
                org_id=org_id,
            )
        except ScraperError as exc:
            if exc.code == "NOT_FOUND":
                logger.info("collect_wb_stock: product nm_id=%s not found on WB — skipping", nm_id)
                return
            logger.warning("collect_wb_stock: ScraperError code=%s nm_id=%s", exc.code, nm_id)
            # No DB write on failure — retry instead
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)

        scraper_level: int | None = getattr(stock_data, "scraper_level", None)
        today = date.today()
        existing = (
            db.query(ContentScore)
            .filter(
                ContentScore.sku_platform_id == sp_id,
                ContentScore.scored_at == today,
            )
            .first()
        )

        if existing:
            existing.in_stock = stock_data.in_stock
            existing.warehouse_qty = stock_data.total_qty
            existing.scraper_level = scraper_level
        else:
            # Partial row: content fields stay NULL until collect_wb_content runs.
            # ML pipeline must guard: WHERE collected_description IS NOT NULL
            db.add(
                ContentScore(
                    id=uuid.uuid4(),
                    sku_platform_id=sp_id,
                    scored_at=today,
                    in_stock=stock_data.in_stock,
                    warehouse_qty=stock_data.total_qty,
                    scraper_level=scraper_level,
                    created_at=datetime.now(tz=timezone.utc),
                )
            )

    logger.info(
        "collect_wb_stock: done nm_id=%s in_stock=%s qty=%s scraper_level=%s",
        nm_id,
        stock_data.in_stock,
        stock_data.total_qty,
        scraper_level,
    )
