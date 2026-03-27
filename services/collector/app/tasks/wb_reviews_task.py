"""
Celery task: collect reviews for a Wildberries SKU.

Fetches the 50 most recent reviews from WB feedbacks API.
Uses a single bulk INSERT ON CONFLICT DO NOTHING for deduplication
(constraint: uq_reviews_sp_ext_id).

org_id extracted as a primitive within the first DB session to avoid
DetachedInstanceError from lazy relationships after session close.

Error handling:
  - NO_NM_ID: external_id is None → silent skip
  - NOT_FOUND: product missing → log and return, 0 rows written
  - ScraperError → self.retry() (max 3, exponential backoff)
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
from app.scrapers.wildberries import WildberriesScraper
from app.tasks._db import get_db_session

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=3,
    name="wb.collect_reviews",
)
def collect_wb_reviews(self, sku_platform_id: str) -> None:
    """
    Collect and deduplicate reviews for one WB SKUPlatform.

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
        logger.warning("collect_wb_reviews: sku_platform %s not found — skipping", sku_platform_id)
        return

    sp_id, nm_id, org_id = row

    if not nm_id:
        logger.info("collect_wb_reviews: NO_NM_ID for sku_platform %s — skipping", sku_platform_id)
        return

    scraper = WildberriesScraper(proxy_rotator=get_proxy_rotator())

    try:
        reviews = asyncio.run(scraper.collect_reviews(nm_id, take=50))
    except ScraperError as exc:
        if exc.code == "NOT_FOUND":
            logger.info("collect_wb_reviews: product nm_id=%s not found on WB — skipping", nm_id)
            return
        logger.warning("collect_wb_reviews: ScraperError code=%s nm_id=%s", exc.code, nm_id)
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    if not reviews:
        logger.info("collect_wb_reviews: 0 reviews for nm_id=%s", nm_id)
        return

    now = datetime.now(tz=timezone.utc)
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
    ]

    with get_db_session() as db:
        stmt = (
            pg_insert(Review)
            .values(values)
            .on_conflict_do_nothing(constraint="uq_reviews_sp_ext_id")
        )
        db.execute(stmt)

    logger.info("collect_wb_reviews: done nm_id=%s count=%d", nm_id, len(reviews))
