"""
ORM model for the reviews table.

The table was created in migration 0003. Migration 0009 added:
  - sentiment VARCHAR(20) CHECK (positive|neutral|negative) nullable
  - sentiment_score DECIMAL(4,3) nullable

extend_existing=True prevents InvalidRequestError when SQLAlchemy encounters
an already-mapped table (e.g. processor service also imports this model).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint(
            "sentiment IN ('positive', 'neutral', 'negative')",
            name="ck_reviews_sentiment",
        ),
        {"extend_existing": True},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    sku_platform_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sku_platforms.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_review_id: Mapped[str] = mapped_column(String(255), nullable=False)
    review_text: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    review_date: Mapped[date] = mapped_column(Date, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Added by migration 0009:
    sentiment: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sentiment_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
