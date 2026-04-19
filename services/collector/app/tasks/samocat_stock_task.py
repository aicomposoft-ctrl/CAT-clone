"""
Celery task: collect stock availability for a Samocat SKU.

Upserts stock fields (in_stock, warehouse_qty) into content_scores for today
using INSERT ... ON CONFLICT DO UPDATE (partial-row contract).

Partial-row contract: if no content_scores row exists yet for today, this task
creates one with only stock fields populated.  Content fields remain NULL until
collect_samocat_content runs.  The ML scoring pipeline MUST filter:
  WHERE collected_description IS NOT NULL

Only stock fields are included in the ON CONFLICT set_ clause — content fields
(collected_title, collected_description, etc.) are intentionally omitted so
they are never overwritten by a stock task running after a content task.

(sp_id, external_id, org_id) extracted as primitives within the first DB
session to avoid DetachedInstanceError after session close.

Error handling:
  - NO_PRODUCT_ID:              external_id empty → silent skip, no DB write
  - PARSE_ERROR:                product_id not numeric → log warning, return
  - NOT_FOUND:                  product missing → log info, return, no write
  - RATE_LIMITED / API_UNAVAILABLE → self.retry() (max 3, exponential backoff), no write
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.celery_app import celery_app
from app.core.base_scraper import DataType, ScraperError
from app.core.scraper_router import ScraperRouter
from app.models import ContentScore, SKUPlatform, SKU
from app.tasks._db import get_db_session
from app.tasks._redis import get_redis_client

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=3,
    name="samocat.collect_stock",
)
def collect_samocat_stock(self, sku_platform_id: str) -> None:
    """
    Collect stock availability for one Samocat SKUPlatform.

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
            "collect_samocat_stock: sku_platform %s not found — skipping", sku_platform_id
        )
        return

    sp_id, product_id, page_url, platform_id, org_id = row

    if not product_id or not str(product_id).strip():
        logger.info(
            "collect_samocat_stock: NO_PRODUCT_ID for sku_platform %s — skipping",
            sku_platform_id,
        )
        return

    product_id = str(product_id).strip()
    now_utc = datetime.now(tz=timezone.utc)
    today = now_utc.date()
    with get_db_session() as db:
        router = ScraperRouter(db, redis_client=get_redis_client())
        try:
            stock_data = router.collect(
                platform_id=platform_id,
                sku_id=product_id,
                data_type=DataType.STOCK,
                org_id=org_id,
                page_url=page_url,
            )
        except ScraperError as exc:
            if exc.code == "NOT_FOUND":
                logger.info(
                    "collect_samocat_stock: product sku_platform=%s not found on Samocat — skipping",
                    sku_platform_id,
                )
                return
            logger.warning(
                "collect_samocat_stock: ScraperError code=%s sku_platform=%s",
                exc.code,
                sku_platform_id,
            )
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)

        scraper_level: int | None = getattr(stock_data, "scraper_level", None)
        # Partial-row upsert: set_ includes ONLY stock fields.
        # Content fields are intentionally absent from set_ so they are never
        # overwritten if the content task already ran first.
        stmt = (
            pg_insert(ContentScore)
            .values(
                id=uuid.uuid4(),
                sku_platform_id=sp_id,
                scored_at=today,
                in_stock=stock_data.in_stock,
                warehouse_qty=stock_data.total_qty,
                scraper_level=scraper_level,
                created_at=now_utc,
            )
            .on_conflict_do_update(
                constraint="uq_content_scores_sp_date",
                set_={
                    "in_stock": stock_data.in_stock,
                    "warehouse_qty": stock_data.total_qty,
                    "scraper_level": scraper_level,
                    # content fields intentionally absent — partial-row contract
                },
            )
        )
        db.execute(stmt)

    logger.info(
        "collect_samocat_stock: done sku_platform=%s scraper_level=%s",
        sku_platform_id,
        scraper_level,
    )
