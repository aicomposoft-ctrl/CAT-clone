"""
Celery task: collect reviews for a Samocat SKU.

Fetches the 50 most recent reviews from the Samocat API reviews endpoint
(`GET /v2/items/{product_id}/reviews?page=1&limit=50`).  Uses a bulk
INSERT ON CONFLICT DO UPDATE for idempotent upsert: existing reviews are
updated with the latest review_text and rating (constraint: uq_reviews_sp_ext_id).
Never loops per-review — single execute() call.

(sp_id, external_id, org_id) extracted as primitives within the first DB
session to avoid DetachedInstanceError after session close.

Error handling:
  - NO_PRODUCT_ID:              external_id empty → silent skip
  - PARSE_ERROR:                product_id not numeric → log warning, return
  - NOT_FOUND:                  404 on reviews endpoint → empty list → return 0 rows
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
from app.scrapers.samocat import SamokatScraper, _parse_product_id
from app.tasks._db import get_db_session

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=3,
    name="samocat.collect_reviews",
)
def collect_samocat_reviews(self, sku_platform_id: str) -> None:
    """
    Collect and upsert reviews for one Samocat SKUPlatform.

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
            "collect_samocat_reviews: sku_platform %s not found — skipping", sku_platform_id
        )
        return

    sp_id, raw_product_id, org_id = row

    if not raw_product_id or not str(raw_product_id).strip():
        logger.info(
            "collect_samocat_reviews: NO_PRODUCT_ID for sku_platform %s — skipping",
            sku_platform_id,
        )
        return
    product_id = str(raw_product_id).strip()

    scraper = SamokatScraper(proxy_rotator=get_proxy_rotator())

    try:
        reviews = asyncio.run(scraper.collect_reviews(product_id, take=50))
    except ScraperError as exc:
        if exc.code == "NOT_FOUND":
            logger.info(
                "collect_samocat_reviews: product sku_platform=%s not found on Samocat — skipping",
                sku_platform_id,
            )
            return
        logger.warning(
            "collect_samocat_reviews: ScraperError code=%s sku_platform=%s",
            exc.code,
            sku_platform_id,
        )
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    if not reviews:
        logger.info(
            "collect_samocat_reviews: 0 reviews for sku_platform=%s", sku_platform_id
        )
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
            "collect_samocat_reviews: all reviews had empty external_review_id for sku_platform=%s",
            sku_platform_id,
        )
        return

    with get_db_session() as db:
        # Single bulk INSERT ON CONFLICT DO UPDATE — no per-review loop (avoids N+1 round-trips)
        # Updates review_text and rating so edits on the platform are reflected.
        insert_stmt = pg_insert(Review).values(values)
        stmt = insert_stmt.on_conflict_do_update(
            constraint="uq_reviews_sp_ext_id",
            set_={
                "review_text": insert_stmt.excluded.review_text,
                "rating": insert_stmt.excluded.rating,
            },
        )
        db.execute(stmt)

    logger.info(
        "collect_samocat_reviews: done sku_platform=%s count=%d", sku_platform_id, len(values)
    )
