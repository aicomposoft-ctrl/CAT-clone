"""
Pydantic request/response schemas for the api_keys domain.

Design rules:
- APIKeyCreateRequest validates that expires_at, if provided, is a future datetime.
- APIKeyCreateResponse includes the raw key field — this is the ONLY response that
  returns the full key. It is never stored and cannot be recovered after this point.
- APIKeyListItem omits the raw key entirely; only key_prefix is shown for display.
- All datetime fields use timezone-aware UTC.
- ConfigDict(from_attributes=True) enables ORM model → schema conversion via
  model_validate(orm_instance).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class APIKeyCreateRequest(BaseModel):
    """
    Body for POST /api/v1/api-keys.

    expires_at must be a future UTC datetime if provided. Passing a past
    datetime is rejected at validation time — it would produce an immediately
    expired (unusable) key.
    """

    name: str = Field(
        min_length=1,
        max_length=255,
        description="Human-readable label for this API key (e.g. 'Power BI Integration').",
    )
    expires_at: Optional[datetime] = Field(
        default=None,
        description=(
            "Optional expiry datetime (ISO 8601, timezone-aware). "
            "Null / absent means the key never expires. "
            "Must be in the future if provided."
        ),
    )

    @field_validator("expires_at", mode="after")
    @classmethod
    def expires_at_must_be_future(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Reject expires_at values that are already in the past."""
        if v is None:
            return v
        # Normalise naive datetimes to UTC to allow comparison.
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        if v <= datetime.now(tz=timezone.utc):
            raise ValueError("expires_at must be a future datetime")
        return v


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class APIKeyCreateResponse(BaseModel):
    """
    Returned on successful POST /api/v1/api-keys.

    The `key` field contains the full plaintext API key — shown exactly once
    and never returned again. The caller must store it securely immediately.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="API key UUID.")
    name: str = Field(description="Human-readable label.")
    key: str = Field(
        description=(
            "Full API key (cat_live_... format). "
            "Shown ONCE on creation — not stored server-side. "
            "Save it now."
        )
    )
    key_prefix: str = Field(description="First 8 chars of the raw key portion (display only).")
    expires_at: Optional[datetime] = Field(description="Expiry datetime, or null if never.")
    created_at: datetime = Field(description="Creation timestamp (UTC).")


class APIKeyListItem(BaseModel):
    """
    Single entry in GET /api/v1/api-keys response.

    Does NOT include the raw key — only the prefix for display.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="API key UUID.")
    name: str = Field(description="Human-readable label.")
    key_prefix: str = Field(description="First 8 chars of the raw key portion (display only).")
    expires_at: Optional[datetime] = Field(description="Expiry datetime, or null if never.")
    last_used_at: Optional[datetime] = Field(description="Last successful auth timestamp, or null.")
    revoked: bool = Field(description="True if the key has been explicitly revoked.")
    created_at: datetime = Field(description="Creation timestamp (UTC).")


class APIKeyListResponse(BaseModel):
    """
    Paginated list response for GET /api/v1/api-keys.
    """

    items: list[APIKeyListItem] = Field(description="List of API key summaries.")
    total: int = Field(description="Total number of API keys for this organisation.")
