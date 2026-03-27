"""
Celery task: collect content for a Wildberries SKU.

Fetches product title, description, composition, and image from WB card API.
Downloads image and stores it in MinIO (S3). Upserts a content_scores row.

Error handling:
  - NO_NM_ID:  external_id is None → silent skip, no DB write
  - NOT_FOUND: product deleted/invalid → log and return, no DB write
  - RATE_LIMITED / API_UNAVAILABLE / PARSE_ERROR → retry via Celery (max 3)
"""

from __future__ import annotations

import asyncio
import logging
import os
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


@celery_app.task(
    bind=True,
    max_retries=3,
    name="wb.collect_content",
    autoretry_for=(ScraperError,),
    retry_backoff=True,
    retry_backoff_max=30,
)
def collect_wb_content(self, sku_platform_id: str) -> None:
    """
    Collect content (title, description, composition, image) for one WB SKUPlatform.

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
        logger.warning("collect_wb_content: sku_platform %s not found — skipping", sku_platform_id)
        return

    nm_id = sp.external_id
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

    # Download and upload image to MinIO (non-fatal if this fails)
    s3_key: str | None = None
    if content.image_url and _WB_IMAGE_CDN_RE.match(content.image_url):
        try:
            image_bytes = httpx.get(content.image_url, timeout=30.0).content
            s3_key = f"org/{sp.sku.org_id}/sku/{sp.sku_id}/wb/main.jpg"
            minio = _get_minio()
            minio.upload(s3_key, image_bytes, "image/jpeg")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "collect_wb_content: image download/upload failed for nm_id=%s: %s", nm_id, exc
            )
            s3_key = None
    elif content.image_url:
        logger.warning(
            "collect_wb_content: image URL failed SSRF allowlist for nm_id=%s: %s",
            nm_id,
            content.image_url,
        )

    today = date.today()
    with get_db_session() as db:
        existing = (
            db.query(ContentScore)
            .filter(
                ContentScore.sku_platform_id == sp.id,
                ContentScore.scored_at == today,
            )
            .first()
        )

        if existing:
            existing.collected_title = sanitize(content.title, 500)
            existing.collected_description = sanitize(content.description, 5000)
            existing.collected_composition = content.composition
            existing.collected_image_url = s3_key
        else:
            db.add(
                ContentScore(
                    id=uuid.uuid4(),
                    sku_platform_id=sp.id,
                    scored_at=today,
                    collected_title=sanitize(content.title, 500),
                    collected_description=sanitize(content.description, 5000),
                    collected_composition=content.composition,
                    collected_image_url=s3_key,
                    created_at=datetime.now(tz=timezone.utc),
                )
            )

    logger.info(
        "collect_wb_content: done nm_id=%s s3_key=%s", nm_id, s3_key
    )
