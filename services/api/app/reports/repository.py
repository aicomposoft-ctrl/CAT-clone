"""
Database queries for the reports domain.

All queries are read-only and MUST be tenant-scoped via skus.org_id.
The content_scores table has no org_id column — isolation is enforced
by joining through sku_platforms → skus.

Query pattern:
  content_scores
    JOIN sku_platforms ON sku_platform_id
    JOIN skus         ON sku_id  (← org_id filter applied here)
    JOIN brands       ON brand_id
    JOIN platforms    ON platform_id
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Brand, Platform, SKU, SKUPlatform
from app.reports.models import ContentScoreRead


@dataclass(slots=True)
class ContentScoreRow:
    """Flat projection used for Excel generation — no lazy-loading issues."""

    brand_name: str
    sku_article: Optional[str]
    sku_name: str
    platform_name: str
    scored_at: date
    image_score: Optional[Decimal]
    description_score: Optional[Decimal]
    composition_score: Optional[Decimal]
    content_total: Optional[Decimal]


async def get_content_scores_for_export(
    db: AsyncSession,
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
    platform_id: Optional[uuid.UUID] = None,
) -> list[ContentScoreRow]:
    """
    Return all content score rows for *org_id* within [date_from, date_to].

    Tenant isolation: SKU.org_id == org_id is the mandatory filter.
    An optional platform_id narrows results to a single platform.

    Ordered by brand name → SKU article → platform name → scored_at for
    deterministic Excel row order.
    """
    stmt = (
        select(
            Brand.name.label("brand_name"),
            SKU.article.label("sku_article"),
            SKU.name.label("sku_name"),
            Platform.name.label("platform_name"),
            ContentScoreRead.scored_at,
            ContentScoreRead.image_score,
            ContentScoreRead.description_score,
            ContentScoreRead.composition_score,
            ContentScoreRead.content_total,
        )
        .join(SKUPlatform, ContentScoreRead.sku_platform_id == SKUPlatform.id)
        .join(SKU, SKUPlatform.sku_id == SKU.id)
        .join(Brand, SKU.brand_id == Brand.id)
        .join(Platform, SKUPlatform.platform_id == Platform.id)
        .where(SKU.org_id == org_id)
        .where(ContentScoreRead.scored_at >= date_from)
        .where(ContentScoreRead.scored_at <= date_to)
        .order_by(
            Brand.name,
            SKU.article.nulls_last(),
            Platform.name,
            ContentScoreRead.scored_at,
        )
    )

    if platform_id is not None:
        stmt = stmt.where(SKUPlatform.platform_id == platform_id)

    result = await db.execute(stmt)
    rows = result.all()

    return [
        ContentScoreRow(
            brand_name=r.brand_name,
            sku_article=r.sku_article,
            sku_name=r.sku_name,
            platform_name=r.platform_name,
            scored_at=r.scored_at,
            image_score=r.image_score,
            description_score=r.description_score,
            composition_score=r.composition_score,
            content_total=r.content_total,
        )
        for r in rows
    ]
