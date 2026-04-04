"""
Pydantic schemas for the reviews domain.

Sentinel field: sentiment is Optional[str] because reviews scraped before
migration 0009 may have sentiment=NULL (not yet scored by Celery task).
Frontend should handle null as "pending classification".
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel


class ReviewHistoryItem(BaseModel):
    id: UUID
    platform_id: UUID
    platform_name: str
    review_text: str
    rating: int
    sentiment: Optional[Literal["positive", "neutral", "negative"]]
    sentiment_score: Optional[Decimal]
    review_date: date


class ReviewHistoryResponse(BaseModel):
    sku_id: UUID
    total: int
    limit: int
    offset: int
    items: list[ReviewHistoryItem]


class ReviewSummaryItem(BaseModel):
    platform_id: UUID
    platform_name: str
    review_count: int
    avg_rating: Optional[Decimal]
    positive_count: int
    neutral_count: int
    negative_count: int
    positive_pct: Decimal
    neutral_pct: Decimal
    negative_pct: Decimal
    last_review_date: Optional[date]


class ReviewSummaryResponse(BaseModel):
    sku_id: UUID
    date_from: date
    date_to: date
    total: int
    items: list[ReviewSummaryItem]


class SentimentShare(BaseModel):
    positive: Decimal
    neutral: Decimal
    negative: Decimal


class WeeklyTrendItem(BaseModel):
    week_start: date
    positive_share: Decimal
    avg_rating: Optional[Decimal]
    review_count: int


class ReviewStats(BaseModel):
    sku_id: UUID
    date_from: date
    date_to: date
    review_count: int
    avg_rating: Optional[Decimal]
    rating_distribution: dict[str, int]
    sentiment_share: Optional[SentimentShare]
    weekly_trend: list[WeeklyTrendItem]
