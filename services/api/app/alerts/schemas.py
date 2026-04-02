"""
Pydantic schemas for the alerts domain.

AlertConfigCreate  — POST body for creating an alert config
AlertConfigUpdate  — PATCH body (all fields optional)
AlertConfigResponse — API response for a single config
AlertConfigPage    — paginated list response
AlertEventResponse — API response for a single event
AlertEventPage     — paginated list response
AlertCheckResponse — response from POST /alerts/check
"""

import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

_VALID_ALERT_TYPES = {"content_drop", "oos"}


class AlertConfigCreate(BaseModel):
    alert_type: str = Field(..., description="'content_drop' or 'oos'")
    sku_id: Optional[uuid.UUID] = Field(
        None, description="NULL = all SKUs for this org"
    )
    platform_id: Optional[uuid.UUID] = Field(
        None, description="NULL = all platforms"
    )
    threshold: Optional[Decimal] = Field(
        None,
        ge=0,
        le=100,
        description="Score threshold (0-100). Required for content_drop; ignored for oos.",
    )
    email_recipients: list[EmailStr] = Field(
        ..., min_length=1, max_length=20, description="At least one recipient."
    )
    is_active: bool = Field(default=True)

    @field_validator("alert_type")
    @classmethod
    def validate_alert_type(cls, v: str) -> str:
        if v not in _VALID_ALERT_TYPES:
            raise ValueError(f"alert_type must be one of: {_VALID_ALERT_TYPES}")
        return v

    @model_validator(mode="after")
    def threshold_required_for_content_drop(self) -> "AlertConfigCreate":
        if self.alert_type == "content_drop" and self.threshold is None:
            raise ValueError("threshold is required for alert_type='content_drop'")
        return self


class AlertConfigUpdate(BaseModel):
    threshold: Optional[Decimal] = Field(None, ge=0, le=100)
    email_recipients: Optional[list[EmailStr]] = Field(None, min_length=1, max_length=20)
    is_active: Optional[bool] = None


class AlertConfigResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    sku_id: Optional[uuid.UUID]
    platform_id: Optional[uuid.UUID]
    alert_type: str
    threshold: Optional[Decimal]
    email_recipients: list[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_model(cls, obj) -> "AlertConfigResponse":
        return cls(
            id=obj.id,
            org_id=obj.org_id,
            sku_id=obj.sku_id,
            platform_id=obj.platform_id,
            alert_type=obj.alert_type,
            threshold=obj.threshold,
            email_recipients=obj.get_recipients(),
            is_active=obj.is_active,
            created_at=obj.created_at,
        )


class AlertConfigPage(BaseModel):
    items: list[AlertConfigResponse]
    total: int
    page: int
    size: int


class AlertEventResponse(BaseModel):
    id: uuid.UUID
    config_id: uuid.UUID
    sku_platform_id: uuid.UUID
    scored_at: date
    triggered_at: datetime
    alert_type: str
    value_before: Optional[Decimal]
    value_after: Optional[Decimal]
    is_sent: bool
    sent_at: Optional[datetime]

    model_config = {"from_attributes": True}


class AlertEventPage(BaseModel):
    items: list[AlertEventResponse]
    total: int
    page: int
    size: int


class AlertCheckResponse(BaseModel):
    events_created: int
    emails_sent: int
    errors: list[str]
