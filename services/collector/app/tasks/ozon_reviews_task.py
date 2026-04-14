"""
Celery task: collect reviews for an Ozon SKU.

Fetches the 50 most recent reviews from the Ozon composer API reviews endpoint.
Uses a single bulk INSERT ON CONFLICT DO NOTHING for idempotent deduplication
(constraint: uq_reviews_sp_ext_id).  Never loops per-review — single execute().

(sp_id, external_id, org_id) extracted as primitives within the first DB
session to avoid DetachedInstanceError after session close.

Error handling:
  - NO_ITEM_ID:                  external_id empty → silent skip
  - PARSE_ERROR:                 item_id not numeric → log warning, return
  - NOT_FOUND:                   product missing → log info, return, 0 rows written
  - RATE_LIMITED / API_UNAVAILABLE → self.retry() (max 3, exponential backoff)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.celery_app import celery_app
from app.core.base_scraper import ScraperError
from app.core.proxy import get_proxy_rotator
from app.models import Review, SKUPlatform, SKU
from app.scrapers.ozon import OzonScraper, _parse_item_id
from app.tasks._db import get_db_session

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=3,
    name="ozon.collect_reviews",
)
def collect_ozon_reviews(self, sku_platform_id: str) -> None:
    """
    Collect and deduplicate reviews for one Ozon SKUPlatform.

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
            "collect_ozon_reviews: sku_platform %s not found — skipping", sku_platform_id
        )
        return

    sp_id, raw_item_id, org_id = row

    # Validate item_id before any HTTP call
    try:
        item_id = _parse_item_id(raw_item_id)
    except ValueError:
        # NO_ITEM_ID — external_id is None or empty string
        logger.info(
            "collect_ozon_reviews: NO_ITEM_ID for sku_platform %s — skipping", sku_platform_id
        )
        return
    except ScraperError as exc:
        # PARSE_ERROR — item_id present but non-numeric
        logger.warning(
            "collect_ozon_reviews: invalid item_id %r for sku_platform %s: %s",
            raw_item_id,
            sku_platform_id,
            exc,
        )
        return

    scraper = OzonScraper(proxy_rotator=get_proxy_rotator())

    try:
        reviews = asyncio.run(scraper.collect_reviews(item_id, take=50))
    except ScraperError as exc:
        if exc.code == "NOT_FOUND":
            logger.info(
                "collect_ozon_reviews: product item_id=%s not found on Ozon — skipping", item_id
            )
            return
        logger.warning(
            "collect_ozon_reviews: ScraperError code=%s item_id=%s", exc.code, item_id
        )
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    if not reviews:
        logger.info("collect_ozon_reviews: 0 reviews for item_id=%s", item_id)
        return

    now = datetime.now(tz=timezone.utc)
    # Build list of dicts; skip any review without an external_review_id
    # (can't deduplicate without a stable key — safer to discard than insert duplicates)
    values = [
        {
            "id": uuid.uuid4(),
            "sku_platform_id": sp_id,
            "external_review_id": review.external_review_id,
            "review_text": review.review_text,
            "rating": review.rating,
            "review_date": review.review_date,
            "collected_at": now,
        }
        for review in reviews
        if review.external_review_id
    ]

    if not values:
        logger.info(
            "collect_ozon_reviews: all reviews had empty external_review_id for item_id=%s",
            item_id,
        )
        return

    with get_db_session() as db:
        # Single bulk INSERT — no per-review loop (avoids N+1 round-trips)
        stmt = (
            pg_insert(Review)
            .values(values)
            .on_conflict_do_nothing(constraint="uq_reviews_sp_ext_id")
        )
        db.execute(stmt)

    logger.info("collect_ozon_reviews: done item_id=%s count=%d", item_id, len(values))
