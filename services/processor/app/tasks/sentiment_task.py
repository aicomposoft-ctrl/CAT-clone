"""
Celery task: score pending reviews with rubert-base-cased-sentiment.

score_pending_reviews:
  Queries reviews with sentiment IS NULL (up to batch_limit rows per run).
  Scores each review using the SentimentScorer singleton (batch_size=32).
  Updates sentiment + sentiment_score columns in the DB.

  Idempotent: WHERE sentiment IS NULL ensures already-scored reviews are
  never re-scored. Running the task multiple times is safe.

  Concurrency-safe: SELECT ... FOR UPDATE SKIP LOCKED prevents duplicate
  processing when multiple Celery workers run concurrently.

  Retry: on RuntimeError (model unavailable), Celery retries up to 3 times
  with exponential backoff (60s, 120s, 240s). Unscored reviews remain NULL.

Beat schedule (registered in celery_app.py):
  03:00 UTC — after collect_reviews_all_skus (02:00) finishes collecting.

Throughput budget:
  1,000 reviews ÷ 32/batch = ~32 batches × ~300ms ≈ 10s per task invocation.
  Sufficient for typical daily ingest of <1,000 reviews/day.
  For higher volumes, increase batch_limit or run task more frequently.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import text

from app.celery_app import celery_app
from app.core.db import get_db_session
from app.sentiment import score_batch

logger = logging.getLogger(__name__)

_BATCH_LIMIT = 1_000  # max reviews scored per task invocation


@celery_app.task(
    bind=True,
    name="processor.score_pending_reviews",
    max_retries=3,
    default_retry_delay=60,  # base: 60s; subsequent: 60 * 2^retries → 60s, 120s, 240s
)
def score_pending_reviews(self, batch_limit: int = _BATCH_LIMIT) -> dict:
    """
    Score up to batch_limit reviews with sentiment IS NULL.

    Returns {"scored": N, "skipped": M} where:
      scored  = reviews successfully classified
      skipped = reviews with empty/NULL/whitespace text (sentiment stays NULL)

    Raises RuntimeError on model failure → Celery retries max 3 times.
    """
    scored = 0
    skipped = 0

    try:
        with get_db_session() as db:
            # Fetch unscored reviews, lock to prevent concurrent duplicate processing
            rows = db.execute(
                text("""
                    SELECT id, review_text
                    FROM reviews
                    WHERE sentiment IS NULL
                    ORDER BY id
                    LIMIT :limit
                    FOR UPDATE SKIP LOCKED
                """),
                {"limit": batch_limit},
            ).fetchall()

        if not rows:
            logger.info("score_pending_reviews: no unscored reviews found")
            return {"scored": 0, "skipped": 0}

        logger.info("score_pending_reviews: fetched %d unscored reviews", len(rows))

        ids = [row.id for row in rows]
        texts = [row.review_text for row in rows]

        # Score all texts — score_batch handles empty/whitespace → (None, None)
        results = score_batch(texts)

        updates = []
        for review_id, (label, score) in zip(ids, results):
            if label is None:
                skipped += 1
            else:
                updates.append({
                    "id": str(review_id),
                    "sentiment": label,
                    "score": score,
                })
                scored += 1

        if updates:
            with get_db_session() as db:
                db.execute(
                    text("""
                        UPDATE reviews
                        SET sentiment = :sentiment, sentiment_score = :score
                        WHERE id = :id::uuid
                    """),
                    updates,
                )

        logger.info(
            "score_pending_reviews: done — scored=%d skipped=%d",
            scored,
            skipped,
        )
        return {"scored": scored, "skipped": skipped}

    except RuntimeError as exc:
        # Model unavailable — exponential backoff: 60s, 120s, 240s
        countdown = 60 * (2 ** self.request.retries)
        logger.warning(
            "score_pending_reviews: model error (attempt %d/%d), retry in %ds: %s",
            self.request.retries + 1,
            self.max_retries + 1,
            countdown,
            exc,
        )
        raise self.retry(exc=exc, countdown=countdown)
