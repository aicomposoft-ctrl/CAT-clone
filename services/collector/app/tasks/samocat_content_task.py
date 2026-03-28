"""
Celery task: collect content for a Samocat SKU.

Fetches product title, description, composition, and image from the Samocat
API (`GET /v2/items/{product_id}`).  Downloads the main product image
asynchronously via proxy and stores it in MinIO (S3).  Upserts a
content_scores row using INSERT ... ON CONFLICT DO UPDATE so concurrent
content + stock task execution is safe.

Key design decisions:
  - (sp_id, sku_id, external_id, org_id) extracted as primitives WITHIN the
    first DB session to avoid DetachedInstanceError after session close.
  - product_id validated via _parse_product_id() before any HTTP call:
      ValueError("NO_PRODUCT_ID")     → silent skip
      ScraperError("PARSE_ERROR")     → log and return
  - Image download uses async httpx (asyncio.run) with proxy rotation —
    never bare sync httpx.get() which would block the worker process.
  - Image URL validated against _SK_IMAGE_CDN_RE SSRF allowlist before
    download; non-matching URLs are logged (without the URL value) and
    skipped.
  - Image failure is non-fatal: s3_key stays None, content upsert proceeds.
  - No autoretry_for on the decorator — manual self.retry() only.

Error handling:
  - NO_PRODUCT_ID:              external_id empty → silent skip, no DB write
  - PARSE_ERROR:                product_id not numeric → log warning, return
  - NOT_FOUND:                  product delisted → log info, return
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
from app.models import ContentScore, SKUPlatform, SKU
from app.scrapers.samocat import SamokatScraper, _SK_IMAGE_CDN_RE, _download_image_async, _parse_product_id
from app.tasks._db import get_db_session

logger = logging.getLogger(__name__)


def _get_minio():
    """Lazy import to avoid circular deps and allow mocking in tests."""
    from app.core.minio_client import MinioClient  # noqa: PLC0415
    return MinioClient()


@celery_app.task(
    bind=True,
    max_retries=3,
    name="samocat.collect_content",
)
def collect_samocat_content(self, sku_platform_id: str) -> None:
    """
    Collect content (title, description, composition, image) for one Samocat SKUPlatform.

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
                SKU.org_id,
            )
            .join(SKU, SKU.id == SKUPlatform.sku_id)
            .filter(SKUPlatform.id == uuid.UUID(sku_platform_id))
            .first()
        )

    if row is None:
        logger.warning(
            "collect_samocat_content: sku_platform %s not found — skipping", sku_platform_id
        )
        return

    sp_id, sku_id, raw_product_id, org_id = row

    # Validate product_id before any HTTP call
    try:
        product_id = _parse_product_id(raw_product_id)
    except ValueError:
        # NO_PRODUCT_ID — external_id is None or empty string
        logger.info(
            "collect_samocat_content: NO_PRODUCT_ID for sku_platform %s — skipping",
            sku_platform_id,
        )
        return
    except ScraperError as exc:
        # PARSE_ERROR — product_id present but non-numeric
        logger.warning(
            "collect_samocat_content: invalid product_id for sku_platform %s: %s",
            sku_platform_id,
            exc,
        )
        return

    scraper = SamokatScraper(proxy_rotator=get_proxy_rotator())

    try:
        content = asyncio.run(scraper.collect_content(product_id))
    except ScraperError as exc:
        if exc.code == "NOT_FOUND":
            logger.info(
                "collect_samocat_content: product sku_platform=%s not found on Samocat — skipping",
                sku_platform_id,
            )
            return
        logger.warning(
            "collect_samocat_content: ScraperError code=%s sku_platform=%s",
            exc.code,
            sku_platform_id,
        )
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    # Download main image and upload to MinIO — non-fatal if this fails
    s3_key: str | None = None
    if content.image_url and _SK_IMAGE_CDN_RE.match(content.image_url):
        try:
            proxy = get_proxy_rotator().next()
            image_bytes = asyncio.run(_download_image_async(content.image_url, proxy))
            s3_key = f"org/{org_id}/sku/{sku_id}/samocat/main.jpg"
            minio = _get_minio()
            minio.upload(s3_key, image_bytes, "image/jpeg")
        except Exception:  # noqa: BLE001
            logger.warning(
                "collect_samocat_content: image download/upload failed for sku_platform=%s",
                sku_platform_id,
            )
            s3_key = None
    elif content.image_url:
        # URL was present but failed the SSRF allowlist — log without the URL value
        # (untrusted scraped data should not be written to logs)
        logger.warning(
            "collect_samocat_content: image URL failed SSRF allowlist for sku_platform=%s",
            sku_platform_id,
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
                created_at=now_utc,
            )
            .on_conflict_do_update(
                constraint="uq_content_scores_sp_date",
                set_={
                    "collected_title": content.title,
                    "collected_description": content.description,
                    "collected_composition": content.composition,
                    "collected_image_url": s3_key,
                },
            )
        )
        db.execute(stmt)

    logger.info("collect_samocat_content: done sku_platform=%s", sku_platform_id)
