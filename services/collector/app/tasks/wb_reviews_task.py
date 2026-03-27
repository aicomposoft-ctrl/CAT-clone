"""
Celery task: collect reviews for a Wildberries SKU.

Fetches the 50 most recent reviews from WB feedbacks API.
Uses INSERT ON CONFLICT DO NOTHING (via uq_reviews_sp_ext_id) for deduplication.

Runs daily alongside the content task from the orchestrator.

Error handling:
  - NO_NM_ID: external_id is None → silent skip
  - NOT_FOUND: product missing → log and return, 0 rows written
  - ScraperError → retry (max 3, exponential backoff)
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
        sp = (
            db.query(SKUPlatform)
            .join(SKU, SKU.id == SKUPlatform.sku_id)
            .filter(SKUPlatform.id == uuid.UUID(sku_platform_id))
            .first()
        )

    if sp is None:
        logger.warning("collect_wb_reviews: sku_platform %s not found — skipping", sku_platform_id)
        return

    nm_id = sp.external_id
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
    with get_db_session() as db:
        for review in reviews:
            stmt = (
                pg_insert(Review)
                .values(
                    id=uuid.uuid4(),
                    sku_platform_id=sp.id,
                    external_review_id=review.external_review_id,
                    review_text=review.review_text,
                    rating=review.rating,
                    review_date=review.review_date,
                    collected_at=now,
                )
                .on_conflict_do_nothing(constraint="uq_reviews_sp_ext_id")
            )
            db.execute(stmt)

    logger.info("collect_wb_reviews: done nm_id=%s count=%d", nm_id, len(reviews))
