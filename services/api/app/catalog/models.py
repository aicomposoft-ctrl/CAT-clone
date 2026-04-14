"""
SQLAlchemy ORM models for the catalog domain: Brand, SKU, Platform, SKUPlatform.

Multi-tenant design:
  - Brand and SKU are org-scoped (org_id column, always filter by org_id in queries)
  - Platform is a global shared catalog (no org_id; read-only via API, ops-seeded)
  - SKUPlatform is tenant-scoped indirectly via sku.org_id JOIN

Article uniqueness: enforced via partial UNIQUE index (org_id, article) WHERE article IS NOT NULL.
Two SKUs with NULL article are allowed within the same org.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


class Brand(Base):
    """
    Product brand, tenant-scoped to an organization.

    type: "client" (own brand) | "competitor" (rival brand being monitored).
    Auto-created during bulk upload when brand_name is not found.
    """

    __tablename__ = "brands"
    __table_args__ = (
        CheckConstraint(
            "type IN ('client', 'competitor')",
            name="ck_brands_type",
        ),
        Index("idx_brands_org_id", "org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # client_id is nullable; NULL means the brand is unassigned (all-clients mode).
    # Set by PATCH /brands/{id} when an agency assigns a brand to a client.
    # Added by migration 0013. Part of multi-client-support feature.
    # NOTE: FK constraint to clients.id is enforced at DB level via migration 0013,
    # not at ORM level — avoids circular import and SQLite test-setup issues.
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        default=None,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="client", server_default="client"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )

    # Relationships
    skus: Mapped[list["SKU"]] = relationship("SKU", back_populates="brand", lazy="raise")

    def __repr__(self) -> str:
        return f"<Brand id={self.id} name={self.name!r} type={self.type!r}>"


class SKU(Base):
    """
    Stock Keeping Unit, tenant-scoped to an organization.

    article: optional external identifier, unique per org (enforced by partial index).
    is_active: soft-delete flag. Inactive SKUs are excluded from default list queries.
    """

    __tablename__ = "skus"
    __table_args__ = (
        Index("idx_skus_org_id", "org_id"),
        Index("idx_skus_brand_id", "brand_id"),
        Index("idx_skus_active", "org_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="RESTRICT"),
        nullable=False,
    )
    article: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    rpc: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    barcode: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sub_category: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reference_image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reference_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reference_composition: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_now_utc,
        onupdate=lambda: datetime.now(tz=timezone.utc),
    )

    # Relationships
    brand: Mapped["Brand"] = relationship("Brand", back_populates="skus", lazy="raise")
    sku_platforms: Mapped[list["SKUPlatform"]] = relationship(
        "SKUPlatform", back_populates="sku", cascade="all, delete-orphan", lazy="raise"
    )

    def __repr__(self) -> str:
        return f"<SKU id={self.id} article={self.article!r} name={self.name!r}>"


class Platform(Base):
    """
    Monitoring platform (marketplace, darkstore, retailer).

    Global shared catalog — not scoped to any org. Managed by ops team via migrations.
    Read-only via API.
    """

    __tablename__ = "platforms"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    scraper_module: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    schedule_cron: Mapped[str] = mapped_column(
        String(50), nullable=False, default="0 2 * * *", server_default="0 2 * * *"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    sku_platforms: Mapped[list["SKUPlatform"]] = relationship(
        "SKUPlatform", back_populates="platform", lazy="raise"
    )

    def __repr__(self) -> str:
        return f"<Platform id={self.id} name={self.name!r} type={self.type!r}>"


class SKUPlatform(Base):
    """
    Many-to-many link between SKU and Platform.

    Tenant isolation: no org_id column; isolation is via sku.org_id JOIN.
    Any query on sku_platforms MUST JOIN through skus to verify org ownership.
    """

    __tablename__ = "sku_platforms"
    __table_args__ = (
        Index("idx_sku_platforms_sku", "sku_id"),
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
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_monitored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )

    # Relationships
    sku: Mapped["SKU"] = relationship("SKU", back_populates="sku_platforms", lazy="raise")
    platform: Mapped["Platform"] = relationship(
        "Platform", back_populates="sku_platforms", lazy="raise"
    )

    def __repr__(self) -> str:
        return f"<SKUPlatform id={self.id} sku_id={self.sku_id} platform_id={self.platform_id}>"
