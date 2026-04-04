"""
SQLAlchemy ORM model for stock_history table.

Written by the Celery stock collector task.
Read by the dashboard distribution query and stock reports.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, SmallInteger, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


class StockHistory(Base):
    __tablename__ = "stock_history"
    __table_args__ = (
        Index("idx_stock_history_org_sku_platform_week", "org_id", "sku_id", "platform_id", "week_number", "year"),
        Index("idx_stock_history_org_week", "org_id", "week_number", "year"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    sku_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skus.id", ondelete="CASCADE"), nullable=False
    )
    platform_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platforms.id", ondelete="RESTRICT"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    week_number: Mapped[int] = mapped_column(SmallInteger(), nullable=False)
    year: Mapped[int] = mapped_column(SmallInteger(), nullable=False)
    stock_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )
