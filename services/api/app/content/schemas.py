"""Pydantic schemas for the content scores domain."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class ContentScoreItem(BaseModel):
    """Single row in the content scores table."""

    id: uuid.UUID
    sku_platform_id: uuid.UUID
    sku_id: uuid.UUID
    sku_name: str
    article: Optional[str]
    brand_id: uuid.UUID
    brand_name: str
    platform_id: uuid.UUID
    platform_name: str
    platform_url: Optional[str]

    scored_at: date
    content_total: Optional[Decimal]
    image_score: Optional[Decimal]
    description_score: Optional[Decimal]
    composition_score: Optional[Decimal]

    collected_image_url: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ContentScorePage(BaseModel):
    items: list[ContentScoreItem]
    total: int
    page: int
    size: int


class ContentScoreHistory(BaseModel):
    scored_at: date
    content_total: Optional[Decimal]


class ContentScoreDrilldown(ContentScoreItem):
    """Drill-down view: adds reference material for side-by-side comparison."""

    collected_description: Optional[str]
    collected_composition: Optional[str]
    collected_title: Optional[str]

    # Reference material from SKU
    reference_image_url: Optional[str]
    reference_description: Optional[str]
    reference_composition: Optional[str]

    history: list[ContentScoreHistory]
