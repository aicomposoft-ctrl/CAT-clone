# Pseudocode — Reviews NLP

**Feature:** Reviews NLP Sentiment Analysis
**SPARC Phase:** Pseudocode (Phase 4)

---

## 1. Schemas

```python
# ReviewHistoryItem
class ReviewHistoryItem(BaseModel):
    id: UUID
    platform_id: UUID
    platform_name: str
    review_text: str
    rating: int           # 1-5
    sentiment: str | None  # "positive" | "neutral" | "negative" | None (unscored)
    sentiment_score: Decimal | None  # 0.000–1.000
    review_date: date

# ReviewSummaryItem (per platform)
class ReviewSummaryItem(BaseModel):
    platform_id: UUID
    platform_name: str
    review_count: int
    avg_rating: Decimal
    positive_count: int
    neutral_count: int
    negative_count: int
    positive_pct: Decimal  # 0.0–100.0
    neutral_pct: Decimal
    negative_pct: Decimal
    last_review_date: date | None

# ReviewSummaryResponse
class ReviewSummaryResponse(BaseModel):
    sku_id: UUID
    date_from: date
    date_to: date
    total: int           # sum of all review_count across platforms
    items: list[ReviewSummaryItem]

# ReviewHistoryResponse
class ReviewHistoryResponse(BaseModel):
    sku_id: UUID
    total: int
    limit: int
    offset: int
    items: list[ReviewHistoryItem]

# SentimentShare
class SentimentShare(BaseModel):
    positive: Decimal
    neutral: Decimal
    negative: Decimal

# WeeklyTrendItem
class WeeklyTrendItem(BaseModel):
    week_start: date
    positive_share: Decimal
    avg_rating: Decimal
    review_count: int

# ReviewStats
class ReviewStats(BaseModel):
    sku_id: UUID
    date_from: date
    date_to: date
    review_count: int
    avg_rating: Decimal | None
    rating_distribution: dict[str, int]  # {"1": N, "2": N, ...}
    sentiment_share: SentimentShare | None
    weekly_trend: list[WeeklyTrendItem]
```

---

## 2. Repository Functions

### fetch_summary(db, org_id, sku_id, date_from, date_to) → list[Row]

```
INPUT: db session, org_id UUID, sku_id UUID, date_from date, date_to date
OUTPUT: list of rows with (platform_id, platform_name, review_count, avg_rating,
        positive_count, neutral_count, negative_count, last_review_date)

STEPS:
1. Build SQL with:
   - JOIN chain: reviews → sku_platforms → platforms → skus
   - WHERE s.org_id = :org_id AND s.id = :sku_id
   - AND r.review_date BETWEEN :date_from AND :date_to
   - COUNT(*) FILTER (WHERE sentiment = 'positive') etc
   - GROUP BY platform_id, platform_name
   - ORDER BY review_count DESC
2. Execute with params {org_id, sku_id, date_from, date_to}
3. RETURN result.all()
```

### fetch_history(db, org_id, sku_id, platform_id, sentiment, date_from, date_to, limit, offset) → list[Row]

```
INPUT: db session + filters
OUTPUT: list of review rows with pagination

STEPS:
1. Build optional clauses:
   - sentiment_clause = "AND r.sentiment = :sentiment" if sentiment else ""
   - platform_clause = "AND sp.platform_id = :platform_id" if platform_id else ""
2. Build SQL with f-string (literal clauses only — safe)
3. params = {org_id, sku_id, date_from, date_to, limit, offset}
4. IF sentiment: params["sentiment"] = sentiment
5. IF platform_id: params["platform_id"] = platform_id
6. RETURN result.all()

NOTE: f-string is safe — only literal SQL clauses are interpolated.
Sentiment is validated as Literal enum in router before reaching repository.
```

### fetch_stats(db, org_id, sku_id, date_from, date_to) → Row | None

```
INPUT: db session + date range
OUTPUT: single row with (review_count, avg_rating, r1-r5, positive_share,
        neutral_share, negative_share, weekly_trend JSON)

STEPS:
1. Build CTE-based SQL with:
   - range_data CTE: filtered reviews for the period
   - weekly CTE: date_trunc('week', ...) aggregates
   - Final SELECT: aggregates + json_agg(weekly)
2. Execute and get one_or_none()
3. IF row is None OR row.review_count == 0: RETURN None
4. RETURN row
```

---

## 3. Service Functions

### validate_date_range(date_from, date_to, default_days_back=30, max_range_days=366)

Reuse from `app.prices.service.validate_date_range` — import directly.

Wait: since it's in the prices domain, we should NOT import cross-domain.
Instead, extract to `app.core.utils` or duplicate the small function in `reviews/service.py`.

**Decision:** Duplicate in `reviews/service.py` as `validate_date_range` (identical signature and
behavior). 3 lines of logic. Avoids cross-domain coupling.

### get_review_summary(db, org_id, sku_id, date_from, date_to) → ReviewSummaryResponse

```
INPUT: db session + params (date_from/to already validated by router)
STEPS:
1. rows = await repository.fetch_summary(db, org_id, sku_id, date_from, date_to)
2. items = []
3. FOR row IN rows:
   a. pct denominator = row.review_count if row.review_count > 0 else 1
   b. positive_pct = round(row.positive_count / denominator * 100, 1)
   c. neutral_pct  = round(row.neutral_count  / denominator * 100, 1)
   d. negative_pct = round(100.0 - positive_pct - neutral_pct, 1)  -- avoids rounding drift
   e. items.append(ReviewSummaryItem(...))
4. total = sum(item.review_count for item in items)
5. RETURN ReviewSummaryResponse(sku_id, date_from, date_to, total, items)
```

### get_review_history(db, org_id, sku_id, platform_id, sentiment, date_from, date_to, limit, offset) → ReviewHistoryResponse

```
STEPS:
1. rows = await repository.fetch_history(...)
2. items = [ReviewHistoryItem(...) for row in rows]
3. RETURN ReviewHistoryResponse(sku_id, total=len(items), limit, offset, items)

NOTE: total here is the count of returned items, not total matching.
Full count query adds overhead; for now, caller uses offset+limit pagination.
If len(items) < limit, caller knows they're on the last page.
```

### get_review_stats(db, org_id, sku_id, date_from, date_to) → ReviewStats

```
STEPS:
1. row = await repository.fetch_stats(db, org_id, sku_id, date_from, date_to)
2. IF row is None:
   RETURN ReviewStats(sku_id, date_from, date_to, review_count=0, avg_rating=None,
                      rating_distribution={"1":0,"2":0,"3":0,"4":0,"5":0},
                      sentiment_share=None, weekly_trend=[])
3. rating_distribution = {"1": row.r1, "2": row.r2, ...}
4. IF row.positive_share is not None:
   sentiment_share = SentimentShare(positive=row.positive_share,
                                    neutral=row.neutral_share,
                                    negative=row.negative_share)
5. ELSE:
   sentiment_share = None  -- all reviews unscored
6. weekly_trend = [WeeklyTrendItem(**item) for item in (row.weekly_trend or [])]
7. RETURN ReviewStats(...)
```

---

## 4. Router Handlers

### GET /summary

```
STEPS:
1. await _enforce_rate_limit(current_user.id)
2. await _require_sku_access(sku_id, db, current_user)  -- HTTP 404 on mismatch
3. try:
     date_from, date_to = validate_date_range(date_from, date_to)
   except ValueError as exc:
     raise HTTPException(422, str(exc))
4. RETURN await service.get_review_summary(db, current_user.org_id, sku_id, date_from, date_to)
```

### GET /history

```
STEPS: same pattern + pass sentiment, platform_id, limit, offset to service
NOTE: sentiment=None means no filter (all sentiments returned)
```

### GET /stats

```
STEPS: same as /summary without platform_id filter
```

---

## 5. score_pending_reviews Celery Task

```
FUNCTION score_pending_reviews(batch_limit=1000) → dict:

STEPS:
1. scored = 0, skipped = 0
2. Open DB connection (synchronous SQLAlchemy — Celery tasks are sync)
3. SELECT id, review_text FROM reviews
   WHERE sentiment IS NULL
   ORDER BY id
   LIMIT :batch_limit
   FOR UPDATE SKIP LOCKED
4. IF no rows: RETURN {"scored": 0, "skipped": 0}
5. texts = [row.review_text for row in rows]
6. ids   = [row.id for row in rows]
7. results = sentiment_scorer.score_batch(texts)
   -- returns [(label, score) | (None, None), ...]
8. updates = []
   FOR i, (label, score) IN enumerate(results):
     IF label is None:  -- empty text
       skipped += 1
     ELSE:
       updates.append({"id": ids[i], "sentiment": label, "sentiment_score": score})
       scored += 1
9. IF updates:
   -- Batch UPDATE using executemany / VALUES list
   db.execute(
     "UPDATE reviews SET sentiment=:sentiment, sentiment_score=:score WHERE id=:id",
     updates
   )
   db.commit()
10. RETURN {"scored": scored, "skipped": skipped}

ERROR HANDLING:
  - IF RuntimeError from score_batch (model unavailable):
    raise self.retry(exc=exc, countdown=60 * 2**self.request.retries)
  - IF DB error: rollback + re-raise (Celery marks task FAILURE)
```

---

## 6. Edge Cases

| Case | Handling |
|------|----------|
| Review text = NULL or "" | Skip in score_batch, sentiment stays NULL |
| Review text > 512 tokens | Truncated by tokenizer (truncation=True) |
| All reviews in range unscored | sentiment_share=None in stats, neutral_pct=0 in summary |
| date_from == date_to | Valid — single-day range |
| date_from > date_to | ValueError → HTTP 422 |
| SKU has 0 reviews | HTTP 200, total=0, items=[] |
| platform_id not monitored for sku | Returns empty (JOIN returns no rows) |
| offset > total | HTTP 200, items=[] |
| Model warmup on first call | ~2-5s delay — acceptable for Celery, not for API |
