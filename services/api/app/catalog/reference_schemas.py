"""
Pydantic schemas for the Reference Upload feature.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ReferenceImageUploadResponse(BaseModel):
    sku_id: UUID
    presigned_url: str
    expires_in: int
    embedding_task_id: Optional[str]  # None when Celery not configured


class ReferenceTextRequest(BaseModel):
    reference_description: Optional[str] = Field(default=None, max_length=2000)
    reference_composition: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("reference_description", "reference_composition", mode="before")
    @classmethod
    def empty_str_to_none(cls, v: object) -> object:
        """Avoid wiping DB: UI often submits '' / whitespace for untouched fields."""
        if isinstance(v, str) and not v.strip():
            return None
        return v


class ReferenceTextUploadResponse(BaseModel):
    sku_id: UUID
    embedding_task_ids: dict[str, Optional[str]]
    # Echo DB state so the client can update cache without a follow-up GET race
    reference_description: Optional[str] = None
    reference_composition: Optional[str] = None
    updated_at: datetime


class PresignedUrlResponse(BaseModel):
    sku_id: UUID
    presigned_url: str
    expires_in: int
