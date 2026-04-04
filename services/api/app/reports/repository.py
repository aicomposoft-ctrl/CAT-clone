"""
Database queries for the reports domain.

All queries are read-only and MUST be tenant-scoped via skus.org_id.
The content_scores and reviews tables have no org_id column — isolation is
enforced by joining through sku_platforms → skus.

Query patterns:
  content_scores
    JOIN sku_platforms ON sku_platform_id
    JOIN skus         ON sku_id  (← org_id filter applied here)
    JOIN brands       ON brand_id
    JOIN platforms    ON platform_id

  stock export additionally:
    LEFT JOIN distribution_plans ON sku_id + platform_id + week_number + year
    (week extracted from scored_at via func.extract — PostgreSQL/SQLite compatible)

  reviews export:
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

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Brand, Platform, SKU, SKUPlatform
from app.reports.models import ContentScoreRead
from app.stock.models import DistributionPlan as DistributionPlanRead


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


@dataclass(slots=True)
class StockRow:
    """Flat projection for the stock Excel export — plan vs fact per SKU×Platform×day."""

    brand_name: str
    sku_article: Optional[str]
    sku_name: str
    platform_name: str
    scored_at: date
    week_number: int
    year: int
    in_stock: Optional[bool]
    warehouse_qty: Optional[int]
    plan_tt_count: Optional[int]   # NULL when no distribution plan for this week


async def get_stock_data_for_export(
    db: AsyncSession,
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
    platform_id: Optional[uuid.UUID] = None,
) -> list[StockRow]:
    """
    Return stock fact rows (in_stock / warehouse_qty) for *org_id* within
    [date_from, date_to], LEFT JOINed with the matching distribution plan for
    the same ISO week.

    Only rows where in_stock IS NOT NULL are included — rows populated solely
    by the ML scorer (no stock task run yet) are excluded.

    Tenant isolation: SKU.org_id == org_id mandatory, enforced via JOIN.

    The week/year match uses func.extract so the query is compatible with
    both PostgreSQL (production) and SQLite (tests).  PostgreSQL uses
    extract('week'/'year'), SQLite uses strftime('%W'/'%Y').
    """
    week_of_scored_at = func.extract("week", ContentScoreRead.scored_at).label("week_num")
    year_of_scored_at = func.extract("year", ContentScoreRead.scored_at).label("year_num")

    stmt = (
        select(
            Brand.name.label("brand_name"),
            SKU.article.label("sku_article"),
            SKU.name.label("sku_name"),
            Platform.name.label("platform_name"),
            ContentScoreRead.scored_at,
            week_of_scored_at,
            year_of_scored_at,
            ContentScoreRead.in_stock,
            ContentScoreRead.warehouse_qty,
            DistributionPlanRead.plan_tt_count,
        )
        .join(SKUPlatform, ContentScoreRead.sku_platform_id == SKUPlatform.id)
        .join(SKU, SKUPlatform.sku_id == SKU.id)
        .join(Brand, SKU.brand_id == Brand.id)
        .join(Platform, SKUPlatform.platform_id == Platform.id)
        .outerjoin(
            DistributionPlanRead,
            (DistributionPlanRead.sku_id == SKU.id)
            & (DistributionPlanRead.platform_id == SKUPlatform.platform_id)
            & (DistributionPlanRead.week_number == func.extract("week", ContentScoreRead.scored_at))
            & (DistributionPlanRead.year == func.extract("year", ContentScoreRead.scored_at)),
        )
        .where(SKU.org_id == org_id)
        .where(ContentScoreRead.scored_at >= date_from)
        .where(ContentScoreRead.scored_at <= date_to)
        .where(ContentScoreRead.in_stock.is_not(None))
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
        StockRow(
            brand_name=r.brand_name,
            sku_article=r.sku_article,
            sku_name=r.sku_name,
            platform_name=r.platform_name,
            scored_at=r.scored_at,
            week_number=int(r.week_num),
            year=int(r.year_num),
            in_stock=r.in_stock,
            warehouse_qty=r.warehouse_qty,
            plan_tt_count=r.plan_tt_count,
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Reviews export
# ---------------------------------------------------------------------------

_ROW_LIMIT = 10_000


@dataclass(slots=True)
class ReviewRow:
    """Flat projection for the reviews Excel export."""

    brand_name: str
    sku_article: Optional[str]
    sku_name: str
    platform_name: str
    review_date: date
    rating: Optional[int]
    sentiment: Optional[str]
    sentiment_score: Optional[Decimal]
    review_text: Optional[str]


async def get_reviews_for_export(
    db: AsyncSession,
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
    platform_id: Optional[uuid.UUID] = None,
    sentiment: Optional[str] = None,
    sku_id: Optional[uuid.UUID] = None,
) -> tuple[list[ReviewRow], bool]:
    """
    Return reviews for *org_id* within [date_from, date_to].

    Returns (rows, truncated).
      rows      — up to _ROW_LIMIT rows (10,000)
      truncated — True when result exceeds _ROW_LIMIT; caller appends warning row

    Tenant isolation: SKU.org_id == org_id is the mandatory filter, applied via JOIN.
    """
    # Local import: app.reviews.models is not imported at module level to avoid
    # a circular dependency (reports → reviews → core → reports).
    from app.reviews.models import Review

    stmt = (
        select(
            Brand.name.label("brand_name"),
            SKU.article.label("sku_article"),
            SKU.name.label("sku_name"),
            Platform.name.label("platform_name"),
            Review.review_date,
            Review.rating,
            Review.sentiment,
            Review.sentiment_score,
            Review.review_text,
        )
        .join(SKUPlatform, Review.sku_platform_id == SKUPlatform.id)
        .join(SKU, SKUPlatform.sku_id == SKU.id)
        .join(Brand, SKU.brand_id == Brand.id)
        .join(Platform, SKUPlatform.platform_id == Platform.id)
        .where(SKU.org_id == org_id)
        .where(Review.review_date >= date_from)
        .where(Review.review_date <= date_to)
        .order_by(
            Brand.name,
            SKU.article.nulls_last(),
            Platform.name,
            Review.review_date.desc(),
        )
    )

    # Apply optional filters BEFORE limit — prevents incorrect truncation detection
    if platform_id is not None:
        stmt = stmt.where(SKUPlatform.platform_id == platform_id)
    if sentiment is not None:
        stmt = stmt.where(Review.sentiment == sentiment)
    if sku_id is not None:
        stmt = stmt.where(SKU.id == sku_id)

    # Fetch one extra row to detect whether the result exceeds the cap
    stmt = stmt.limit(_ROW_LIMIT + 1)

    result = await db.execute(stmt)
    raw = result.all()

    truncated = len(raw) > _ROW_LIMIT
    rows = raw[:_ROW_LIMIT]

    return (
        [
            ReviewRow(
                brand_name=r.brand_name,
                sku_article=r.sku_article,
                sku_name=r.sku_name,
                platform_name=r.platform_name,
                review_date=r.review_date,
                rating=r.rating,
                sentiment=r.sentiment,
                sentiment_score=Decimal(str(r.sentiment_score)) if r.sentiment_score is not None else None,
                review_text=r.review_text,
            )
            for r in rows
        ],
        truncated,
    )
