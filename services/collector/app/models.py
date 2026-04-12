"""
Synchronous SQLAlchemy ORM models for Celery collector tasks.

These models map to the same PostgreSQL tables as the API service but use
the sync session factory from tasks/_db.py. No inheritance from the API's
AsyncBase — separate Base declared here for the collector process.

Models defined here:
  - SKU          (read-only — needed to resolve org_id from sku_platform)
  - SKUPlatform  (read — source of nm_id / external_id)
  - ContentScore (upsert — content + stock tasks)
  - PriceSnapshot (insert — price task)
  - Review        (insert on conflict do nothing — reviews task)
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Platform(Base):
    __tablename__ = "platforms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SKU(Base):
    __tablename__ = "skus"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)

    sku_platforms: Mapped[list["SKUPlatform"]] = relationship(
        "SKUPlatform", back_populates="sku", lazy="select"
    )


class SKUPlatform(Base):
    __tablename__ = "sku_platforms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    sku_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skus.id", ondelete="CASCADE"), nullable=False
    )
    platform_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_monitored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    sku: Mapped["SKU"] = relationship("SKU", back_populates="sku_platforms", lazy="select")


class ContentScore(Base):
    __tablename__ = "content_scores"
    __table_args__ = (
        UniqueConstraint("sku_platform_id", "scored_at", name="uq_content_scores_sp_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    sku_platform_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sku_platforms.id", ondelete="CASCADE"), nullable=False
    )
    scored_at: Mapped[date] = mapped_column(Date(), nullable=False)
    # Content fields — populated by content task
    collected_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    collected_description: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    collected_composition: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    collected_image_url: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    # Stock fields — populated by stock task (partial-row contract)
    in_stock: Mapped[Optional[bool]] = mapped_column(Boolean(), nullable=True)
    warehouse_qty: Mapped[Optional[int]] = mapped_column(Integer(), nullable=True)
    # ML scoring fields — populated by processor service
    image_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    description_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    composition_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    content_total: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    sku_platform_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sku_platforms.id", ondelete="CASCADE"), nullable=False
    )
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    original_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    discount_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    promo_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("sku_platform_id", "external_review_id", name="uq_reviews_sp_ext_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    sku_platform_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sku_platforms.id", ondelete="CASCADE"), nullable=False
    )
    external_review_id: Mapped[str] = mapped_column(String(255), nullable=False)
    review_text: Mapped[str] = mapped_column(Text(), nullable=False)
    rating: Mapped[int] = mapped_column(SmallInteger(), nullable=False)
    review_date: Mapped[date] = mapped_column(Date(), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OrgPlatformCredentials(Base):
    """
    Per-organisation credentials for a specific platform.

    Stores encrypted API tokens and scraper fallback configuration.
    Always filtered by org_id — never queried globally.
    """

    __tablename__ = "org_platform_credentials"
    __table_args__ = (
        UniqueConstraint("org_id", "platform_id", name="uq_org_platform_creds"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    platform_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platforms.id", ondelete="CASCADE"), nullable=False
    )
    # Fernet-encrypted token value; None means no API token available
    api_token_encrypted: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    # Identifies which L0 scraper class handles this token type (e.g. "wb_seller")
    api_token_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Optional override of the default fallback chain, e.g. ["l0", "l1", "l2"]
    fallback_chain: Mapped[Optional[dict]] = mapped_column(JSON(), nullable=True)
    # Optional per-org CSS/XPath selector overrides for L1 scrapers
    selectors: Mapped[Optional[dict]] = mapped_column(JSON(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
