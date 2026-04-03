"""
Business logic for the prices domain.

Responsibilities:
  - Date range validation and defaults
  - Delegation to repository
  - Schema mapping

No SQLAlchemy sessions created here; db is injected from router.
No HTTP concerns (no HTTPException raised here).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.prices import repository
from app.prices.schemas import (
    PriceAnomaly,
    PriceAnomaliesResponse,
    PriceHistoryItem,
    PriceHistoryResponse,
    PriceLatestItem,
    PriceLatestResponse,
    PriceStats,
)


def _validate_date_range(
    date_from: date | None,
    date_to: date | None,
    default_days_back: int = 30,
    max_range_days: int = 366,
) -> tuple[date, date]:
    """
    Apply defaults and validate the date range.

    Raises ValueError with a human-readable message on invalid input.
    The router catches ValueError and converts to HTTP 422.
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


async def get_price_history(
    db: AsyncSession,
    org_id: UUID,
    sku_id: UUID,
    platform_id: UUID | None,
    date_from: date | None,
    date_to: date | None,
    limit: int,
) -> PriceHistoryResponse:
    date_from, date_to = _validate_date_range(date_from, date_to)

    rows = await repository.fetch_history(
        db=db,
        org_id=org_id,
        sku_id=sku_id,
        platform_id=platform_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )

    items = [
        PriceHistoryItem(
            id=row.id,
            platform_id=row.platform_id,
            platform_name=row.platform_name,
            price=row.price,
            original_price=row.original_price,
            discount_pct=row.discount_pct,
            promo_label=row.promo_label,
            collected_at=row.collected_at,
        )
        for row in rows
    ]
    return PriceHistoryResponse(sku_id=sku_id, items=items, total=len(items))


async def get_latest_prices(
    db: AsyncSession,
    org_id: UUID,
    sku_id: UUID,
) -> PriceLatestResponse:
    rows = await repository.fetch_latest(db=db, org_id=org_id, sku_id=sku_id)

    if not rows:
        return PriceLatestResponse(
            sku_id=sku_id, cheapest_platform_id=None, items=[]
        )

    # Sort by price ASC for display; cheapest = minimum price row
    sorted_rows = sorted(rows, key=lambda r: r.price)
    cheapest_platform_id = sorted_rows[0].platform_id

    items = [
        PriceLatestItem(
            platform_id=row.platform_id,
            platform_name=row.platform_name,
            price=row.price,
            original_price=row.original_price,
            discount_pct=row.discount_pct,
            promo_label=row.promo_label,
            collected_at=row.collected_at,
        )
        for row in sorted_rows
    ]
    return PriceLatestResponse(
        sku_id=sku_id,
        cheapest_platform_id=cheapest_platform_id,
        items=items,
    )


async def get_price_stats(
    db: AsyncSession,
    org_id: UUID,
    sku_id: UUID,
    platform_id: UUID | None,
    date_from: date | None,
    date_to: date | None,
) -> PriceStats:
    date_from, date_to = _validate_date_range(date_from, date_to)

    row = await repository.fetch_stats(
        db=db,
        org_id=org_id,
        sku_id=sku_id,
        platform_id=platform_id,
        date_from=date_from,
        date_to=date_to,
    )

    if row is None:
        return PriceStats(
            sku_id=sku_id,
            platform_id=platform_id,
            date_from=date_from,
            date_to=date_to,
            snapshot_count=0,
            price_min=None,
            price_max=None,
            price_avg=None,
            price_median=None,
            first_price=None,
            last_price=None,
            change_abs=None,
            change_pct=None,
            discount_avg=None,
        )

    first = Decimal(str(row.first_price))
    last = Decimal(str(row.last_price))
    change_abs = (last - first).quantize(Decimal("0.01"))
    change_pct = (
        (change_abs / first * 100).quantize(Decimal("0.01"))
        if first != 0
        else None
    )

    return PriceStats(
        sku_id=sku_id,
        platform_id=platform_id,
        date_from=date_from,
        date_to=date_to,
        snapshot_count=int(row.snapshot_count),
        price_min=Decimal(str(row.price_min)),
        price_max=Decimal(str(row.price_max)),
        price_avg=Decimal(str(row.price_avg)),
        price_median=Decimal(str(row.price_median)),
        first_price=first,
        last_price=last,
        change_abs=change_abs,
        change_pct=change_pct,
        discount_avg=Decimal(str(row.discount_avg)),
    )


async def get_price_anomalies(
    db: AsyncSession,
    org_id: UUID,
    sku_id: UUID,
    platform_id: UUID | None,
    date_from: date | None,
    date_to: date | None,
    threshold: float,
    direction: str,
) -> PriceAnomaliesResponse:
    date_from, date_to = _validate_date_range(date_from, date_to)

    rows = await repository.fetch_anomalies(
        db=db,
        org_id=org_id,
        sku_id=sku_id,
        platform_id=platform_id,
        date_from=date_from,
        date_to=date_to,
        threshold=threshold,
        direction=direction,
    )

    items = [
        PriceAnomaly(
            platform_id=row.platform_id,
            platform_name=row.platform_name,
            date=row.date,
            price_before=Decimal(str(row.price_before)),
            price_after=Decimal(str(row.price_after)),
            change_abs=Decimal(str(row.change_abs)),
            change_pct=Decimal(str(row.change_pct)),
            direction="down" if row.change_pct < 0 else "up",
        )
        for row in rows
    ]
    return PriceAnomaliesResponse(
        sku_id=sku_id, threshold=threshold, items=items
    )
