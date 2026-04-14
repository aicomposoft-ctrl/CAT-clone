"""
SQLAlchemy ORM model for the stock domain: DistributionPlan.

Tenant isolation: distribution_plans has no org_id column.
Isolation is enforced by always joining through skus.org_id.
Every query in repository.py MUST join through skus — never query this
table directly without verifying org ownership.
"""

import uuid
from uuid import uuid4

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DistributionPlan(Base):
    """
    Distribution plan row: planned trade-point count for a SKU×Platform×week.

    UNIQUE constraint on (sku_id, platform_id, week_number, year) enables
    UPSERT semantics — re-uploading the same CSV week is safe and idempotent.
    """

    __tablename__ = "distribution_plans"
    __table_args__ = (
        UniqueConstraint(
            "sku_id",
            "platform_id",
            "week_number",
            "year",
            name="uq_distribution_plans_key",
        ),
        Index(
            "idx_distribution_plans_sku_platform_week",
            "sku_id",
            "platform_id",
            "week_number",
            "year",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skus.id", ondelete="CASCADE"),
        nullable=False,
    )
    platform_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platforms.id", ondelete="RESTRICT"),
        nullable=False,
    )
    group_name: Mapped[str] = mapped_column(String(100), nullable=False)
    plan_tt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<DistributionPlan id={self.id} sku_id={self.sku_id} "
            f"week={self.week_number}/{self.year}>"
        )
