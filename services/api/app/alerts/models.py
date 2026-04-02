"""
SQLAlchemy ORM models for the alerts domain: AlertConfig, AlertEvent.

Multi-tenant isolation:
  - AlertConfig is scoped by org_id (direct column).
  - AlertEvent is scoped indirectly via config.org_id JOIN — every query
    against alert_events MUST join through alert_configs.org_id.

email_recipients is stored as a JSON string (list of email addresses).
This is cross-DB compatible (PostgreSQL and SQLite for tests).
"""

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

ALERT_TYPES = frozenset({"content_drop", "oos"})


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


class AlertConfig(Base):
    """
    An alert rule for an org.

    sku_id = NULL  → applies to all active SKUs for this org.
    platform_id = NULL → applies to all platforms.
    threshold = NULL → only valid for 'oos' alerts (no numeric cut-off needed).
    email_recipients → JSON-encoded list of email strings, always non-empty.
    """

    __tablename__ = "alert_configs"
    __table_args__ = (
        CheckConstraint(
            "alert_type IN ('content_drop', 'oos')",
            name="ck_alert_configs_type",
        ),
        Index("idx_alert_configs_org_id", "org_id"),
        Index("idx_alert_configs_active", "org_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    sku_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skus.id", ondelete="CASCADE"),
        nullable=True,
    )
    platform_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platforms.id", ondelete="RESTRICT"),
        nullable=True,
    )
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    threshold: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    # JSON-encoded list of email strings, e.g. '["a@x.com","b@x.com"]'
    email_recipients: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )

    def get_recipients(self) -> list[str]:
        """Decode email_recipients JSON string to a Python list."""
        return json.loads(self.email_recipients)

    def __repr__(self) -> str:
        return (
            f"<AlertConfig id={self.id} type={self.alert_type!r} "
            f"org={self.org_id} active={self.is_active}>"
        )


class AlertEvent(Base):
    """
    A single triggered alert instance.

    Dedup constraint: (config_id, sku_platform_id, scored_at) is UNIQUE
    so re-running the check job on the same day never produces duplicate events.

    Tenant isolation: no direct org_id. All queries MUST join through
    alert_configs.org_id — never query alert_events directly.
    """

    __tablename__ = "alert_events"
    __table_args__ = (
        UniqueConstraint(
            "config_id",
            "sku_platform_id",
            "scored_at",
            name="uq_alert_events_no_duplicate",
        ),
        Index("idx_alert_events_config", "config_id"),
        Index("idx_alert_events_pending", "is_sent", "triggered_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("alert_configs.id", ondelete="CASCADE"),
        nullable=False,
    )
    sku_platform_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sku_platforms.id", ondelete="CASCADE"),
        nullable=False,
    )
    scored_at: Mapped[date] = mapped_column(Date(), nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    value_before: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    value_after: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    is_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<AlertEvent id={self.id} type={self.alert_type!r} "
            f"sent={self.is_sent} at={self.scored_at}>"
        )
