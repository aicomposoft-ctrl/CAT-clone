"""
Celery task: collect stock availability for a Lenta SKU.

Delegates to ScraperRouter for adaptive L1→L2→L3 fallback.
Upserts stock fields (in_stock, warehouse_qty) into content_scores for today
using INSERT ... ON CONFLICT DO UPDATE (partial-row contract).

Partial-row contract: if no content_scores row exists yet for today, this task
creates one with only stock fields populated.  Content fields remain NULL until
collect_lenta_content runs.  The ML scoring pipeline MUST filter:
  WHERE collected_description IS NOT NULL

Error handling:
  - NO_PRODUCT_ID:              external_id empty → silent skip, no DB write
  - NOT_FOUND:                  product missing → log info, return, no write
  - RATE_LIMITED / API_UNAVAILABLE / PARSE_ERROR → self.retry() (max 3)
  - ALL_LEVELS_FAILED → self.retry() (max 3)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

import redis as redis_lib

from app.celery_app import REDIS_URL, celery_app
from app.core.base_scraper import DataType, StockData, ScraperError
from app.core.scraper_router import ScraperRouter
from app.models import ContentScore, SKUPlatform, SKU
from app.tasks._db import get_db_session

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=3,
    name="lenta.collect_stock",
)
def collect_lenta_stock(self, sku_platform_id: str) -> None:
    """
    Collect stock availability for one Lenta SKUPlatform.

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
            "collect_lenta_stock: sku_platform %s not found — skipping", sku_platform_id
        )
        return

    sp_id, raw_product_id, platform_id, org_id = row

    if not raw_product_id or not str(raw_product_id).strip():
        logger.info(
            "collect_lenta_stock: NO_PRODUCT_ID for sku_platform %s — skipping",
            sku_platform_id,
        )
        return
    product_id = str(raw_product_id).strip()

    with get_db_session() as db:
        _redis = redis_lib.from_url(REDIS_URL, decode_responses=False)
        router = ScraperRouter(db, redis_client=_redis)
        try:
            stock_data: StockData = router.collect(
                platform_id=platform_id,
                sku_id=product_id,
                data_type=DataType.STOCK,
                org_id=org_id,
            )
        except ScraperError as exc:
            if exc.code == "NOT_FOUND":
                logger.info(
                    "collect_lenta_stock: product sku_platform=%s not found — skipping",
                    sku_platform_id,
                )
                return
            logger.warning(
                "collect_lenta_stock: ScraperError code=%s sku_platform=%s",
                exc.code,
                sku_platform_id,
            )
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)

        now_utc = datetime.now(tz=timezone.utc)
        today = now_utc.date()
        # Partial-row upsert: set_ includes ONLY stock fields — partial-row contract.
        stmt = (
            pg_insert(ContentScore)
            .values(
                id=uuid.uuid4(),
                sku_platform_id=sp_id,
                scored_at=today,
                in_stock=stock_data.in_stock,
                warehouse_qty=stock_data.total_qty,
                created_at=now_utc,
            )
            .on_conflict_do_update(
                constraint="uq_content_scores_sp_date",
                set_={
                    "in_stock": stock_data.in_stock,
                    "warehouse_qty": stock_data.total_qty,
                },
            )
        )
        db.execute(stmt)

    logger.info("collect_lenta_stock: done sku_platform=%s", sku_platform_id)
