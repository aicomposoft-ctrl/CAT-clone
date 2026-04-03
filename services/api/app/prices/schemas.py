"""
Pydantic request/response schemas for the prices domain.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class PriceHistoryItem(BaseModel):
    id: UUID
    platform_id: UUID
    platform_name: str
    price: Decimal
    original_price: Decimal
    discount_pct: Decimal
    promo_label: str | None
    collected_at: datetime

    model_config = {"from_attributes": True}


class PriceHistoryResponse(BaseModel):
    sku_id: UUID
    items: list[PriceHistoryItem]
    total: int


class PriceLatestItem(BaseModel):
    platform_id: UUID
    platform_name: str
    price: Decimal
    original_price: Decimal
    discount_pct: Decimal
    promo_label: str | None
    collected_at: datetime

    model_config = {"from_attributes": True}


class PriceLatestResponse(BaseModel):
    sku_id: UUID
    cheapest_platform_id: UUID | None
    items: list[PriceLatestItem]


class PriceStats(BaseModel):
    sku_id: UUID
    platform_id: UUID | None
    date_from: date
    date_to: date
    snapshot_count: int
    price_min: Decimal | None
    price_max: Decimal | None
    price_avg: Decimal | None
    price_median: Decimal | None
    first_price: Decimal | None
    last_price: Decimal | None
    change_abs: Decimal | None
    change_pct: Decimal | None
    discount_avg: Decimal | None


class PriceAnomaly(BaseModel):
    platform_id: UUID
    platform_name: str
    date: date
    price_before: Decimal
    price_after: Decimal
    change_abs: Decimal
    change_pct: Decimal
    direction: Literal["up", "down"]


class PriceAnomaliesResponse(BaseModel):
    sku_id: UUID
    threshold: float
    items: list[PriceAnomaly]
