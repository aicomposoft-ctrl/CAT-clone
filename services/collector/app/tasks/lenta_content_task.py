"""
Celery task: collect content for a Lenta SKU.

Delegates to ScraperRouter for adaptive L1→L2→L3 fallback.
Downloads the product image asynchronously and stores it in MinIO (S3).
Upserts a content_scores row using INSERT ... ON CONFLICT DO UPDATE.

Key design decisions:
  - ScraperRouter handles L1/L2/L3 fallback transparently.
  - (sp_id, sku_id, external_id, platform_id, org_id) extracted as primitives
    WITHIN the first DB session to avoid DetachedInstanceError.
  - Image download uses async httpx (asyncio.run) with proxy rotation.
  - Image URL validated against _LT_IMAGE_CDN_RE SSRF allowlist before download.
  - Image failure is non-fatal: s3_key stays None, content upsert proceeds.

Error handling:
  - NO_PRODUCT_ID:              external_id empty → silent skip, no DB write
  - NOT_FOUND:                  product delisted → log info, return
  - RATE_LIMITED / API_UNAVAILABLE / PARSE_ERROR → self.retry() (max 3)
  - ALL_LEVELS_FAILED → self.retry() (max 3)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

import redis as redis_lib

from app.celery_app import REDIS_URL, celery_app
from app.core.base_scraper import ContentData, DataType, ScraperError
from app.core.proxy import get_proxy_rotator
from app.core.scraper_router import ScraperRouter
from app.models import ContentScore, SKUPlatform, SKU
from app.scrapers.lenta import _download_image_async, _LT_IMAGE_CDN_RE
from app.tasks._db import get_db_session

logger = logging.getLogger(__name__)


def _get_minio():
    """Lazy import to avoid circular deps and allow mocking in tests."""
    from app.core.minio_client import MinioClient  # noqa: PLC0415
    return MinioClient()


@celery_app.task(
    bind=True,
    max_retries=3,
    name="lenta.collect_content",
)
def collect_lenta_content(self, sku_platform_id: str) -> None:
    """
    Collect content (title, description, composition, image) for one Lenta SKUPlatform.

    Delegates to ScraperRouter (L1→L2→L3 fallback).

    Args:
        sku_platform_id: UUID string of the sku_platforms row.
    """
    with get_db_session() as db:
        row = (
            db.query(
                SKUPlatform.id,
                SKUPlatform.sku_id,
                SKUPlatform.external_id,
                SKUPlatform.platform_id,
                SKU.org_id,
            )
            .join(SKU, SKU.id == SKUPlatform.sku_id)
            .filter(SKUPlatform.id == uuid.UUID(sku_platform_id))
            .first()
        )

    if row is None:
        logger.warning(
            "collect_lenta_content: sku_platform %s not found — skipping", sku_platform_id
        )
        return

    sp_id, sku_id, raw_product_id, platform_id, org_id = row

    if not raw_product_id or not str(raw_product_id).strip():
        logger.info(
            "collect_lenta_content: NO_PRODUCT_ID for sku_platform %s — skipping",
            sku_platform_id,
        )
        return
    product_id = str(raw_product_id).strip()

    with get_db_session() as db:
        _redis = redis_lib.from_url(REDIS_URL, decode_responses=False)
        router = ScraperRouter(db, redis_client=_redis)
        try:
            content: ContentData = router.collect(
                platform_id=platform_id,
                sku_id=product_id,
                data_type=DataType.CONTENT,
                org_id=org_id,
            )
        except ScraperError as exc:
            if exc.code == "NOT_FOUND":
                logger.info(
                    "collect_lenta_content: product sku_platform=%s not found — skipping",
                    sku_platform_id,
                )
                return
            logger.warning(
                "collect_lenta_content: ScraperError code=%s sku_platform=%s",
                exc.code,
                sku_platform_id,
            )
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)

        scraper_level: int | None = getattr(content, "scraper_level", None)

        # Download image — non-fatal
        s3_key: str | None = None
        if content.image_url and _LT_IMAGE_CDN_RE.match(content.image_url):
            try:
                proxy = get_proxy_rotator().next()
                image_bytes = asyncio.run(_download_image_async(content.image_url, proxy))
                s3_key = f"org/{org_id}/sku/{sku_id}/lenta/main.jpg"
                _get_minio().upload(s3_key, image_bytes, "image/jpeg")
            except Exception:  # noqa: BLE001
                logger.warning(
                    "collect_lenta_content: image download/upload failed for sku_platform=%s",
                    sku_platform_id,
                )
                s3_key = None
        elif content.image_url:
            logger.warning(
                "collect_lenta_content: image URL failed SSRF allowlist for sku_platform=%s",
                sku_platform_id,
            )

        now_utc = datetime.now(tz=timezone.utc)
        today = now_utc.date()
        stmt = (
            pg_insert(ContentScore)
            .values(
                id=uuid.uuid4(),
                sku_platform_id=sp_id,
                scored_at=today,
                collected_title=content.title,
                collected_description=content.description,
                collected_composition=content.composition,
                collected_image_url=s3_key,
                scraper_level=scraper_level,
                created_at=now_utc,
            )
            .on_conflict_do_update(
                constraint="uq_content_scores_sp_date",
                set_={
                    "collected_title": content.title,
                    "collected_description": content.description,
                    "collected_composition": content.composition,
                    "collected_image_url": s3_key,
                    "scraper_level": scraper_level,
                },
            )
        )
        db.execute(stmt)

    logger.info(
        "collect_lenta_content: done sku_platform=%s scraper_level=%s",
        sku_platform_id,
        scraper_level,
    )
