"""
Celery task: compute E5 reference text embedding and cache in Redis.

Task name: "cat.compute_text_embedding"
  Must match the name dispatched by services/api/app/catalog/reference_service.py
  (_dispatch_text_task calls compute_text_embedding.apply_async(queue='ml')).

Triggered by: PUT /api/v1/catalog/skus/{id}/reference-text in the API.

Args:
  sku_id: str  — UUID of the SKU (Redis key prefix)
  field:  str  — "desc" | "comp"
  text:   str  — reference description or composition text

Flow:
  1. Encode text with multilingual-e5-base, "passage: " prefix (e5 document protocol)
  2. Validate shape (768,) and L2 norm
  3. Store in Redis: ref_emb:{sku_id}:{field}, TTL 30 days, raw float32 bytes
"""

from __future__ import annotations

import logging

from app.celery_app import celery_app
from app.core.e5_model import encode_reference_text
from app.core.redis_client import set_embedding

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=3,
    name="cat.compute_text_embedding",
)
def compute_text_embedding(self, sku_id: str, field: str, text: str) -> None:
    """
    Compute multilingual-e5-base embedding for a reference text and cache in Redis.

    Args:
        sku_id: UUID string — Redis key: ref_emb:{sku_id}:{field}
        field:  "desc" or "comp"
        text:   reference text content (description or composition)
    """
    if field not in ("desc", "comp"):
        logger.error(
            "compute_text_embedding: unknown field=%r for sku_id=%s — skipping", field, sku_id
        )
        return

    if not text or not text.strip():
        logger.warning(
            "compute_text_embedding: empty text for sku_id=%s field=%s — skipping", sku_id, field
        )
        return

    try:
        embedding = encode_reference_text(text)
    except ValueError as exc:
        logger.error(
            "compute_text_embedding: %s for sku_id=%s field=%s — skipping", exc, sku_id, field
        )
        return
    except Exception as exc:
        logger.warning(
            "compute_text_embedding: E5 encode failed for sku_id=%s field=%s (attempt %d): %s",
            sku_id, field, self.request.retries + 1, exc,
        )
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    try:
        set_embedding(sku_id, embedding, field=field)
    except Exception as exc:
        logger.warning(
            "compute_text_embedding: Redis write failed for sku_id=%s field=%s (attempt %d): %s",
            sku_id, field, self.request.retries + 1, exc,
        )
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    logger.info("compute_text_embedding: done sku_id=%s field=%s", sku_id, field)
