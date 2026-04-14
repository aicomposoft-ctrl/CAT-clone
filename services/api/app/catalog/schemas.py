"""
Pydantic request/response schemas for the catalog domain.

Naming convention: XxxRequest (input), XxxResponse (output), XxxListResponse (paginated list).
All UUIDs are uuid.UUID, all datetimes are timezone-aware.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Brand schemas
# ---------------------------------------------------------------------------

class BrandCreateRequest(BaseModel):
    name: str = Field(..., max_length=255)
    type: str = Field(default="client", pattern="^(client|competitor)$")


class BrandUpdateRequest(BaseModel):
    """Used by PATCH /brands/{id} to assign a brand to a client (or remove the assignment)."""
    client_id: Optional[UUID] = None


class BrandResponse(BaseModel):
    id: UUID
    org_id: UUID
    client_id: Optional[UUID] = None
    name: str
    type: str
    created_at: datetime

    model_config = {"from_attributes": True}


class BrandListResponse(BaseModel):
    items: list[BrandResponse]
    total: int


# ---------------------------------------------------------------------------
# SKU schemas
# ---------------------------------------------------------------------------

class SKUCreateRequest(BaseModel):
    brand_id: UUID
    article: Optional[str] = Field(default=None, max_length=100)
    rpc: Optional[str] = Field(default=None, max_length=100)
    name: str = Field(..., max_length=500)
    barcode: Optional[str] = Field(default=None, max_length=50)
    category: Optional[str] = Field(default=None, max_length=255)
    sub_category: Optional[str] = Field(default=None, max_length=255)


class SKUUpdateRequest(BaseModel):
    brand_id: Optional[UUID] = None
    article: Optional[str] = Field(default=None, max_length=100)
    rpc: Optional[str] = Field(default=None, max_length=100)
    name: Optional[str] = Field(default=None, max_length=500)
    barcode: Optional[str] = Field(default=None, max_length=50)
    category: Optional[str] = Field(default=None, max_length=255)
    sub_category: Optional[str] = Field(default=None, max_length=255)
    is_active: Optional[bool] = None


class SKUResponse(BaseModel):
    id: UUID
    org_id: UUID
    brand: BrandResponse
    article: Optional[str]
    rpc: Optional[str]
    name: str
    barcode: Optional[str]
    category: Optional[str]
    sub_category: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    # Reference fields — needed by the frontend to pre-populate the reference drawer
    reference_description: Optional[str] = None
    reference_composition: Optional[str] = None
    reference_image_url: Optional[str] = None

    model_config = {"from_attributes": True}


class SKUListFilters(BaseModel):
    brand_id: Optional[UUID] = None
    include_inactive: bool = False


class SKUListResponse(BaseModel):
    items: list[SKUResponse]
    total: int
    next_cursor: Optional[str]


# ---------------------------------------------------------------------------
# Bulk upload schemas
# ---------------------------------------------------------------------------

class BulkUploadRowError(BaseModel):
    row: int
    field: str
    reason: str


class BulkUploadResponse(BaseModel):
    imported: int
    failed: int
    errors: list[BulkUploadRowError]


# ---------------------------------------------------------------------------
# Platform schemas
# ---------------------------------------------------------------------------

class PlatformResponse(BaseModel):
    id: UUID
    name: str
    type: Optional[str]
    schedule_cron: str
    is_active: bool

    model_config = {"from_attributes": True}


class PlatformListResponse(BaseModel):
    items: list[PlatformResponse]


# ---------------------------------------------------------------------------
# SKUPlatform schemas
# ---------------------------------------------------------------------------

class SKUPlatformCreateRequest(BaseModel):
    sku_id: UUID
    platform_id: UUID
    external_id: Optional[str] = Field(default=None, max_length=255)
    url: Optional[str] = None


class SKUPlatformResponse(BaseModel):
    id: UUID
    sku_id: UUID
    platform_id: UUID
    external_id: Optional[str]
    url: Optional[str]
    is_monitored: bool
    created_at: datetime

    model_config = {"from_attributes": True}
