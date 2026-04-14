"""
Pydantic v2 schemas for the stock domain.
"""

from uuid import UUID

from pydantic import BaseModel


class RowError(BaseModel):
    """Single row-level validation or lookup error from a CSV upload."""

    row: int
    field: str
    message: str


class DistributionPlanUploadResponse(BaseModel):
    """Response from POST /api/v1/stock/distribution-plan."""

    imported: int
    errors: list[RowError]


class DistributionPlanRow(BaseModel):
    """Single distribution plan row returned by GET listing."""

    id: UUID
    sku_id: UUID
    platform_id: UUID
    platform_name: str       # resolved via JOIN with platforms table
    sku_barcode: str | None  # resolved via JOIN with skus table (nullable in schema)
    group_name: str
    plan_tt_count: int
    week_number: int
    year: int


class DistributionPlanPage(BaseModel):
    """Paginated response for GET /api/v1/stock/distribution-plan."""

    items: list[DistributionPlanRow]
    total: int
    page: int
    size: int
