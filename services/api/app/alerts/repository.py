"""
Database queries for the alerts domain.

All queries MUST be org-scoped:
  - alert_configs: direct org_id column
  - alert_events: join through alert_configs.org_id — never query directly

De-duplication of events uses the UNIQUE constraint
(config_id, sku_platform_id, scored_at) — INSERT is silently ignored on conflict
via INSERT OR IGNORE (SQLite) / ON CONFLICT DO NOTHING (PostgreSQL).
"""

import json
import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.alerts.models import AlertConfig, AlertEvent
from app.catalog.models import Brand, Platform, SKU, SKUPlatform
from app.reports.models import ContentScoreRead


# ---------------------------------------------------------------------------
# AlertConfig CRUD
# ---------------------------------------------------------------------------


async def create_config(
    db: AsyncSession,
    org_id: uuid.UUID,
    alert_type: str,
    email_recipients: list[str],
    sku_id: Optional[uuid.UUID] = None,
    platform_id: Optional[uuid.UUID] = None,
    threshold: Optional[Decimal] = None,
    is_active: bool = True,
) -> AlertConfig:
    config = AlertConfig(
        org_id=org_id,
        sku_id=sku_id,
        platform_id=platform_id,
        alert_type=alert_type,
        threshold=threshold,
        email_recipients=json.dumps(email_recipients),
        is_active=is_active,
    )
    db.add(config)
    await db.flush()
    await db.refresh(config)
    return config


async def get_config(
    db: AsyncSession, config_id: uuid.UUID, org_id: uuid.UUID
) -> Optional[AlertConfig]:
    stmt = select(AlertConfig).where(
        AlertConfig.id == config_id, AlertConfig.org_id == org_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_configs(
    db: AsyncSession,
    org_id: uuid.UUID,
    limit: int,
    offset: int,
) -> tuple[list[AlertConfig], int]:
    count_stmt = (
        select(func.count())
        .select_from(AlertConfig)
        .where(AlertConfig.org_id == org_id)
    )
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(AlertConfig)
        .where(AlertConfig.org_id == org_id)
        .order_by(AlertConfig.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def update_config(
    db: AsyncSession,
    config: AlertConfig,
    threshold: Optional[Decimal],
    email_recipients: Optional[list[str]],
    is_active: Optional[bool],
) -> AlertConfig:
    if threshold is not None:
        config.threshold = threshold
    if email_recipients is not None:
        config.email_recipients = json.dumps(email_recipients)
    if is_active is not None:
        config.is_active = is_active
    await db.flush()
    await db.refresh(config)
    return config


async def delete_config(
    db: AsyncSession, config_id: uuid.UUID, org_id: uuid.UUID
) -> bool:
    stmt = (
        delete(AlertConfig)
        .where(AlertConfig.id == config_id, AlertConfig.org_id == org_id)
    )
    result = await db.execute(stmt)
    return result.rowcount > 0


# ---------------------------------------------------------------------------
# Alert check queries
# ---------------------------------------------------------------------------


async def get_active_configs(
    db: AsyncSession, org_id: uuid.UUID
) -> list[AlertConfig]:
    """Return all active alert configs for the org."""
    stmt = (
        select(AlertConfig)
        .where(AlertConfig.org_id == org_id, AlertConfig.is_active.is_(True))
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_content_drop_candidates(
    db: AsyncSession,
    org_id: uuid.UUID,
    check_date: date,
    threshold: Decimal,
    sku_id: Optional[uuid.UUID],
    platform_id: Optional[uuid.UUID],
) -> list[dict]:
    """
    Return sku_platform rows where content_total < threshold on check_date.

    Each dict has: sku_platform_id, content_total, sku_name, platform_name.
    Used to determine which alert events to create for a content_drop config.
    """
    stmt = (
        select(
            ContentScoreRead.sku_platform_id,
            ContentScoreRead.content_total,
            SKU.name.label("sku_name"),
            SKU.article.label("sku_article"),
            Platform.name.label("platform_name"),
        )
        .join(SKUPlatform, ContentScoreRead.sku_platform_id == SKUPlatform.id)
        .join(SKU, SKUPlatform.sku_id == SKU.id)
        .join(Platform, SKUPlatform.platform_id == Platform.id)
        .where(SKU.org_id == org_id)
        .where(ContentScoreRead.scored_at == check_date)
        .where(ContentScoreRead.content_total < threshold)
        .where(ContentScoreRead.content_total.is_not(None))
    )
    if sku_id is not None:
        stmt = stmt.where(SKUPlatform.sku_id == sku_id)
    if platform_id is not None:
        stmt = stmt.where(SKUPlatform.platform_id == platform_id)

    result = await db.execute(stmt)
    return [dict(r._mapping) for r in result.all()]


async def get_oos_candidates(
    db: AsyncSession,
    org_id: uuid.UUID,
    check_date: date,
    sku_id: Optional[uuid.UUID],
    platform_id: Optional[uuid.UUID],
) -> list[dict]:
    """
    Return sku_platform rows where in_stock = False on check_date.
    """
    stmt = (
        select(
            ContentScoreRead.sku_platform_id,
            SKU.name.label("sku_name"),
            SKU.article.label("sku_article"),
            Platform.name.label("platform_name"),
        )
        .join(SKUPlatform, ContentScoreRead.sku_platform_id == SKUPlatform.id)
        .join(SKU, SKUPlatform.sku_id == SKU.id)
        .join(Platform, SKUPlatform.platform_id == Platform.id)
        .where(SKU.org_id == org_id)
        .where(ContentScoreRead.scored_at == check_date)
        .where(ContentScoreRead.in_stock.is_(False))
    )
    if sku_id is not None:
        stmt = stmt.where(SKUPlatform.sku_id == sku_id)
    if platform_id is not None:
        stmt = stmt.where(SKUPlatform.platform_id == platform_id)

    result = await db.execute(stmt)
    return [dict(r._mapping) for r in result.all()]


async def get_alerted_sku_platforms(
    db: AsyncSession,
    config_id: uuid.UUID,
    scored_at: date,
) -> set[uuid.UUID]:
    """Return set of sku_platform_ids already alerted for this config + date."""
    stmt = select(AlertEvent.sku_platform_id).where(
        AlertEvent.config_id == config_id,
        AlertEvent.scored_at == scored_at,
    )
    result = await db.execute(stmt)
    return {row[0] for row in result.all()}


async def create_event(
    db: AsyncSession,
    config_id: uuid.UUID,
    org_id: uuid.UUID,
    sku_platform_id: uuid.UUID,
    scored_at: date,
    alert_type: str,
    value_before: Optional[Decimal] = None,
    value_after: Optional[Decimal] = None,
) -> Optional[AlertEvent]:
    """
    Insert an AlertEvent. Returns None if the dedup constraint fires
    (already exists for this config × sku_platform × date).

    Uses a savepoint (begin_nested) so an IntegrityError only rolls back
    this single INSERT — the surrounding session transaction is preserved.
    """
    event = AlertEvent(
        config_id=config_id,
        org_id=org_id,
        sku_platform_id=sku_platform_id,
        scored_at=scored_at,
        alert_type=alert_type,
        value_before=value_before,
        value_after=value_after,
        is_sent=False,
    )
    try:
        async with db.begin_nested():
            db.add(event)
            await db.flush()
        return event
    except IntegrityError:
        return None


async def mark_events_sent(
    db: AsyncSession, event_ids: list[uuid.UUID]
) -> None:
    """Mark a batch of events as sent."""
    if not event_ids:
        return
    stmt = (
        update(AlertEvent)
        .where(AlertEvent.id.in_(event_ids))
        .values(is_sent=True, sent_at=datetime.now(tz=timezone.utc))
    )
    await db.execute(stmt)
    logger.info(
        "Alert events marked sent: count=%d event_ids=%s",
        len(event_ids),
        [str(e) for e in event_ids],
    )


# ---------------------------------------------------------------------------
# AlertEvent listing
# ---------------------------------------------------------------------------


async def list_events(
    db: AsyncSession,
    org_id: uuid.UUID,
    limit: int,
    offset: int,
    alert_type: Optional[str] = None,
    is_sent: Optional[bool] = None,
) -> tuple[list[AlertEvent], int]:
    """
    Return paginated alert events for org, ordered newest first.
    Tenant isolation via JOIN through alert_configs.org_id.
    """
    base = select(AlertEvent).where(AlertEvent.org_id == org_id)
    if alert_type is not None:
        base = base.where(AlertEvent.alert_type == alert_type)
    if is_sent is not None:
        base = base.where(AlertEvent.is_sent.is_(is_sent))

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    data_stmt = (
        base.order_by(AlertEvent.triggered_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(data_stmt)
    return list(result.scalars().all()), total
