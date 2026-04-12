"""
Celery task: collect content for a Wildberries SKU.

Fetches product title, description, composition, and image from WB card API.
Downloads image async (via proxy) and stores it in MinIO (S3).
Upserts a content_scores row including the scraper_level provenance field.

Key design decisions:
  - All scraping is now delegated to ScraperRouter, which handles the fallback
    chain (L0 token → L1 public API → L2 browser) transparently. Task signature
    is unchanged for backward compatibility (R-04).
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
  - ALL_LEVELS_FAILED → retry via self.retry() (max 3)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, timezone

import httpx

from app.celery_app import celery_app
from app.core.base_scraper import ContentData, DataType, ScraperError
from app.core.proxy import get_proxy_rotator
from app.core.sanitize import sanitize
from app.core.scraper_router import ScraperRouter
from app.models import ContentScore, SKUPlatform, SKU
from app.scrapers.wildberries import _WB_IMAGE_CDN_RE
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


def _save_content_score(
    db,
    sp_id: uuid.UUID,
    sku_id: uuid.UUID,
    org_id: uuid.UUID,
    nm_id: str,
    content: ContentData,
    scraper_level: int | None,
) -> None:
    """
    Upsert a ContentScore row for today.

    Preserves the partial-row contract: if a stock-only row already exists,
    it is updated with the content fields (not replaced).
    """
    # Image: download + upload to MinIO (non-fatal if this fails)
    s3_key: str | None = None
    if content.image_url and _WB_IMAGE_CDN_RE.match(content.image_url):
        try:
            proxy = get_proxy_rotator().next()
            image_bytes = asyncio.run(_download_image_async(content.image_url, proxy))
            s3_key = f"org/{org_id}/sku/{sku_id}/wb/main.jpg"
            minio = _get_minio()
            minio.upload(s3_key, image_bytes, "image/jpeg")
        except Exception:  # noqa: BLE001
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
        existing.scraper_level = scraper_level
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
                scraper_level=scraper_level,
                created_at=datetime.now(tz=timezone.utc),
            )
        )


@celery_app.task(
    bind=True,
    max_retries=3,
    name="wb.collect_content",
)
def collect_wb_content(self, sku_platform_id: str) -> None:
    """
    Collect content (title, description, composition, image) for one WB SKUPlatform.

    Delegates to ScraperRouter for adaptive fallback (L0 → L1 → L2).
    Task signature is unchanged for backward compatibility (R-04).

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
                SKUPlatform.platform_id,
                SKU.org_id,
            )
            .join(SKU, SKU.id == SKUPlatform.sku_id)
            .filter(SKUPlatform.id == uuid.UUID(sku_platform_id))
            .first()
        )

    if row is None:
        logger.warning("collect_wb_content: sku_platform %s not found — skipping", sku_platform_id)
        return

    sp_id, sku_id, nm_id, platform_id, org_id = row

    if not nm_id:
        logger.info("collect_wb_content: NO_NM_ID for sku_platform %s — skipping", sku_platform_id)
        return

    with get_db_session() as db:
        router = ScraperRouter(db)
        try:
            content = router.collect(
                platform_id=platform_id,
                sku_id=nm_id,
                data_type=DataType.CONTENT,
                org_id=org_id,
            )
        except ScraperError as exc:
            if exc.code == "NOT_FOUND":
                logger.info(
                    "collect_wb_content: product nm_id=%s not found on WB — skipping", nm_id
                )
                return
            logger.warning("collect_wb_content: ScraperError code=%s nm_id=%s", exc.code, nm_id)
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)

        scraper_level: int | None = getattr(content, "scraper_level", None)
        _save_content_score(db, sp_id, sku_id, org_id, nm_id, content, scraper_level)

    logger.info("collect_wb_content: done nm_id=%s scraper_level=%s", nm_id, scraper_level)
