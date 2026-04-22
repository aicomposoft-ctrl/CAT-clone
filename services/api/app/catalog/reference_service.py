"""
Business logic for reference image and text uploads.

Rules:
  - Always verify SKU ownership via org_id before any S3 or Redis operation.
  - DB flush before Celery dispatch to avoid race condition (worker sees stale DB state).
  - Embedding cache invalidated synchronously on every upload/update.
  - Service raises LookupError (→ 404) or ValueError (→ 422/409) — never imports fastapi.
"""

from __future__ import annotations

import logging
import os
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import SKU
from app.catalog.reference_schemas import (
    PresignedUrlResponse,
    ReferenceImageUploadResponse,
    ReferenceTextRequest,
    ReferenceTextUploadResponse,
)
from app.catalog.repository import SKURepository
from app.core.minio_client import MinioClient

logger = logging.getLogger(__name__)

_EMBEDDING_TTL = 2592000  # 30 days in seconds


async def _get_redis():
    """Return an async Redis client. Returns None if REDIS_URL is not configured."""
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        return None
    try:
        from redis.asyncio import from_url as async_redis_from_url
        return await async_redis_from_url(redis_url, decode_responses=False)
    except Exception as exc:
        logger.warning("Redis unavailable: %s", exc)
        return None


async def _invalidate_embedding(redis_client, sku_id: UUID, *fields: str) -> None:
    """Delete embedding cache keys for a SKU. Silent on Redis failure."""
    if redis_client is None:
        return
    try:
        keys = [f"ref_emb:{sku_id}:{field}" for field in fields]
        await redis_client.delete(*keys)
    except Exception as exc:
        logger.warning("Redis delete failed for sku %s fields %s: %s", sku_id, fields, exc)


def _dispatch_clip_task(sku_id: UUID, s3_key: str) -> Optional[str]:
    """Dispatch CLIP embedding Celery task. Returns task ID or None if Celery not configured."""
    try:
        from app.tasks.embedding_tasks import compute_clip_embedding
        # Must route to 'ml' queue — processor worker listens on --queues=ml only.
        task = compute_clip_embedding.apply_async(args=[str(sku_id), s3_key], queue="ml")
        return task.id
    except Exception as exc:
        logger.warning("CLIP embedding task dispatch failed: %s", exc)
        return None


def _dispatch_text_task(sku_id: UUID, field: str, text: str) -> Optional[str]:
    """Dispatch text embedding Celery task. Returns task ID or None if Celery not configured."""
    try:
        from app.tasks.embedding_tasks import compute_text_embedding
        # Must route to 'ml' queue — processor worker listens on --queues=ml only.
        task = compute_text_embedding.apply_async(args=[str(sku_id), field, text], queue="ml")
        return task.id
    except Exception as exc:
        logger.warning("Text embedding task dispatch failed for field %s: %s", field, exc)
        return None


async def upload_reference_image(
    db: AsyncSession,
    minio: MinioClient,
    org_id: UUID,
    sku_id: UUID,
    content: bytes,
    filename: str,
    content_type: str,
) -> ReferenceImageUploadResponse:
    # 1. Verify SKU ownership
    sku = await SKURepository.get_by_id_and_org(db, sku_id, org_id)
    if sku is None:
        raise LookupError("SKU_NOT_FOUND")

    # 2. Validate image (size, extension, magic bytes, content-type)
    ext, mime = minio.validate_image(content, filename, content_type)

    # 3. Delete old S3 object and invalidate cached embedding if replacing
    redis = await _get_redis()
    if sku.reference_image_url is not None:
        await minio.delete(sku.reference_image_url, org_id=org_id)
        await _invalidate_embedding(redis, sku_id, "image")

    # 4. Upload new image
    s3_key = MinioClient.make_s3_key(org_id, sku_id, ext)
    await minio.upload(s3_key, content, mime)

    # 5. Persist S3 key to DB and flush before Celery dispatch (avoid race condition)
    await SKURepository.update(db, sku, reference_image_url=s3_key)
    await db.flush()

    # 6. Dispatch CLIP embedding computation (async, best-effort)
    task_id = _dispatch_clip_task(sku_id, s3_key)

    # 7. Generate presigned URL for immediate use
    presigned_url = await minio.presign(s3_key)

    return ReferenceImageUploadResponse(
        sku_id=sku_id,
        presigned_url=presigned_url,
        expires_in=MinioClient.PRESIGNED_TTL,
        embedding_task_id=task_id,
    )


async def upload_reference_text(
    db: AsyncSession,
    org_id: UUID,
    sku_id: UUID,
    data: ReferenceTextRequest,
) -> ReferenceTextUploadResponse:
    # 1. Verify SKU ownership
    sku = await SKURepository.get_by_id_and_org(db, sku_id, org_id)
    if sku is None:
        raise LookupError("SKU_NOT_FOUND")

    updates: dict = {}
    task_ids: dict[str, Optional[str]] = {}
    fields_to_invalidate: list[str] = []

    if data.reference_description is not None:
        updates["reference_description"] = data.reference_description
        fields_to_invalidate.append("desc")

    if data.reference_composition is not None:
        updates["reference_composition"] = data.reference_composition
        fields_to_invalidate.append("comp")

    if not updates:
        await db.refresh(sku)
        return ReferenceTextUploadResponse(
            sku_id=sku_id,
            embedding_task_ids={},
            reference_description=sku.reference_description,
            reference_composition=sku.reference_composition,
            updated_at=sku.updated_at,
        )

    # 2. Invalidate stale embeddings before DB update
    redis = await _get_redis()
    await _invalidate_embedding(redis, sku_id, *fields_to_invalidate)

    # 3. Persist to DB, then re-read row so response matches committed state (avoids stale ORM)
    await SKURepository.update(db, sku, **updates)
    fresh = await SKURepository.get_by_id_and_org(db, sku_id, org_id)
    if fresh is None:
        raise LookupError("SKU_NOT_FOUND")

    # 4. Dispatch text embedding tasks (async, best-effort)
    if data.reference_description is not None:
        task_ids["description"] = _dispatch_text_task(sku_id, "desc", data.reference_description)
    if data.reference_composition is not None:
        task_ids["composition"] = _dispatch_text_task(sku_id, "comp", data.reference_composition)

    return ReferenceTextUploadResponse(
        sku_id=sku_id,
        embedding_task_ids=task_ids,
        reference_description=fresh.reference_description,
        reference_composition=fresh.reference_composition,
        updated_at=fresh.updated_at,
    )


async def get_presigned_url(
    db: AsyncSession,
    minio: MinioClient,
    org_id: UUID,
    sku_id: UUID,
) -> PresignedUrlResponse:
    # 1. Verify SKU ownership (org isolation)
    sku = await SKURepository.get_by_id_and_org(db, sku_id, org_id)
    if sku is None:
        raise LookupError("SKU_NOT_FOUND")

    if sku.reference_image_url is None:
        raise LookupError("REFERENCE_IMAGE_NOT_FOUND")

    presigned_url = await minio.presign(sku.reference_image_url)
    return PresignedUrlResponse(
        sku_id=sku_id,
        presigned_url=presigned_url,
        expires_in=MinioClient.PRESIGNED_TTL,
    )
