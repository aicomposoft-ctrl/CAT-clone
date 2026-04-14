"""
ORM model for the price_snapshots table.

The table is created in migration 0003 and written exclusively by the
collector service (Celery tasks). This module provides a read-only ORM
mapping used by the prices domain for analytics queries.

extend_existing=True prevents InvalidRequestError if another module ever
imports the same table name via SQLAlchemy's shared metadata.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PriceSnapshot(Base):
    """
    Append-only time series of price checks per SKU × platform.

    Tenant isolation: no org_id column on this table.
    All queries must JOIN through sku_platforms → skus.org_id.
    """

    __tablename__ = "price_snapshots"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    sku_platform_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sku_platforms.id", ondelete="CASCADE"),
        nullable=False,
    )
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    original_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    discount_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    promo_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
