"""
Business logic for the alerts domain.

check_and_send_alerts():
  Main entry point — runs all active alert configs for an org,
  creates AlertEvents for triggered conditions, and sends emails.

  Steps:
    1. Load active configs for the org.
    2. For each config:
       a. Query candidates (content scores or stock facts) for today.
       b. Exclude SKU×platforms already alerted today (dedup).
       c. Insert new AlertEvent rows.
    3. Group new events by config, render email, send.
    4. Mark events as sent.

  Returns AlertCheckResponse with counts and any non-fatal errors.
"""

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts import repository
from app.alerts.email import AlertEmailContext, send_alert_email
from app.alerts.models import AlertConfig, AlertEvent
from app.alerts.schemas import AlertCheckResponse, AlertConfigCreate, AlertConfigUpdate, AlertConfigPage, AlertConfigResponse, AlertEventPage, AlertEventResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CRUD helpers (thin wrappers used by the router)
# ---------------------------------------------------------------------------


async def create_alert_config(
    db: AsyncSession,
    org_id: uuid.UUID,
    data: AlertConfigCreate,
) -> AlertConfigResponse:
    config = await repository.create_config(
        db=db,
        org_id=org_id,
        alert_type=data.alert_type,
        email_recipients=[str(e) for e in data.email_recipients],
        sku_id=data.sku_id,
        platform_id=data.platform_id,
        threshold=data.threshold,
        is_active=data.is_active,
    )
    await db.commit()
    return AlertConfigResponse.from_orm_model(config)


async def get_alert_configs(
    db: AsyncSession,
    org_id: uuid.UUID,
    page: int,
    size: int,
) -> AlertConfigPage:
    items, total = await repository.list_configs(
        db=db, org_id=org_id, limit=size, offset=(page - 1) * size
    )
    return AlertConfigPage(
        items=[AlertConfigResponse.from_orm_model(c) for c in items],
        total=total,
        page=page,
        size=size,
    )


async def update_alert_config(
    db: AsyncSession,
    org_id: uuid.UUID,
    config_id: uuid.UUID,
    data: AlertConfigUpdate,
) -> Optional[AlertConfigResponse]:
    config = await repository.get_config(db, config_id, org_id)
    if config is None:
        return None
    recipients = [str(e) for e in data.email_recipients] if data.email_recipients else None
    updated = await repository.update_config(
        db=db,
        config=config,
        threshold=data.threshold,
        email_recipients=recipients,
        is_active=data.is_active,
    )
    await db.commit()
    return AlertConfigResponse.from_orm_model(updated)


async def delete_alert_config(
    db: AsyncSession, org_id: uuid.UUID, config_id: uuid.UUID
) -> bool:
    deleted = await repository.delete_config(db, config_id, org_id)
    await db.commit()
    return deleted


async def get_alert_events(
    db: AsyncSession,
    org_id: uuid.UUID,
    page: int,
    size: int,
    alert_type: Optional[str] = None,
    is_sent: Optional[bool] = None,
) -> AlertEventPage:
    items, total = await repository.list_events(
        db=db,
        org_id=org_id,
        limit=size,
        offset=(page - 1) * size,
        alert_type=alert_type,
        is_sent=is_sent,
    )
    return AlertEventPage(
        items=[AlertEventResponse.model_validate(e) for e in items],
        total=total,
        page=page,
        size=size,
    )


# ---------------------------------------------------------------------------
# Alert check engine
# ---------------------------------------------------------------------------


async def check_and_send_alerts(
    db: AsyncSession,
    org_id: uuid.UUID,
    org_name: str,
    check_date: Optional[date] = None,
) -> AlertCheckResponse:
    """
    Run all active alert configs for the org.

    check_date defaults to today (UTC).  Can be overridden in tests or for
    backfill scenarios.
    """
    if check_date is None:
        check_date = datetime.now(tz=timezone.utc).date()

    configs = await repository.get_active_configs(db, org_id)
    if not configs:
        return AlertCheckResponse(events_created=0, emails_sent=0, errors=[])

    events_created = 0
    emails_sent = 0
    errors: list[str] = []

    # Group events by config_id so we send one email per config rule
    new_events_by_config: dict[uuid.UUID, list[tuple[AlertEvent, dict]]] = {}

    for config in configs:
        new_events_by_config[config.id] = []
        candidates = await _get_candidates(db, config, check_date)

        # Bulk pre-load already-alerted sku_platform_ids for this config + date
        # to avoid N+1 SELECT queries (one per candidate).
        already_alerted_set = await repository.get_alerted_sku_platforms(
            db, config.id, check_date
        )

        for candidate in candidates:
            sp_id = candidate["sku_platform_id"]
            if sp_id in already_alerted_set:
                continue

            value_after: Optional[Decimal] = candidate.get("content_total")

            event = await repository.create_event(
                db=db,
                config_id=config.id,
                org_id=config.org_id,
                sku_platform_id=sp_id,
                scored_at=check_date,
                alert_type=config.alert_type,
                value_after=value_after,
            )
            if event is not None:
                events_created += 1
                new_events_by_config[config.id].append((event, candidate))

    # Commit all events before sending emails (atomic: emails are best-effort)
    await db.commit()

    # Send one email per config that has new events
    for config in configs:
        event_pairs = new_events_by_config.get(config.id, [])
        if not event_pairs:
            continue

        rows = [
            {
                "sku_name": c.get("sku_name", ""),
                "sku_article": c.get("sku_article"),
                "platform_name": c.get("platform_name", ""),
                "value_after": c.get("content_total"),
            }
            for _, c in event_pairs
        ]
        ctx = AlertEmailContext(
            alert_type=config.alert_type,
            org_name=org_name,
            check_date=check_date,
            recipients=config.get_recipients(),
            rows=rows,
        )

        try:
            await send_alert_email(ctx)
            sent_ids = [e.id for e, _ in event_pairs]
            await repository.mark_events_sent(db, sent_ids)
            await db.commit()
            emails_sent += 1
        except Exception as exc:
            logger.error("Failed to send alert email for config %s: %s", config.id, exc)
            errors.append(f"config {config.id}: {exc}")

    return AlertCheckResponse(
        events_created=events_created,
        emails_sent=emails_sent,
        errors=errors,
    )


async def _get_candidates(
    db: AsyncSession, config: AlertConfig, check_date: date
) -> list[dict]:
    """Dispatch to the right candidate query based on alert_type."""
    if config.alert_type == "content_drop":
        return await repository.get_content_drop_candidates(
            db=db,
            org_id=config.org_id,
            check_date=check_date,
            threshold=config.threshold,
            sku_id=config.sku_id,
            platform_id=config.platform_id,
        )
    if config.alert_type == "oos":
        return await repository.get_oos_candidates(
            db=db,
            org_id=config.org_id,
            check_date=check_date,
            sku_id=config.sku_id,
            platform_id=config.platform_id,
        )
    logger.warning("Unknown alert_type %r — skipping config %s", config.alert_type, config.id)
    return []
