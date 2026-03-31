"""
Celery task: compute CLIP reference image embedding and cache in Redis.

Task name: "cat.compute_clip_embedding"
  Must match the name dispatched by services/api/app/catalog/reference_service.py
  (_dispatch_clip_task imports and calls compute_clip_embedding.delay()).

Triggered by: POST /api/v1/catalog/skus/{id}/reference-image upload in the API.

Flow:
  1. Download reference image from MinIO (S3 key from API)
  2. Decode bytes → PIL RGB image (JPEG/PNG/WEBP only)
  3. Compute CLIP ViT-B/32 embedding → np.ndarray shape (512,), L2-normalized
  4. Validate shape and L2 norm (AC-SEC-5)
  5. Store in Redis: ref_emb:{sku_id}:image, TTL 30 days, pickle protocol 5

Error handling:
  - MinIO download fails (transient):   retry (max 3, countdown=2^attempt)
  - MinIO download fails (permanent):   log error, task ends without Redis write
  - Image decode fails (bad format):    log warning, no retry
  - Zero-norm embedding:                log error, no retry (model/image issue)
  - Redis write fails:                  retry (max 3, countdown=2^attempt)
"""

from __future__ import annotations

import logging

from app.celery_app import celery_app
from app.core.clip_model import decode_image, encode_image
from app.core.minio_client import download_object
from app.core.redis_client import set_embedding

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=3,
    name="cat.compute_clip_embedding",
)
def compute_clip_embedding(self, sku_id: str, s3_key: str) -> None:
    """
    Download reference image, compute CLIP embedding, store in Redis.

    Args:
        sku_id: UUID string — Redis key: ref_emb:{sku_id}:image
        s3_key: MinIO object key for the reference image
    """
    # Step 1: Download image from MinIO (retry on transient errors)
    try:
        image_bytes = download_object(s3_key)
    except ValueError as exc:
        # Oversized image — no retry
        logger.warning(
            "compute_clip_embedding: %s for sku_id=%s — skipping", exc, sku_id
        )
        return
    except Exception as exc:
        logger.warning(
            "compute_clip_embedding: MinIO download failed for sku_id=%s (attempt %d): %s",
            sku_id,
            self.request.retries + 1,
            exc,
        )
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    # Step 2: Decode image (JPEG/PNG/WEBP only — AC-SEC-3)
    try:
        pil_image = decode_image(image_bytes)
    except Exception as exc:
        logger.warning(
            "compute_clip_embedding: image decode failed for sku_id=%s: %s — skipping",
            sku_id,
            exc,
        )
        return

    # Step 3: Compute CLIP embedding
    try:
        embedding = encode_image(pil_image)
    except ValueError as exc:
        # Zero-norm guard triggered (AC-SEC-5)
        logger.error(
            "compute_clip_embedding: %s for sku_id=%s — skipping", exc, sku_id
        )
        return

    # Step 4: Store in Redis (retry on transient errors)
    try:
        set_embedding(sku_id, embedding, field="image")
    except Exception as exc:
        logger.warning(
            "compute_clip_embedding: Redis write failed for sku_id=%s (attempt %d): %s",
            sku_id,
            self.request.retries + 1,
            exc,
        )
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    logger.info("compute_clip_embedding: done sku_id=%s", sku_id)
