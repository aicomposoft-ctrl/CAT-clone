"""
Celery task: collect stock availability for an Ozon SKU.

Upserts stock fields (in_stock, warehouse_qty) into content_scores for today
using INSERT ... ON CONFLICT DO UPDATE (partial-row contract).

Partial-row contract: if no content_scores row exists yet for today, this task
creates one with only stock fields populated.  Content fields remain NULL until
collect_ozon_content runs.  The ML scoring pipeline MUST filter:
  WHERE collected_description IS NOT NULL

Only stock fields are included in the ON CONFLICT set_ clause — content fields
(collected_title, collected_description, etc.) are intentionally omitted so
they are never overwritten by a stock task running after a content task.

(sp_id, external_id, org_id) extracted as primitives within the first DB
session to avoid DetachedInstanceError after session close.

Error handling:
  - NO_ITEM_ID:                  external_id empty → silent skip, no DB write
  - PARSE_ERROR:                 item_id not numeric → log warning, return
  - NOT_FOUND:                   product missing → log info, return, no write
  - RATE_LIMITED / API_UNAVAILABLE → self.retry() (max 3, exponential backoff), no write
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.celery_app import celery_app
from app.core.base_scraper import ScraperError
from app.core.proxy import get_proxy_rotator
from app.models import ContentScore, SKUPlatform, SKU
from app.scrapers.ozon import OzonScraper, _parse_item_id
from app.tasks._db import get_db_session

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=3,
    name="ozon.collect_stock",
)
def collect_ozon_stock(self, sku_platform_id: str) -> None:
    """
    Collect stock availability for one Ozon SKUPlatform.

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
            "collect_ozon_stock: sku_platform %s not found — skipping", sku_platform_id
        )
        return

    sp_id, raw_item_id, org_id = row

    # Validate item_id before any HTTP call
    try:
        item_id = _parse_item_id(raw_item_id)
    except ValueError:
        # NO_ITEM_ID — external_id is None or empty string
        logger.info(
            "collect_ozon_stock: NO_ITEM_ID for sku_platform %s — skipping", sku_platform_id
        )
        return
    except ScraperError as exc:
        # PARSE_ERROR — item_id present but non-numeric
        logger.warning(
            "collect_ozon_stock: invalid item_id %r for sku_platform %s: %s",
            raw_item_id,
            sku_platform_id,
            exc,
        )
        return

    scraper = OzonScraper(proxy_rotator=get_proxy_rotator())

    try:
        stock_data = asyncio.run(scraper.collect_stock(item_id))
    except ScraperError as exc:
        if exc.code == "NOT_FOUND":
            logger.info(
                "collect_ozon_stock: product item_id=%s not found on Ozon — skipping", item_id
            )
            return
        logger.warning(
            "collect_ozon_stock: ScraperError code=%s item_id=%s", exc.code, item_id
        )
        # No DB write on API failure — retry instead
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    today = date.today()
    with get_db_session() as db:
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
                created_at=datetime.now(tz=timezone.utc),
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

    logger.info(
        "collect_ozon_stock: done item_id=%s in_stock=%s qty=%s",
        item_id,
        stock_data.in_stock,
        stock_data.total_qty,
    )
