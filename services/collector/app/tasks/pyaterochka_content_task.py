"""
Celery task: collect content for a Pyaterochka SKU.

Fetches product title, description, composition, and image from the 5ka.ru
API (`GET /api/v1/products/{plu}/`).  Downloads the main product image
asynchronously via proxy and stores it in MinIO (S3).  Upserts a
content_scores row using INSERT ... ON CONFLICT DO UPDATE.
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
from app.scrapers.pyaterochka import _download_image_async
from app.tasks._db import get_db_session
from app.tasks._redis import get_redis_client
from app.tasks._retry_policy import should_retry_scrape_error

logger = logging.getLogger(__name__)


def _get_minio():
    from app.core.minio_client import MinioClient  # noqa: PLC0415
    return MinioClient()


@celery_app.task(
    bind=True,
    max_retries=3,
    name="pyaterochka.collect_content",
)
def collect_pyaterochka_content(self, sku_platform_id: str) -> None:
    """Collect content (title, description, composition, image) for one Pyaterochka SKUPlatform."""
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
            "collect_pyaterochka_content: sku_platform %s not found — skipping",
            sku_platform_id,
        )
        return

    sp_id, sku_id, product_id, page_url, platform_id, org_id = row

    if not product_id:
        logger.info(
            "collect_pyaterochka_content: NO_PRODUCT_ID for sku_platform %s — skipping",
            sku_platform_id,
        )
        return

    with get_db_session() as db:
        router = ScraperRouter(db, redis_client=get_redis_client())
        try:
            content = router.collect(
                platform_id=platform_id,
                sku_id=product_id,
                data_type=DataType.CONTENT,
                org_id=org_id,
                page_url=page_url,
            )
        except ScraperError as exc:
            if exc.code == "NOT_FOUND":
                logger.info(
                    "collect_pyaterochka_content: product sku_platform=%s not found — skipping",
                    sku_platform_id,
                )
                return
            logger.warning(
                "collect_pyaterochka_content: ScraperError code=%s sku_platform=%s",
                exc.code, sku_platform_id,
            )
            if not should_retry_scrape_error(exc):
                raise
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)
        scraper_level: int | None = getattr(content, "scraper_level", None)

    logger.info(
        "collect_pyaterochka_content: scraped sku_platform=%s title_len=%d desc_len=%d image_url=%r",
        sku_platform_id,
        len(content.title or ""),
        len(content.description or ""),
        content.image_url,
    )

    async def _fetch_image():
        img: bytes | None = None
        if content.image_url:
            try:
                img = await _download_image_async(content.image_url, get_proxy_rotator().next())
            except ValueError as exc:
                logger.warning("collect_pyaterochka_content: image SSRF reject sku_platform=%s: %s", sku_platform_id, exc)
            except Exception as exc:  # noqa: BLE001
                logger.warning("collect_pyaterochka_content: image download failed sku_platform=%s: %s", sku_platform_id, exc)
        return img

    try:
        image_bytes = asyncio.run(_fetch_image())
    except Exception:  # noqa: BLE001
        image_bytes = None

    s3_key: str | None = None
    if image_bytes is not None:
        try:
            s3_key = f"org/{org_id}/sku/{sku_id}/pyaterochka/main.jpg"
            minio = _get_minio()
            minio.upload(s3_key, image_bytes, "image/jpeg")
        except Exception:  # noqa: BLE001
            logger.warning(
                "collect_pyaterochka_content: MinIO upload failed for sku_platform=%s",
                sku_platform_id, exc_info=True,
            )
            s3_key = None
    elif content.image_url:
        logger.warning(
            "collect_pyaterochka_content: image download failed for sku_platform=%s",
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
        "collect_pyaterochka_content: done sku_platform=%s scraper_level=%s",
        sku_platform_id, scraper_level,
    )
