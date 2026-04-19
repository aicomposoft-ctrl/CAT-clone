"""
Celery task: collect content for an Ozon SKU.

Fetches product title, description, composition, and image from the Ozon
composer API (widgetStates double-JSON pattern).  Downloads the main product
image asynchronously via proxy and stores it in MinIO (S3).  Upserts a
content_scores row using INSERT ... ON CONFLICT DO UPDATE so concurrent
content + stock task execution is safe.

Key design decisions:
  - (sp_id, sku_id, external_id, org_id) extracted as primitives WITHIN the
    first DB session to avoid DetachedInstanceError after session close.
  - item_id validated via _parse_item_id() before any HTTP call:
      ValueError("NO_ITEM_ID")        → silent skip
      ScraperError("PARSE_ERROR")     → log and return
  - Image download uses async httpx (asyncio.run) with proxy rotation —
    never bare sync httpx.get() which would block the worker process.
  - Image failure is non-fatal: s3_key stays None, content upsert proceeds.
  - No autoretry_for on the decorator — manual self.retry() only.

Error handling:
  - NO_ITEM_ID:                  external_id empty → silent skip, no DB write
  - PARSE_ERROR:                 item_id not numeric → log warning, return
  - NOT_FOUND:                   product delisted → log info, return
  - RATE_LIMITED / API_UNAVAILABLE → self.retry() (max 3, exponential backoff)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.celery_app import celery_app
from app.core.base_scraper import DataType, ScraperError
from app.core.proxy import get_proxy_rotator
from app.core.scraper_router import ScraperRouter
from app.models import ContentScore, SKUPlatform, SKU
from app.scrapers.ozon import _OZ_IMAGE_CDN_RE, _download_image_async
from app.tasks._db import get_db_session
from app.tasks._redis import get_redis_client
from app.tasks._retry_policy import should_retry_scrape_error

logger = logging.getLogger(__name__)


def _get_minio():
    """Lazy import to avoid circular deps and allow mocking in tests."""
    from app.core.minio_client import MinioClient  # noqa: PLC0415
    return MinioClient()


@celery_app.task(
    bind=True,
    max_retries=3,
    name="ozon.collect_content",
)
def collect_ozon_content(self, sku_platform_id: str) -> None:
    """
    Collect content (title, description, composition, image) for one Ozon SKUPlatform.

    Args:
        sku_platform_id: UUID string of the sku_platforms row.
    """
    # Extract primitive values within the session — ORM objects must NOT escape
    # the session boundary (DetachedInstanceError on lazy-loaded attributes).
    with get_db_session() as db:
        row = (
            db.query(
                SKUPlatform.id,
                SKUPlatform.sku_id,
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
            "collect_ozon_content: sku_platform %s not found — skipping", sku_platform_id
        )
        return

    sp_id, sku_id, item_id, page_url, platform_id, org_id = row

    if not item_id:
        logger.info("collect_ozon_content: NO_ITEM_ID for sku_platform %s — skipping", sku_platform_id)
        return

    with get_db_session() as db:
        router = ScraperRouter(db, redis_client=get_redis_client())
        try:
            content = router.collect(
                platform_id=platform_id,
                sku_id=item_id,
                data_type=DataType.CONTENT,
                org_id=org_id,
                page_url=page_url,
            )
        except ScraperError as exc:
            if exc.code == "NOT_FOUND":
                logger.info("collect_ozon_content: product item_id=%s not found on Ozon — skipping", item_id)
                return
            logger.warning("collect_ozon_content: ScraperError code=%s item_id=%s", exc.code, item_id)
            if not should_retry_scrape_error(exc):
                raise
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)
        scraper_level: int | None = getattr(content, "scraper_level", None)

    # Download main image and upload to MinIO — non-fatal if this fails
    s3_key: str | None = None
    if content.image_url and _OZ_IMAGE_CDN_RE.match(content.image_url):
        try:
            proxy = get_proxy_rotator().next()
            image_bytes = asyncio.run(_download_image_async(content.image_url, proxy))
            s3_key = f"org/{org_id}/sku/{sku_id}/ozon/main.jpg"
            minio = _get_minio()
            minio.upload(s3_key, image_bytes, "image/jpeg")
        except Exception:  # noqa: BLE001
            logger.warning(
                "collect_ozon_content: image download/upload failed for item_id=%s", item_id
            )
            s3_key = None
    elif content.image_url:
        # URL was present but failed the allowlist — log without the URL value
        # (untrusted scraped data should not be written to logs)
        logger.warning(
            "collect_ozon_content: image URL failed SSRF allowlist for item_id=%s", item_id
        )

    now_utc = datetime.now(tz=timezone.utc)
    today = now_utc.date()
    with get_db_session() as db:
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

    logger.info("collect_ozon_content: done item_id=%s scraper_level=%s", item_id, scraper_level)
