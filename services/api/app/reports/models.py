"""
SQLAlchemy ORM models for the reports domain (read-only).

These models map to tables owned by other domains but are referenced here
for JOIN queries in the reports repository.  No writes ever happen through
these models — the reports module is strictly read-only.

Tenant isolation: all queries MUST join through skus.org_id.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ContentScoreRead(Base):
    """
    Read-only mapping of the content_scores table for the reports domain.

    Uses __tablename__ = "content_scores" — matches the table created by
    migration 0003.  All scoring columns may be NULL when the ML processor
    has not yet run for this row.
    """

    __tablename__ = "content_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    sku_platform_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sku_platforms.id", ondelete="CASCADE"),
        nullable=False,
    )
    scored_at: Mapped[date] = mapped_column(Date(), nullable=False)
    collected_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    image_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    description_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    composition_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    content_total: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    in_stock: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
