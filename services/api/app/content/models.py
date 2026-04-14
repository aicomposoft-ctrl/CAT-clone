"""
SQLAlchemy ORM model for content_scores table.

The table is written by the Celery collector+processor pipeline and read
by the API for dashboard, reports, and drill-down views.

Multi-tenant isolation:
  content_scores has no direct org_id column. Tenant scoping is enforced
  via JOIN: content_scores → sku_platforms → skus → skus.org_id.
  All repository queries embed this JOIN as defence-in-depth.
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


class ContentScore(Base):
    """
    Daily content score snapshot for a (SKU, platform) pair.

    image_score     — CLIP cosine similarity of collected vs reference image
    description_score — multilingual-e5 cosine similarity of descriptions
    composition_score — multilingual-e5 cosine similarity of compositions
    content_total   — weighted aggregate: 0.40×image + 0.35×desc + 0.25×comp
    """

    __tablename__ = "content_scores"
    __table_args__ = (
        UniqueConstraint("sku_platform_id", "scored_at", name="uq_content_scores_sp_date"),
        Index("idx_content_scores_sp", "sku_platform_id"),
        Index("idx_content_scores_date", "scored_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    sku_platform_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sku_platforms.id", ondelete="CASCADE"),
        nullable=False,
    )
    scored_at: Mapped[date] = mapped_column(Date(), nullable=False)

    # Collected content fields
    collected_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    collected_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    collected_composition: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    collected_image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Stock fields (populated by stock task, optional on content rows)
    in_stock: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    warehouse_qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ML scores (populated by processor service)
    image_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    description_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    composition_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    content_total: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )

    def __repr__(self) -> str:
        return (
            f"<ContentScore sp={self.sku_platform_id} date={self.scored_at} "
            f"total={self.content_total}>"
        )
