"""
HTTP routes for the alerts domain.

Endpoints:
  POST   /api/v1/alerts/configs          — create alert config (admin, manager)
  GET    /api/v1/alerts/configs          — list configs (all roles)
  PATCH  /api/v1/alerts/configs/{id}     — update config (admin, manager)
  DELETE /api/v1/alerts/configs/{id}     — delete config (admin, manager)
  GET    /api/v1/alerts/events           — list alert events (all roles)
  POST   /api/v1/alerts/check            — run alert check manually (admin only)
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.repository import UserRepository
from app.core.deps import get_current_user, get_db, require_role
from app.alerts import service
from app.alerts.schemas import (
    AlertCheckResponse,
    AlertConfigCreate,
    AlertConfigPage,
    AlertConfigResponse,
    AlertConfigUpdate,
    AlertEventPage,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/configs",
    response_model=AlertConfigResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create alert config",
)
async def create_alert_config(
    body: AlertConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "manager")),
) -> AlertConfigResponse:
    return await service.create_alert_config(db=db, org_id=current_user.org_id, data=body)


@router.get(
    "/configs",
    response_model=AlertConfigPage,
    summary="List alert configs",
)
async def list_alert_configs(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlertConfigPage:
    return await service.get_alert_configs(
        db=db, org_id=current_user.org_id, page=page, size=size
    )


@router.patch(
    "/configs/{config_id}",
    response_model=AlertConfigResponse,
    summary="Update alert config",
)
async def update_alert_config(
    config_id: UUID,
    body: AlertConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "manager")),
) -> AlertConfigResponse:
    result = await service.update_alert_config(
        db=db, org_id=current_user.org_id, config_id=config_id, data=body
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CONFIG_NOT_FOUND")
    return result


@router.delete(
    "/configs/{config_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete alert config",
)
async def delete_alert_config(
    config_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "manager")),
) -> None:
    deleted = await service.delete_alert_config(
        db=db, org_id=current_user.org_id, config_id=config_id
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CONFIG_NOT_FOUND")


@router.get(
    "/events",
    response_model=AlertEventPage,
    summary="List alert events",
)
async def list_alert_events(
    alert_type: Optional[str] = Query(None, description="Filter: 'content_drop' or 'oos'"),
    is_sent: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlertEventPage:
    return await service.get_alert_events(
        db=db,
        org_id=current_user.org_id,
        page=page,
        size=size,
        alert_type=alert_type,
        is_sent=is_sent,
    )


@router.post(
    "/check",
    response_model=AlertCheckResponse,
    summary="Run alert check for this org (admin only)",
)
async def run_alert_check(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> AlertCheckResponse:
    """
    Manually trigger the alert check for the authenticated admin's org.
    Useful for testing alert configs without waiting for the scheduled run.
    Emails are sent if SMTP_HOST is configured.
    """
    try:
        return await service.check_and_send_alerts(
            db=db,
            org_id=current_user.org_id,
            org_name=str(current_user.org_id),  # name resolved in background job
        )
    except Exception:
        logger.exception("Unexpected error during manual alert check")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="INTERNAL_ERROR",
        )
