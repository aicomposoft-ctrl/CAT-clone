"""Celery task: collect stock availability for a Magnit SKU."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.celery_app import celery_app
from app.core.base_scraper import DataType, ScraperError
from app.core.scraper_router import ScraperRouter
from app.models import ContentScore, SKUPlatform, SKU
from app.tasks._db import get_db_session
from app.tasks._redis import get_redis_client

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, name="magnit.collect_stock")
def collect_magnit_stock(self, sku_platform_id: str) -> None:
    """Collect stock availability for one Magnit SKUPlatform."""
    with get_db_session() as db:
        row = (
            db.query(
                SKUPlatform.id,
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
        logger.warning("collect_magnit_stock: sku_platform %s not found", sku_platform_id)
        return

    sp_id, product_id, page_url, platform_id, org_id = row
    if not product_id:
        return

    now_utc = datetime.now(tz=timezone.utc)
    today = now_utc.date()
    with get_db_session() as db:
        router = ScraperRouter(db, redis_client=get_redis_client())
        try:
            stock_data = router.collect(
                platform_id=platform_id,
                sku_id=product_id,
                data_type=DataType.STOCK,
                org_id=org_id,
                page_url=page_url,
            )
        except ScraperError as exc:
            if exc.code == "NOT_FOUND":
                return
            logger.warning(
                "collect_magnit_stock: ScraperError code=%s sku_platform=%s",
                exc.code, sku_platform_id,
            )
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)

        scraper_level: int | None = getattr(stock_data, "scraper_level", None)
        stmt = (
            pg_insert(ContentScore)
            .values(
                id=uuid.uuid4(),
                sku_platform_id=sp_id,
                scored_at=today,
                in_stock=stock_data.in_stock,
                warehouse_qty=stock_data.total_qty,
                scraper_level=scraper_level,
                created_at=now_utc,
            )
            .on_conflict_do_update(
                constraint="uq_content_scores_sp_date",
                set_={
                    "in_stock": stock_data.in_stock,
                    "warehouse_qty": stock_data.total_qty,
                    "scraper_level": scraper_level,
                },
            )
        )
        db.execute(stmt)

    logger.info(
        "collect_magnit_stock: done sku_platform=%s scraper_level=%s",
        sku_platform_id, scraper_level,
    )
