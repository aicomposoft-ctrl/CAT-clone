"""
Celery tasks: daily multilingual-e5-base text scoring pipeline.

Two tasks:
  score_text_content_all  — orchestrator, Beat 06:30 UTC
  score_text_content      — per-row: description_score + composition_score + content_total

score_text_content_all:
  Queries content_scores rows where:
    scored_at = today()
    collected_description IS NOT NULL
    AND (description_score IS NULL OR
         (collected_composition IS NOT NULL AND composition_score IS NULL))
  Dispatches one score_text_content task per row (Celery group).
  Idempotent: fully-scored rows are excluded from the query.

score_text_content:
  For one row, independently scores description AND composition:
    - Encodes collected text with multilingual-e5-base ("query: " prefix)
    - Loads reference embedding from Redis (ref_emb:{sku_id}:desc or :comp)
    - Computes cosine similarity (dot product, both L2-normalized)
    - Writes description_score and/or composition_score
  Then computes content_total if all three scores (image + desc + comp) are non-NULL:
    content_total = 0.40 × image_score + 0.35 × description_score + 0.25 × composition_score
  All writes happen in a single DB transaction (atomic).

Multi-tenant isolation:
  sku_id → ref_emb:{sku_id}:{field} (UUID uniqueness = org namespace isolation)
  DB UPDATE is by content_scores.id (PK) — single-row, no cross-org risk.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from celery import group
from sqlalchemy import update

from app.celery_app import celery_app
from app.core.db import get_db_session
from app.core.e5_model import encode_text
from app.core.redis_client import get_embedding
from app.models import ContentScore, SKUPlatform

logger = logging.getLogger(__name__)

# content_total formula weights
_W_IMAGE = Decimal("0.40")
_W_DESC = Decimal("0.35")
_W_COMP = Decimal("0.25")


def _today() -> date:
    from datetime import datetime
    return datetime.now(tz=timezone.utc).date()


@celery_app.task(name="processor.score_text_content_all")
def score_text_content_all() -> None:
    """
    Daily orchestrator: dispatch per-row text scoring tasks.
    Triggered by Celery Beat at 06:30 UTC (30 min after image scoring).

    Idempotent — fully-scored rows excluded by the query filter.
    """
    today = _today()

    with get_db_session() as db:
        rows = (
            db.query(
                ContentScore.id,
                SKUPlatform.sku_id,
                ContentScore.collected_description,
                ContentScore.collected_composition,
            )
            .join(SKUPlatform, SKUPlatform.id == ContentScore.sku_platform_id)
            .filter(
                ContentScore.scored_at == today,
                ContentScore.collected_description.isnot(None),
                # Dispatch if description unscored OR composition exists but unscored
                (
                    ContentScore.description_score.is_(None)
                    | (
                        ContentScore.collected_composition.isnot(None)
                        & ContentScore.composition_score.is_(None)
                    )
                ),
            )
            .all()
        )

    count = len(rows)
    logger.info("score_text_content_all: %d rows to score for %s", count, today)

    if not rows:
        return

    group(
        score_text_content.s(
            str(row.id),
            str(row.sku_id),
            row.collected_description,
            row.collected_composition,
        )
        for row in rows
    ).delay()

    logger.info("score_text_content_all: dispatched %d tasks", count)


@celery_app.task(
    bind=True,
    max_retries=3,
    name="processor.score_text_content",
)
def score_text_content(
    self,
    cs_id: str,
    sku_id: str,
    description: Optional[str],
    composition: Optional[str],
) -> None:
    """
    Compute text similarity scores for one content_scores row.

    Args:
        cs_id:       content_scores.id (PK)
        sku_id:      skus.id — used for Redis key lookup
        description: collected_description (may be None)
        composition: collected_composition (may be None)
    """
    import numpy as np

    scores_to_write: dict = {}

    # ── Description scoring ──────────────────────────────────────────────────
    if description and description.strip():
        ref_desc = get_embedding(sku_id, field="desc")
        if ref_desc is None:
            logger.warning(
                "score_text_content: no ref_emb:desc for sku_id=%s cs_id=%s — skip desc",
                sku_id,
                cs_id,
            )
        else:
            try:
                collected_desc_emb = encode_text(description)
                raw_desc = float(np.dot(collected_desc_emb, ref_desc))
                clamped_desc = max(0.0, min(1.0, raw_desc))
                scores_to_write["description_score"] = Decimal(
                    str(clamped_desc)
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            except ValueError as exc:
                logger.error(
                    "score_text_content: %s for cs_id=%s desc — skip", exc, cs_id
                )
    else:
        logger.info(
            "score_text_content: empty/null description for cs_id=%s — skip desc", cs_id
        )

    # ── Composition scoring ──────────────────────────────────────────────────
    if composition and composition.strip():
        ref_comp = get_embedding(sku_id, field="comp")
        if ref_comp is None:
            logger.warning(
                "score_text_content: no ref_emb:comp for sku_id=%s cs_id=%s — skip comp",
                sku_id,
                cs_id,
            )
        else:
            try:
                collected_comp_emb = encode_text(composition)
                raw_comp = float(np.dot(collected_comp_emb, ref_comp))
                clamped_comp = max(0.0, min(1.0, raw_comp))
                scores_to_write["composition_score"] = Decimal(
                    str(clamped_comp)
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            except ValueError as exc:
                logger.error(
                    "score_text_content: %s for cs_id=%s comp — skip", exc, cs_id
                )
    else:
        logger.info(
            "score_text_content: null/empty composition for cs_id=%s — skip comp", cs_id
        )

    if not scores_to_write:
        return  # nothing to write

    # ── content_total (all three scores required) ────────────────────────────
    try:
        with get_db_session() as db:
            row = (
                db.query(
                    ContentScore.image_score,
                    ContentScore.description_score,
                    ContentScore.composition_score,
                )
                .filter(ContentScore.id == uuid.UUID(cs_id))
                .first()
            )

            if row is None:
                logger.warning(
                    "score_text_content: cs_id=%s not found (deleted?) — skip write",
                    cs_id,
                )
                return

            # Merge existing scores with newly computed ones
            image_score = row.image_score
            new_desc = scores_to_write.get(
                "description_score", row.description_score
            )
            new_comp = scores_to_write.get(
                "composition_score", row.composition_score
            )

            if (
                image_score is not None
                and new_desc is not None
                and new_comp is not None
            ):
                scores_to_write["content_total"] = (
                    _W_IMAGE * image_score
                    + _W_DESC * new_desc
                    + _W_COMP * new_comp
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            result = db.execute(
                update(ContentScore)
                .where(ContentScore.id == uuid.UUID(cs_id))
                .values(**scores_to_write)
            )
            if result.rowcount == 0:
                logger.warning(
                    "score_text_content: UPDATE 0 rows for cs_id=%s — deleted?",
                    cs_id,
                )

    except Exception as exc:
        logger.warning(
            "score_text_content: DB error for cs_id=%s (attempt %d): %s",
            cs_id,
            self.request.retries + 1,
            exc,
        )
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    logger.info(
        "score_text_content: done cs_id=%s scores=%s",
        cs_id,
        {k: str(v) for k, v in scores_to_write.items()},
    )
