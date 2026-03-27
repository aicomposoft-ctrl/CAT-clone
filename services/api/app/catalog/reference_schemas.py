"""
Pydantic schemas for the Reference Upload feature.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ReferenceImageUploadResponse(BaseModel):
    sku_id: UUID
    presigned_url: str
    expires_in: int
    embedding_task_id: Optional[str]  # None when Celery not configured


class ReferenceTextRequest(BaseModel):
    reference_description: Optional[str] = Field(default=None, max_length=2000)
    reference_composition: Optional[str] = Field(default=None, max_length=1000)


class ReferenceTextUploadResponse(BaseModel):
    sku_id: UUID
    embedding_task_ids: dict[str, Optional[str]]


class PresignedUrlResponse(BaseModel):
    sku_id: UUID
    presigned_url: str
    expires_in: int
