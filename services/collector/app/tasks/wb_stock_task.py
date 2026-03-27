"""
Celery task: collect stock availability for a Wildberries SKU.

Upserts stock fields (in_stock, warehouse_qty) into content_scores for today.

Partial-row contract: if no content_scores row exists yet for today, this task
creates one with only stock fields set. Content fields remain NULL.
ML scoring pipeline MUST filter WHERE collected_description IS NOT NULL.

org_id extracted as a primitive within the first DB session to avoid
DetachedInstanceError from lazy relationships after session close.

Error handling:
  - NO_NM_ID:    external_id is None → silent skip
  - NOT_FOUND:   product missing → log and return, no write
  - API_UNAVAILABLE → self.retry() (max 3, exponential backoff), no write on failure
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, timezone

from app.celery_app import celery_app
from app.core.base_scraper import ScraperError
from app.core.proxy import get_proxy_rotator
from app.models import ContentScore, SKUPlatform, SKU
from app.scrapers.wildberries import WildberriesScraper
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
        logger.warning("collect_wb_stock: sku_platform %s not found — skipping", sku_platform_id)
        return

    sp_id, nm_id, org_id = row

    if not nm_id:
        logger.info("collect_wb_stock: NO_NM_ID for sku_platform %s — skipping", sku_platform_id)
        return

    scraper = WildberriesScraper(proxy_rotator=get_proxy_rotator())

    try:
        stock_data = asyncio.run(scraper.collect_stock(nm_id))
    except ScraperError as exc:
        if exc.code == "NOT_FOUND":
            logger.info("collect_wb_stock: product nm_id=%s not found on WB — skipping", nm_id)
            return
        logger.warning("collect_wb_stock: ScraperError code=%s nm_id=%s", exc.code, nm_id)
        # No DB write on API failure — retry instead
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    today = date.today()
    with get_db_session() as db:
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
                    created_at=datetime.now(tz=timezone.utc),
                )
            )

    logger.info(
        "collect_wb_stock: done nm_id=%s in_stock=%s qty=%s",
        nm_id,
        stock_data.in_stock,
        stock_data.total_qty,
    )
