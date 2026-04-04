"""Pydantic schemas for the dashboard summary endpoint."""

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class DashboardRedZoneItem(BaseModel):
    sku_platform_id: uuid.UUID
    sku_name: str
    article: Optional[str]
    platform_name: str
    content_total: Optional[float]
    scored_at: date


class DashboardAlert(BaseModel):
    id: uuid.UUID
    alert_type: str
    sku_name: str
    platform_name: str
    value_before: Optional[float]
    value_after: Optional[float]
    triggered_at: datetime
    is_sent: bool


class DashboardSummary(BaseModel):
    avg_content_score: float
    active_alerts_count: int
    distribution_coverage_pct: float
    monitored_sku_count: int
    red_zone: list[DashboardRedZoneItem]
    recent_alerts: list[DashboardAlert]
