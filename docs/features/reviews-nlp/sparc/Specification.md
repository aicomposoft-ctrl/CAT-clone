# Specification — Reviews NLP

**Feature:** Reviews NLP Sentiment Analysis
**SPARC Phase:** Specification (Phase 3)

---

## 1. API Contracts

### GET /api/v1/reviews/summary

**Purpose:** Per-platform sentiment breakdown for a SKU.

**Query Parameters:**

| Param | Type | Required | Constraint | Default |
|-------|------|----------|------------|---------|
| sku_id | UUID | ✅ | must belong to caller's org | — |
| date_from | date | ❌ | ≤ date_to | today − 30 days |
| date_to | date | ❌ | ≥ date_from, ≤ today | today |

**Response 200:**
```json
{
  "sku_id": "uuid",
  "date_from": "2026-03-04",
  "date_to": "2026-04-03",
  "total": 87,
  "items": [
    {
      "platform_id": "uuid",
      "platform_name": "Wildberries",
      "review_count": 52,
      "avg_rating": 4.2,
      "positive_count": 38,
      "neutral_count": 9,
      "negative_count": 5,
      "positive_pct": 73.1,
      "neutral_pct": 17.3,
      "negative_pct": 9.6,
      "last_review_date": "2026-04-01"
    }
  ]
}
```

**Errors:**
- 401 — unauthenticated
- 404 — SKU not found or belongs to other org
- 422 — invalid date range

---

### GET /api/v1/reviews/history

**Purpose:** Paginated individual reviews with sentiment.

**Query Parameters:**

| Param | Type | Required | Constraint | Default |
|-------|------|----------|------------|---------|
| sku_id | UUID | ✅ | — | — |
| platform_id | UUID | ❌ | — | all platforms |
| sentiment | Literal["positive","neutral","negative"] | ❌ | enum | all |
| date_from | date | ❌ | ≤ date_to | today − 30 days |
| date_to | date | ❌ | — | today |
| limit | int | ❌ | 1 ≤ limit ≤ 500 | 100 |
| offset | int | ❌ | ≥ 0 | 0 |

**Response 200:**
```json
{
  "sku_id": "uuid",
  "total": 87,
  "limit": 100,
  "offset": 0,
  "items": [
    {
      "id": "uuid",
      "platform_id": "uuid",
      "platform_name": "Ozon",
      "review_text": "Отличное качество!",
      "rating": 5,
      "sentiment": "positive",
      "sentiment_score": 0.94,
      "review_date": "2026-04-01"
    }
  ]
}
```

**Errors:** same as /summary plus 422 on invalid sentiment literal.

---

### GET /api/v1/reviews/stats

**Purpose:** Aggregated statistics with weekly trend.

**Query Parameters:** same as /summary.

**Response 200:**
```json
{
  "sku_id": "uuid",
  "date_from": "2026-03-04",
  "date_to": "2026-04-03",
  "review_count": 87,
  "avg_rating": 4.1,
  "rating_distribution": {"1": 2, "2": 3, "3": 8, "4": 24, "5": 50},
  "sentiment_share": {
    "positive": 0.71,
    "neutral": 0.18,
    "negative": 0.11
  },
  "weekly_trend": [
    {"week_start": "2026-03-30", "positive_share": 0.78, "avg_rating": 4.4, "review_count": 12}
  ]
}
```

---

## 2. Data Model

### Migration 0009 — Add sentiment columns to reviews

```sql
ALTER TABLE reviews
  ADD COLUMN sentiment VARCHAR(20) CHECK (sentiment IN ('positive', 'neutral', 'negative')),
  ADD COLUMN sentiment_score DECIMAL(4, 3);

-- Index for filtering unscored rows (Celery task query)
CREATE INDEX idx_reviews_sentiment_null ON reviews (id) WHERE sentiment IS NULL;

-- Index for summary query: GROUP BY sku_platform_id + sentiment + review_date range
CREATE INDEX idx_reviews_sp_sentiment ON reviews (sku_platform_id, sentiment, review_date);
```

Note: Both columns are nullable — reviews collected before this migration remain `sentiment IS NULL`
until the backfill Celery task runs.

---

## 3. Sentiment Model

**Model:** `blanchefort/rubert-base-cased-sentiment` (HuggingFace)
- Input: Russian review text (max 512 tokens, truncation on overflow)
- Output: probabilities for `POSITIVE`, `NEUTRAL`, `NEGATIVE`
- Label mapping: `POSITIVE` → `"positive"`, `NEGATIVE` → `"negative"`, `NEUTRAL` → `"neutral"`
- `sentiment` = argmax label, `sentiment_score` = argmax probability
- Batch size: 32 (balances GPU memory and throughput)

**Scoring rules:**
- Empty or NULL text → skip (sentiment stays NULL, no error)
- Text > 512 tokens → truncate (tokenizer `truncation=True`)
- Model unavailable → raise `RuntimeError` (Celery retries)

---

## 4. Tenant Isolation

Reviews have no direct `org_id` column. Isolation is enforced via JOIN chain:
```
reviews.sku_platform_id → sku_platforms.sku_id → skus.org_id
```

Two-gate pattern (same as prices):
1. Router gate: `SKURepository.get_by_id_and_org(db, sku_id, org_id)` → 404 if mismatch
2. Repository defence-in-depth: all queries JOIN to skus with `s.org_id = :org_id AND s.id = :sku_id`

---

## 5. Non-Functional Requirements

| NFR | Requirement |
|-----|-------------|
| Performance | GET /summary and /stats < 200ms p95 on 10k reviews |
| Throughput | score_pending_reviews: ≥ 1,000 reviews/min |
| Availability | API endpoints available without ML model (null sentiment is OK) |
| Idempotency | Running score_pending_reviews multiple times is safe |
| Rate limiting | 60 req/min per user (shared Redis sliding window, same as prices) |
| Max date range | 366 days (consistent with prices domain) |

---

## 6. BDD Scenarios

### Scenario: Summary returns per-platform breakdown
```gherkin
Given manager_a has a SKU with 10 reviews on WB (7 positive, 2 neutral, 1 negative) and
  5 reviews on Ozon (5 positive)
When GET /api/v1/reviews/summary?sku_id=<id>
Then HTTP 200
And items has 2 entries
And WB entry has positive_pct=70.0, negative_pct=10.0, avg_rating present
And Ozon entry has positive_pct=100.0, review_count=5
```

### Scenario: Cross-tenant isolation
```gherkin
Given manager_b authenticates with org_b JWT
When GET /api/v1/reviews/summary?sku_id=<org_a_sku_id>
Then HTTP 404 with detail="SKU_NOT_FOUND"
```

### Scenario: History with sentiment filter
```gherkin
Given a SKU has 20 reviews: 12 positive, 5 neutral, 3 negative
When GET /api/v1/reviews/history?sku_id=<id>&sentiment=negative
Then HTTP 200
And total=3 and items has 3 entries
And each item has sentiment="negative"
```

### Scenario: Stats weekly trend
```gherkin
Given reviews span 14 days across 2 calendar weeks
When GET /api/v1/reviews/stats?sku_id=<id>
Then HTTP 200 with weekly_trend having 2 entries
And each entry has week_start, positive_share, avg_rating, review_count
```

### Scenario: Celery task scores pending reviews
```gherkin
Given 50 reviews exist with sentiment IS NULL
When score_pending_reviews task runs
Then all 50 reviews have non-null sentiment and sentiment_score
And task return value includes {"scored": 50, "skipped": 0}
```

### Scenario: Empty text skipped by scorer
```gherkin
Given one review has review_text="" (empty string)
When score_pending_reviews task runs
Then that review is skipped
And task return value includes {"skipped": 1}
```

### Scenario: Date range > 366 days rejected
```gherkin
Given date_from=2025-01-01, date_to=2026-06-01 (> 366 days)
When GET /api/v1/reviews/summary?sku_id=<id>&date_from=...&date_to=...
Then HTTP 422 with message containing "366"
```
