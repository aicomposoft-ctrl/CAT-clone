"""
Celery task: collect content for a Wildberries SKU.

Fetches product title, description, composition, and image from WB card API.
Downloads image async (via proxy) and stores it in MinIO (S3).
Upserts a content_scores row.

Key design decisions:
  - org_id and sku_id are extracted as primitives WITHIN the first DB session to
    avoid DetachedInstanceError from lazy-loaded relationships after session close.
  - Image download uses async httpx (via asyncio.run) with proxy rotation — never
    bare sync httpx.get(), which would block the worker process for up to 30s.
  - No autoretry_for on the decorator — manual self.retry() handles all retry logic
    to avoid double-retry conflicts.

Error handling:
  - NO_NM_ID:  external_id is None → silent skip, no DB write
  - NOT_FOUND: product deleted/invalid → log and return, no DB write
  - RATE_LIMITED / API_UNAVAILABLE / PARSE_ERROR → retry via self.retry() (max 3)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, timezone

import httpx

from app.celery_app import celery_app
from app.core.base_scraper import ScraperError
from app.core.proxy import get_proxy_rotator
from app.core.sanitize import sanitize
from app.models import ContentScore, SKUPlatform, SKU
from app.scrapers.wildberries import WildberriesScraper, _WB_IMAGE_CDN_RE
from app.tasks._db import get_db_session

logger = logging.getLogger(__name__)


def _get_minio():
    """Lazy import to avoid circular deps and allow mocking in tests."""
    from app.core.minio_client import MinioClient  # noqa: PLC0415
    return MinioClient()


async def _download_image_async(url: str, proxy: str | None) -> bytes:
    """Download image bytes asynchronously using proxy. Raises on HTTP error."""
    async with httpx.AsyncClient(proxy=proxy, timeout=30.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


@celery_app.task(
    bind=True,
    max_retries=3,
    name="wb.collect_content",
)
def collect_wb_content(self, sku_platform_id: str) -> None:
    """
    Collect content (title, description, composition, image) for one WB SKUPlatform.

    Args:
        sku_platform_id: UUID string of the sku_platforms row.
    """
    # Load SKUPlatform and extract primitive values within the session to avoid
    # DetachedInstanceError from lazy relationships after session close.
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
        logger.warning("collect_wb_content: sku_platform %s not found — skipping", sku_platform_id)
        return

    sp_id, sku_id, nm_id, org_id = row

    if not nm_id:
        logger.info("collect_wb_content: NO_NM_ID for sku_platform %s — skipping", sku_platform_id)
        return

    scraper = WildberriesScraper(proxy_rotator=get_proxy_rotator())

    try:
        content = asyncio.run(scraper.collect_content(nm_id))
    except ScraperError as exc:
        if exc.code == "NOT_FOUND":
            logger.info(
                "collect_wb_content: product nm_id=%s not found on WB — skipping", nm_id
            )
            return
        logger.warning("collect_wb_content: ScraperError code=%s nm_id=%s", exc.code, nm_id)
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    # Download and upload image to MinIO via async httpx + proxy (non-fatal if this fails)
    s3_key: str | None = None
    if content.image_url and _WB_IMAGE_CDN_RE.match(content.image_url):
        try:
            proxy = get_proxy_rotator().next()
            image_bytes = asyncio.run(_download_image_async(content.image_url, proxy))
            s3_key = f"org/{org_id}/sku/{sku_id}/wb/main.jpg"
            minio = _get_minio()
            minio.upload(s3_key, image_bytes, "image/jpeg")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "collect_wb_content: image download/upload failed for nm_id=%s", nm_id
            )
            s3_key = None
    elif content.image_url:
        # Log only that it failed, not the URL value (untrusted scraped data)
        logger.warning(
            "collect_wb_content: image URL failed SSRF allowlist for nm_id=%s", nm_id
        )

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
            existing.collected_title = sanitize(content.title, 500)
            existing.collected_description = sanitize(content.description, 5000)
            existing.collected_composition = sanitize(content.composition or "", 2000) or None
            existing.collected_image_url = s3_key
        else:
            db.add(
                ContentScore(
                    id=uuid.uuid4(),
                    sku_platform_id=sp_id,
                    scored_at=today,
                    collected_title=sanitize(content.title, 500),
                    collected_description=sanitize(content.description, 5000),
                    collected_composition=sanitize(content.composition or "", 2000) or None,
                    collected_image_url=s3_key,
                    created_at=datetime.now(tz=timezone.utc),
                )
            )

    logger.info("collect_wb_content: done nm_id=%s", nm_id)
