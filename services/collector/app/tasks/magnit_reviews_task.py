"""Celery task: collect reviews for a Magnit SKU."""

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
from app.scrapers.magnit import MagnitScraper
from app.tasks._db import get_db_session

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, name="magnit.collect_reviews")
def collect_magnit_reviews(self, sku_platform_id: str) -> None:
    """Collect and upsert reviews for one Magnit SKUPlatform."""
    with get_db_session() as db:
        row = (
            db.query(SKUPlatform.id, SKUPlatform.external_id, SKU.org_id)
            .join(SKU, SKU.id == SKUPlatform.sku_id)
            .filter(SKUPlatform.id == uuid.UUID(sku_platform_id))
            .first()
        )

    if row is None:
        logger.warning("collect_magnit_reviews: sku_platform %s not found", sku_platform_id)
        return

    sp_id, product_id, org_id = row
    if not product_id:
        return

    scraper = MagnitScraper(proxy_rotator=get_proxy_rotator())
    try:
        reviews = asyncio.run(scraper.collect_reviews(product_id, take=50))
    except ScraperError as exc:
        if exc.code == "NOT_FOUND":
            return
        logger.warning(
            "collect_magnit_reviews: ScraperError code=%s sku_platform=%s",
            exc.code, sku_platform_id,
        )
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    if not reviews:
        return

    now = datetime.now(tz=timezone.utc)
    values = [
        {
            "id": uuid.uuid4(),
            "sku_platform_id": sp_id,
            "external_review_id": r.external_review_id,
            "review_text": r.review_text,
            "rating": r.rating,
            "review_date": r.review_date,
            "collected_at": now,
        }
        for r in reviews
        if r.external_review_id
    ]

    if not values:
        return

    with get_db_session() as db:
        insert_stmt = pg_insert(Review).values(values)
        db.execute(
            insert_stmt.on_conflict_do_update(
                constraint="uq_reviews_sp_ext_id",
                set_={
                    "review_text": insert_stmt.excluded.review_text,
                    "rating": insert_stmt.excluded.rating,
                    "review_date": insert_stmt.excluded.review_date,
                },
            )
        )

    logger.info(
        "collect_magnit_reviews: done sku_platform=%s count=%d",
        sku_platform_id, len(values),
    )
