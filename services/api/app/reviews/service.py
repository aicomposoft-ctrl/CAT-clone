"""
Business logic for the reviews domain.

Responsibilities:
  - Date range validation and defaults
  - Delegation to repository
  - Schema mapping (percentage calculations, nullability contracts)

No SQLAlchemy sessions created here; db is injected from router.
No HTTP concerns (no HTTPException raised here).

validate_date_range is intentionally duplicated from the prices domain (same logic).
This avoids cross-domain coupling for a 3-line utility. Candidate for app.core.utils
in a future refactor.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.reviews import repository
from app.reviews.schemas import (
    ReviewHistoryItem,
    ReviewHistoryResponse,
    ReviewStats,
    ReviewSummaryItem,
    ReviewSummaryResponse,
    SentimentShare,
    WeeklyTrendItem,
)


def validate_date_range(
    date_from: date | None,
    date_to: date | None,
    default_days_back: int = 30,
    max_range_days: int = 366,
) -> tuple[date, date]:
    """
    Apply defaults and validate the date range.

    Raises ValueError with a human-readable message on invalid input.
    The router catches ValueError and converts to HTTP 422.
    Called from the router layer; service functions receive already-validated dates.
    """
    today = date.today()

    if date_from is None:
        date_from = today - timedelta(days=default_days_back)
    if date_to is None:
        date_to = today

    if date_from > date_to:
        raise ValueError("date_from must be before date_to")

    if (date_to - date_from).days > max_range_days:
        raise ValueError(f"Date range cannot exceed {max_range_days} days")

    return date_from, date_to


async def get_review_summary(
    db: AsyncSession,
    org_id: UUID,
    sku_id: UUID,
    date_from: date,
    date_to: date,
) -> ReviewSummaryResponse:
    rows = await repository.fetch_summary(
        db=db, org_id=org_id, sku_id=sku_id, date_from=date_from, date_to=date_to
    )

    items = []
    for row in rows:
        denom = row.review_count if row.review_count > 0 else 1
        positive_pct = Decimal(str(round(row.positive_count / denom * 100, 1)))
        neutral_pct = Decimal(str(round(row.neutral_count / denom * 100, 1)))
        # Subtract to avoid rounding drift exceeding 100%
        negative_pct = Decimal(str(max(0, round(100.0 - float(positive_pct) - float(neutral_pct), 1))))

        items.append(ReviewSummaryItem(
            platform_id=row.platform_id,
            platform_name=row.platform_name,
            review_count=row.review_count,
            avg_rating=Decimal(str(row.avg_rating)) if row.avg_rating is not None else None,
            positive_count=row.positive_count,
            neutral_count=row.neutral_count,
            negative_count=row.negative_count,
            positive_pct=positive_pct,
            neutral_pct=neutral_pct,
            negative_pct=negative_pct,
            last_review_date=row.last_review_date,
        ))

    total = sum(item.review_count for item in items)
    return ReviewSummaryResponse(
        sku_id=sku_id,
        date_from=date_from,
        date_to=date_to,
        total=total,
        items=items,
    )


async def get_review_history(
    db: AsyncSession,
    org_id: UUID,
    sku_id: UUID,
    platform_id: UUID | None,
    sentiment: str | None,
    date_from: date,
    date_to: date,
    limit: int,
    offset: int,
) -> ReviewHistoryResponse:
    rows = await repository.fetch_history(
        db=db,
        org_id=org_id,
        sku_id=sku_id,
        platform_id=platform_id,
        sentiment=sentiment,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )

    items = [
        ReviewHistoryItem(
            id=row.id,
            platform_id=row.platform_id,
            platform_name=row.platform_name,
            review_text=row.review_text,
            rating=row.rating,
            sentiment=row.sentiment,
            sentiment_score=Decimal(str(row.sentiment_score)) if row.sentiment_score is not None else None,
            review_date=row.review_date,
        )
        for row in rows
    ]
    return ReviewHistoryResponse(
        sku_id=sku_id,
        total=len(items),
        limit=limit,
        offset=offset,
        items=items,
    )


async def get_review_stats(
    db: AsyncSession,
    org_id: UUID,
    sku_id: UUID,
    date_from: date,
    date_to: date,
) -> ReviewStats:
    row = await repository.fetch_stats(
        db=db, org_id=org_id, sku_id=sku_id, date_from=date_from, date_to=date_to
    )

    if row is None:
        return ReviewStats(
            sku_id=sku_id,
            date_from=date_from,
            date_to=date_to,
            review_count=0,
            avg_rating=None,
            rating_distribution={"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
            sentiment_share=None,
            weekly_trend=[],
        )

    rating_distribution = {
        "1": int(row.r1 or 0),
        "2": int(row.r2 or 0),
        "3": int(row.r3 or 0),
        "4": int(row.r4 or 0),
        "5": int(row.r5 or 0),
    }

    sentiment_share = None
    if row.positive_share is not None:
        sentiment_share = SentimentShare(
            positive=Decimal(str(row.positive_share)),
            neutral=Decimal(str(row.neutral_share)),
            negative=Decimal(str(row.negative_share)),
        )

    weekly_trend = [
        WeeklyTrendItem(
            week_start=item["week_start"],
            positive_share=Decimal(str(item["positive_share"] or 0)),
            avg_rating=Decimal(str(item["avg_rating"])) if item.get("avg_rating") is not None else None,
            review_count=int(item["review_count"]),
        )
        for item in (row.weekly_trend or [])
    ]

    return ReviewStats(
        sku_id=sku_id,
        date_from=date_from,
        date_to=date_to,
        review_count=int(row.review_count),
        avg_rating=Decimal(str(row.avg_rating)) if row.avg_rating is not None else None,
        rating_distribution=rating_distribution,
        sentiment_share=sentiment_share,
        weekly_trend=weekly_trend,
    )
