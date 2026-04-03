# Architecture — Reviews NLP

**Feature:** Reviews NLP Sentiment Analysis
**SPARC Phase:** Architecture (Phase 5)

---

## 1. Component Map

```
services/api/app/reviews/
├── __init__.py
├── models.py          ← Review ORM (extend_existing=True, adds sentiment fields)
├── schemas.py         ← Pydantic: ReviewHistoryItem, ReviewSummaryItem, ReviewStats, etc.
├── repository.py      ← Raw SQL: fetch_summary, fetch_history, fetch_stats
└── router.py          ← /summary, /history, /stats endpoints + rate limit + SKU gate

services/processor/app/
└── sentiment.py       ← SentimentScorer singleton + score_batch()

services/collector/app/tasks/
└── reviews_task.py    ← score_pending_reviews Celery task (calls processor via import or HTTP)

infrastructure/postgres/migrations/
└── 0009_add_reviews_sentiment.py  ← ALTER TABLE reviews ADD COLUMN sentiment, sentiment_score
```

---

## 2. Data Flow

```
Collector (Scrapy/Playwright)
        │
        ▼
  reviews table (sentiment IS NULL, sentiment_score IS NULL)
        │
        ▼
  Celery Beat (daily 03:00 or after collect_reviews_all_skus completes)
        │
        ▼
  score_pending_reviews task
        │
  SELECT id, review_text FROM reviews WHERE sentiment IS NULL LIMIT 1000
        │ (batches of 32)
        ▼
  SentimentScorer.score_batch(texts)
  → rubert-base-cased-sentiment (HuggingFace pipeline)
  → [(label, score), ...]
        │
  UPDATE reviews SET sentiment=?, sentiment_score=? WHERE id=?
        │
        ▼
  All reviews have sentiment populated
        │
        ▼
  FastAPI endpoints read from reviews table
```

---

## 3. ORM Model

```python
# services/api/app/reviews/models.py
class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    sku_platform_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sku_platforms.id", ondelete="CASCADE"), nullable=False)
    external_review_id: Mapped[str] = mapped_column(String(255), nullable=False)
    review_text: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    review_date: Mapped[date] = mapped_column(Date, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Added by migration 0009:
    sentiment: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sentiment_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
```

---

## 4. Repository SQL Patterns

### fetch_summary — GROUP BY platform, sentiment
```sql
SELECT
    sp.platform_id,
    p.name              AS platform_name,
    COUNT(*)            AS review_count,
    ROUND(AVG(r.rating)::numeric, 2) AS avg_rating,
    COUNT(*) FILTER (WHERE r.sentiment = 'positive') AS positive_count,
    COUNT(*) FILTER (WHERE r.sentiment = 'neutral')  AS neutral_count,
    COUNT(*) FILTER (WHERE r.sentiment = 'negative') AS negative_count,
    MAX(r.review_date)  AS last_review_date
FROM reviews r
JOIN sku_platforms sp ON sp.id = r.sku_platform_id
JOIN platforms p      ON p.id = sp.platform_id
JOIN skus s           ON s.id = sp.sku_id
WHERE s.org_id = :org_id
  AND s.id = :sku_id
  AND r.review_date BETWEEN :date_from AND :date_to
GROUP BY sp.platform_id, p.name
ORDER BY review_count DESC
```
Uses: `idx_reviews_sp_sentiment` (sku_platform_id, sentiment, review_date)

### fetch_history — paginated with optional filters
```sql
SELECT r.id, sp.platform_id, p.name AS platform_name,
       r.review_text, r.rating, r.sentiment, r.sentiment_score, r.review_date
FROM reviews r
JOIN sku_platforms sp ON sp.id = r.sku_platform_id
JOIN platforms p      ON p.id  = sp.platform_id
JOIN skus s           ON s.id  = sp.sku_id
WHERE s.org_id = :org_id
  AND s.id     = :sku_id
  AND r.review_date BETWEEN :date_from AND :date_to
  {sentiment_clause}   -- AND r.sentiment = :sentiment (if provided)
  {platform_clause}    -- AND sp.platform_id = :platform_id (if provided)
ORDER BY r.review_date DESC
LIMIT :limit OFFSET :offset
```

### fetch_stats — aggregates + weekly trend via generate_series
```sql
WITH range_data AS (
    SELECT r.rating, r.sentiment, r.review_date
    FROM reviews r
    JOIN sku_platforms sp ON sp.id = r.sku_platform_id
    JOIN skus s ON s.id = sp.sku_id
    WHERE s.org_id = :org_id AND s.id = :sku_id
      AND r.review_date BETWEEN :date_from AND :date_to
),
weekly AS (
    SELECT
        date_trunc('week', review_date::timestamp)::date AS week_start,
        ROUND(AVG(rating)::numeric, 2) AS avg_rating,
        COUNT(*) AS review_count,
        ROUND(COUNT(*) FILTER (WHERE sentiment = 'positive')::numeric / NULLIF(COUNT(*), 0), 4) AS positive_share
    FROM range_data
    GROUP BY 1
    ORDER BY 1
)
SELECT
    COUNT(*)                                                              AS review_count,
    ROUND(AVG(rating)::numeric, 2)                                        AS avg_rating,
    COUNT(*) FILTER (WHERE rating = 1)                                    AS r1,
    COUNT(*) FILTER (WHERE rating = 2)                                    AS r2,
    COUNT(*) FILTER (WHERE rating = 3)                                    AS r3,
    COUNT(*) FILTER (WHERE rating = 4)                                    AS r4,
    COUNT(*) FILTER (WHERE rating = 5)                                    AS r5,
    ROUND(COUNT(*) FILTER (WHERE sentiment = 'positive')::numeric / NULLIF(COUNT(*), 0), 4) AS positive_share,
    ROUND(COUNT(*) FILTER (WHERE sentiment = 'neutral')::numeric  / NULLIF(COUNT(*), 0), 4) AS neutral_share,
    ROUND(COUNT(*) FILTER (WHERE sentiment = 'negative')::numeric / NULLIF(COUNT(*), 0), 4) AS negative_share,
    (SELECT json_agg(row_to_json(w)) FROM weekly w)                       AS weekly_trend
FROM range_data
```
Single SQL round-trip. `FILTER (WHERE ...)` is PostgreSQL 9.4+ aggregate extension.

---

## 5. SentimentScorer (processor service)

```python
# services/processor/app/sentiment.py

from __future__ import annotations
from typing import Sequence
from transformers import pipeline

_SCORER: pipeline | None = None
_MODEL_NAME = "blanchefort/rubert-base-cased-sentiment"
_LABEL_MAP = {"POSITIVE": "positive", "NEGATIVE": "negative", "NEUTRAL": "neutral"}

def get_scorer() -> pipeline:
    """Lazy singleton — model loads once per process, reused for all batches."""
    global _SCORER
    if _SCORER is None:
        _SCORER = pipeline(
            "text-classification",
            model=_MODEL_NAME,
            truncation=True,
            max_length=512,
            top_k=1,
            device=-1,          # CPU; change to 0 for GPU
        )
    return _SCORER


def score_batch(texts: Sequence[str]) -> list[tuple[str, float]]:
    """
    Score a list of texts. Returns [(label, score), ...] parallel to input.

    Empty/whitespace-only texts return (None, None) — caller must handle.
    """
    scorer = get_scorer()
    results = []
    batch = []
    indices = []

    for i, text in enumerate(texts):
        if text and text.strip():
            batch.append(text)
            indices.append(i)
        else:
            results.append((None, None))

    if batch:
        preds = scorer(batch, batch_size=32)
        batch_results = [(
            _LABEL_MAP[p[0]["label"]],
            round(p[0]["score"], 3)
        ) for p in preds]
        # Re-merge with None placeholders
        batch_iter = iter(batch_results)
        final = [(None, None)] * len(texts)
        for idx in indices:
            final[idx] = next(batch_iter)
        return final

    return results
```

---

## 6. Celery Task Design

```python
# services/collector/app/tasks/reviews_task.py

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def score_pending_reviews(self, batch_limit: int = 1000):
    """
    Score up to batch_limit reviews with sentiment IS NULL.

    Returns {"scored": N, "skipped": M} where skipped = empty-text reviews.

    Retry semantics: on RuntimeError (model unavailable), Celery retries 3×
    with exponential backoff (60s, 120s, 240s). Scored reviews are committed
    per sub-batch of 32 to limit transaction size.
    """
    ...
```

**Key design decisions:**
- Batch commit every 32 rows (not one transaction for all 1000) — limits lock time
- `LIMIT 1000` per task invocation — repeated daily runs catch up over time
- `SELECT ... FOR UPDATE SKIP LOCKED` prevents duplicate processing on concurrent workers
- Task scheduled via Celery Beat: `0 3 * * *` (03:00 daily, after collect_reviews_all_skus at 02:00)

---

## 7. Indexes

Migration 0009 adds:
```sql
-- For Celery task: find unscored rows quickly
CREATE INDEX idx_reviews_sentiment_null ON reviews (id) WHERE sentiment IS NULL;

-- For API summary/history: (sku_platform_id, sentiment, review_date) covers all 3 endpoints
CREATE INDEX idx_reviews_sp_sentiment ON reviews (sku_platform_id, sentiment, review_date);
```

Existing indexes from migration 0003:
- `idx_reviews_sp` on `(sku_platform_id)` — general FK lookup
- `idx_reviews_date` on `(review_date)` — date range scans
- `idx_reviews_sp_date` on `(sku_platform_id, review_date DESC)` — history queries

---

## 8. Rate Limiting

Reuse `_enforce_rate_limit` pattern from prices domain:
- 60 req/min per user via Redis sorted set
- No-op when REDIS_URL is unset (dev/test)
- Graceful degradation on Redis failure

---

## 9. Deployment Notes

- `rubert-base-cased-sentiment` (~700MB): pre-download to Docker volume at build time
  ```dockerfile
  RUN python -c "from transformers import pipeline; pipeline('text-classification', model='blanchefort/rubert-base-cased-sentiment')"
  ```
- Processor service CPU: 2 vCPU minimum for acceptable throughput
- Model is loaded once per worker process (singleton) — Celery concurrency=4 → 4 model instances
