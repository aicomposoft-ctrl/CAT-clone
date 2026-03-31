"""
Synchronous SQLAlchemy ORM models for the processor service.

Maps to the same PostgreSQL tables as the API and collector services.
Uses a separate Base — no inheritance from the API's AsyncBase.

Models:
  SKU          — resolves org_id (read-only)
  SKUPlatform  — resolves sku_id from content_scores (read-only)
  ContentScore — target of image_score UPDATE
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SKU(Base):
    __tablename__ = "skus"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)


class SKUPlatform(Base):
    __tablename__ = "sku_platforms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    sku_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skus.id"), nullable=False
    )
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_monitored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ContentScore(Base):
    __tablename__ = "content_scores"
    __table_args__ = (
        UniqueConstraint("sku_platform_id", "scored_at", name="uq_content_scores_sp_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    sku_platform_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sku_platforms.id"), nullable=False
    )
    scored_at: Mapped[date] = mapped_column(Date(), nullable=False)
    collected_image_url: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    image_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
