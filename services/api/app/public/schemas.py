"""
Public-facing response schemas for the /api/v1/public/* endpoints.

These schemas are intentionally simpler than internal domain schemas:
  - No internal IDs (config_id, sku_platform_id, etc.)
  - No sensitive operational fields
  - Stable field names for external API consumers (Power BI, 3rd-party integrations)

All schemas use ConfigDict(from_attributes=True) for ORM → schema conversion via
model_validate(). Numeric scores are float (not Decimal) for JSON serialisation
convenience — precision loss is acceptable at 2 decimal places.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# SKU + Content Score schemas
# ---------------------------------------------------------------------------


class PublicSKUItem(BaseModel):
    """
    A single SKU with its latest aggregated content score.

    content_total / image_score / description_score / completeness_score are None
    when no score has been computed yet (newly added SKU or processor lag).

    platform_count: number of distinct platforms this SKU is monitored on.
    """

    model_config = ConfigDict(from_attributes=True)

    sku_id: uuid.UUID
    sku_name: str
    external_id: Optional[str]
    brand_name: str
    content_total: Optional[float]
    image_score: Optional[float]
    description_score: Optional[float]
    completeness_score: Optional[float]
    scored_at: Optional[datetime]
    platform_count: int


class PublicSKUListResponse(BaseModel):
    """Paginated response for GET /public/skus."""

    model_config = ConfigDict(from_attributes=True)

    items: list[PublicSKUItem]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Stock schemas
# ---------------------------------------------------------------------------


class PublicStockItem(BaseModel):
    """
    Stock status for a single (SKU × platform) pair.

    in_stock: True = product is available, False = out-of-stock.
    stock_status: optional human-readable status string from the platform.
    last_checked_at: timestamp of the most recent stock check.
    """

    model_config = ConfigDict(from_attributes=True)

    sku_id: uuid.UUID
    sku_name: str
    platform_id: uuid.UUID
    platform_name: str
    in_stock: bool
    stock_status: Optional[str]
    last_checked_at: Optional[datetime]


class PublicStockResponse(BaseModel):
    """Paginated response for GET /public/stock."""

    model_config = ConfigDict(from_attributes=True)

    items: list[PublicStockItem]
    total: int


# ---------------------------------------------------------------------------
# Price schemas
# ---------------------------------------------------------------------------


class PublicPriceItem(BaseModel):
    """
    Latest price snapshot for a single (SKU × platform) pair.

    price: current selling price (may be None if not yet scraped).
    currency: ISO 4217 currency code (e.g. "RUB").
    discount_pct: percentage discount from original_price (0–100).
    snapshot_at: timestamp when this price was collected.
    """

    model_config = ConfigDict(from_attributes=True)

    sku_id: uuid.UUID
    sku_name: str
    platform_id: uuid.UUID
    platform_name: str
    price: Optional[float]
    currency: str
    discount_pct: Optional[float]
    snapshot_at: Optional[datetime]


class PublicPriceResponse(BaseModel):
    """Response for GET /public/prices."""

    model_config = ConfigDict(from_attributes=True)

    items: list[PublicPriceItem]
    total: int


# ---------------------------------------------------------------------------
# Reviews summary schemas
# ---------------------------------------------------------------------------


class PublicReviewsSummary(BaseModel):
    """
    Aggregated sentiment summary for a single brand.

    Percentages sum to 100 (within floating-point precision).
    All percentage fields are None when no reviews exist.
    """

    model_config = ConfigDict(from_attributes=True)

    brand_id: uuid.UUID
    brand_name: str
    total_reviews: int
    avg_rating: Optional[float]
    positive_pct: Optional[float]
    negative_pct: Optional[float]
    neutral_pct: Optional[float]


class PublicReviewsSummaryResponse(BaseModel):
    """Response for GET /public/reviews/summary."""

    model_config = ConfigDict(from_attributes=True)

    items: list[PublicReviewsSummary]


# ---------------------------------------------------------------------------
# Alert schemas
# ---------------------------------------------------------------------------


class PublicAlertItem(BaseModel):
    """
    A single triggered alert event.

    sku_id / sku_name / platform_name may be None when the alert config
    applies org-wide (no specific SKU or platform scoped).

    severity: derived from alert_type — "critical" for content_drop, "warning" for oos.
    message: human-readable summary of what triggered the alert.
    """

    model_config = ConfigDict(from_attributes=True)

    alert_id: uuid.UUID
    alert_type: str
    sku_id: Optional[uuid.UUID]
    sku_name: Optional[str]
    platform_name: Optional[str]
    severity: str
    message: str
    triggered_at: datetime


class PublicAlertResponse(BaseModel):
    """Response for GET /public/alerts."""

    model_config = ConfigDict(from_attributes=True)

    items: list[PublicAlertItem]
    total: int
