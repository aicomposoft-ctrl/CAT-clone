"""
Celery tasks: daily CLIP image scoring pipeline.

Two tasks:
  score_image_content_all  — orchestrator, Beat 06:00 UTC
  score_image_content      — per-row scorer

score_image_content_all:
  Queries all content_scores rows where:
    scored_at = today()
    image_score IS NULL
    collected_image_url IS NOT NULL
  Dispatches one score_image_content task per matching row (Celery group).
  Idempotent: if run twice, second run finds 0 unscored rows → no-op.

score_image_content:
  For one content_scores row:
    1. Load reference embedding from Redis: ref_emb:{sku_id}:image
       → if missing: log warning, return (no DB write, score stays NULL)
    2. Download collected image from MinIO via collected_image_url (S3 key)
       → oversized (> MAX_IMAGE_BYTES): log warning, return
       → transient error: retry (max 3, countdown=2^attempt)
    3. Decode image (JPEG/PNG/WEBP — AC-SEC-3)
       → decode failure: log warning, return
    4. Compute CLIP embedding → cosine similarity (dot product, both L2-normalized)
    5. Clamp to [0.0, 1.0], round to 2 decimal places
    6. UPDATE content_scores SET image_score=score WHERE id=cs_id
       → row deleted race: UPDATE 0 rows → log warning, no crash

Multi-tenant isolation:
  sku_id → ref_emb:{sku_id}:image (UUID uniqueness = org namespace isolation)
  DB UPDATE is by content_scores.id (PK) — single-row, no cross-org risk.
  PostgreSQL RLS provides final backstop (application DB user).
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from celery import group
from sqlalchemy import update

from app.celery_app import celery_app
from app.core.clip_model import decode_image, encode_image
from app.core.db import get_db_session
from app.core.minio_client import download_object
from app.core.redis_client import get_embedding
from app.models import ContentScore, SKUPlatform

logger = logging.getLogger(__name__)


def _today() -> date:
    """Return today's date in UTC."""
    return datetime.now(tz=timezone.utc).date()


@celery_app.task(name="processor.score_image_content_all")
def score_image_content_all() -> None:
    """
    Daily orchestrator: dispatch per-row scoring tasks for all unscored images.
    Triggered by Celery Beat at 06:00 UTC.

    Idempotent — rows with image_score already set are excluded from the query.
    """
    today = _today()

    with get_db_session() as db:
        rows = (
            db.query(
                ContentScore.id,
                SKUPlatform.sku_id,
                ContentScore.collected_image_url,
            )
            .join(SKUPlatform, SKUPlatform.id == ContentScore.sku_platform_id)
            .filter(
                ContentScore.scored_at == today,
                ContentScore.image_score.is_(None),
                ContentScore.collected_image_url.isnot(None),
            )
            .all()
        )

    count = len(rows)
    logger.info("score_image_content_all: %d rows to score for %s", count, today)

    if not rows:
        return

    group(
        score_image_content.s(str(row.id), str(row.sku_id), row.collected_image_url)
        for row in rows
    ).apply_async(queue="ml")

    logger.info("score_image_content_all: dispatched %d tasks", count)


@celery_app.task(
    bind=True,
    max_retries=3,
    name="processor.score_image_content",
)
def score_image_content(
    self,
    cs_id: str,
    sku_id: str,
    s3_key: str,
) -> None:
    """
    Compute CLIP cosine similarity for one content_scores row.

    Args:
        cs_id:   content_scores.id (UUID string) — scope of the DB UPDATE
        sku_id:  skus.id (UUID string) — Redis key: ref_emb:{sku_id}:image
        s3_key:  MinIO key for the collected image
    """
    import numpy as np

    # Step 1: Load reference embedding from Redis
    ref_emb = get_embedding(sku_id, field="image")
    if ref_emb is None:
        logger.warning(
            "score_image_content: no reference embedding for sku_id=%s cs_id=%s — skip",
            sku_id,
            cs_id,
        )
        return  # no DB write — score stays NULL, re-queued next run

    # Step 2: Download collected image from MinIO
    try:
        image_bytes = download_object(s3_key)
    except ValueError as exc:
        # Oversized image (AC-SEC-1) — no retry
        logger.warning(
            "score_image_content: %s cs_id=%s — skip", exc, cs_id
        )
        return
    except Exception as exc:
        logger.warning(
            "score_image_content: MinIO download failed cs_id=%s (attempt %d): %s",
            cs_id,
            self.request.retries + 1,
            exc,
        )
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    # Step 3: Decode image (format validation — AC-SEC-3)
    try:
        pil_image = decode_image(image_bytes)
    except Exception as exc:
        logger.warning(
            "score_image_content: image decode failed cs_id=%s: %s — skip", cs_id, exc
        )
        return

    # Step 4: Compute CLIP embedding
    try:
        collected_emb = encode_image(pil_image)
    except ValueError as exc:
        # Zero-norm guard (AC-SEC-5)
        logger.error(
            "score_image_content: %s cs_id=%s — skip", exc, cs_id
        )
        return

    # Step 5: Cosine similarity — both embeddings are L2-normalized → dot product
    raw_score = float(np.dot(collected_emb, ref_emb))
    clamped = max(0.0, min(1.0, raw_score))
    score = Decimal(str(clamped)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Step 6: UPDATE content_scores.image_score (single-row by PK)
    with get_db_session() as db:
        result = db.execute(
            update(ContentScore)
            .where(ContentScore.id == uuid.UUID(cs_id))
            .values(image_score=score)
        )
        if result.rowcount == 0:
            logger.warning(
                "score_image_content: cs_id=%s not found in DB (deleted?) — no write",
                cs_id,
            )
            return

    logger.info(
        "score_image_content: done cs_id=%s sku_id=%s score=%s",
        cs_id,
        sku_id,
        score,
    )
