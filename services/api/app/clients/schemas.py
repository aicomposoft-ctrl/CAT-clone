"""
Pydantic request/response schemas for the clients domain.

Design rules:
- ClientCreateRequest validates slug against ^[a-z0-9-]+$ pattern — enforced
  at validation time so invalid slugs are rejected before any DB call.
- slug is NOT updatable via ClientUpdateRequest — it is a stable identifier
  used in JWT claims and report filenames. Changing it would invalidate active
  tokens with a client_id claim (Architecture.md § 3, § 6).
- ClientResponse includes brand_count (computed in service layer via COUNT query)
  so the management UI can display brand assignments without a separate call.
- ConfigDict(from_attributes=True) enables ORM model → schema conversion via
  model_validate(orm_instance).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class ClientCreateRequest(BaseModel):
    """
    Body for POST /api/v1/clients.

    slug must match ^[a-z0-9-]+$ and be unique within the org (enforced by
    service layer and DB partial unique index uq_clients_org_slug).
    """

    name: str = Field(
        min_length=1,
        max_length=255,
        description="Human-readable client name (e.g. 'Nestle RU').",
    )
    slug: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9-]+$",
        description=(
            "URL-safe identifier unique within the org. "
            "Lowercase letters, digits, and hyphens only. "
            "Used in report filenames and JWT client context."
        ),
    )
    contact_email: Optional[EmailStr] = Field(
        default=None,
        description="Optional contact email for the client.",
    )
    logo_url: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional URL for the client's logo image.",
    )


class ClientUpdateRequest(BaseModel):
    """
    Body for PATCH /api/v1/clients/{client_id}.

    slug is intentionally omitted — it is a stable identifier and cannot be
    changed after creation (Architecture.md § 3: slug used in JWT claims and
    report filenames; changing it would invalidate active tokens).
    """

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Updated human-readable client name.",
    )
    contact_email: Optional[EmailStr] = Field(
        default=None,
        description="Updated contact email for the client.",
    )
    logo_url: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Updated URL for the client's logo image.",
    )


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class ClientResponse(BaseModel):
    """
    Single client representation returned by all CRUD endpoints.

    brand_count is a computed field — populated by the service layer via a
    COUNT query on brands.client_id (not stored in the clients table).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Client UUID.")
    name: str = Field(description="Human-readable client name.")
    slug: str = Field(description="URL-safe client identifier (stable, not updatable).")
    contact_email: Optional[str] = Field(description="Contact email, or null.")
    logo_url: Optional[str] = Field(description="Logo URL, or null.")
    is_active: bool = Field(description="False if the client has been deactivated.")
    brand_count: int = Field(description="Number of brands currently assigned to this client.")
    created_at: datetime = Field(description="Creation timestamp (UTC).")


class ClientListResponse(BaseModel):
    """
    Paginated list response for GET /api/v1/clients.
    """

    items: list[ClientResponse] = Field(description="List of client records.")
    total: int = Field(description="Total number of clients for this organisation.")
