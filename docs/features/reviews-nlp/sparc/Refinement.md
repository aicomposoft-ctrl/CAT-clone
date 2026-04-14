# Refinement — Reviews NLP

**Feature:** Reviews NLP Sentiment Analysis
**SPARC Phase:** Refinement (Phase 6)

---

## 1. Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| rubert model not downloaded in Docker | Medium | High | Pre-download in Dockerfile RUN step; verify in CI |
| Large backfill blocks daily scraping | Low | Medium | `SELECT ... FOR UPDATE SKIP LOCKED`; limit=1000 per task |
| Rating distribution nulls if r1-r5 all 0 | Low | Low | Default to 0 in Python, not DB |
| sentiment_share = None confuses frontend | Medium | Low | Document in schema — means "reviews not yet scored" |
| date_trunc('week') week boundary ambiguity | Low | Low | ISO week (Monday start) consistent with PostgreSQL default |
| Cross-domain validate_date_range duplication | Low | Low | 3-line function, acceptable duplication over coupling |
| `text-classification` pipeline API change | Low | Low | Pin transformers version in requirements.txt |

---

## 2. Edge Case Matrix

| Scenario | Input | Expected | Handling |
|----------|-------|----------|----------|
| All reviews unscored | sentiment IS NULL for all | summary/stats return 0 for all sentiment counts | SQL FILTER returns 0 |
| Review text is NULL | NULL in DB | skip (NULL stays) | score_batch guard |
| Review text is empty string | "" | skip (NULL stays) | `text.strip()` guard |
| Review text has only spaces | "   " | skip | `text.strip()` guard |
| SKU with 0 reviews | No rows in DB | 200, total=0, items=[] | repository returns [] |
| Only one platform | 1 platform in reviews | summary.items has 1 entry | GROUP BY works with 1 group |
| Week boundary crossing | Reviews span Mon and Sun | 2 weekly entries | date_trunc('week') splits correctly |
| date_from = date_to | Same date | Single-day range, valid | BETWEEN is inclusive both ends |
| offset > total results | offset=1000 on 5 reviews | 200, items=[] | SQL LIMIT/OFFSET returns empty |
| limit=500 exactly | boundary | 200, works | le=500 constraint |
| limit=501 | over boundary | 422 | FastAPI Query validator |
| limit=0 | zero | 422 | ge=1 constraint |
| negative_pct = 100 - positive_pct - neutral_pct | rounding might exceed 100 | clamped at 0 | subtraction from 100 prevents overshoot |

---

## 3. Testing Strategy

### Unit Tests
- `SentimentScorer.score_batch` with mocked HuggingFace pipeline
  - normal text → correct label/score
  - empty string → (None, None)
  - whitespace-only → (None, None)
  - batch of 32 exactly + overflow to 33
- `validate_date_range` (identical tests to prices domain)
- `get_review_summary` pct calculation (zero reviews → no ZeroDivision)
- `get_review_stats` with null weekly_trend JSON

### E2E Tests (SQLite + service mocks)
- GET /summary: normal response, empty, cross-tenant 404, date 422, unauthenticated 401
- GET /history: normal, sentiment filter, limit/offset, limit boundary 422, cross-tenant 404
- GET /stats: all fields, null stats (no reviews), date 422
- Rate limit mock (same pattern as prices tests)

### Integration Tests (PostgreSQL required)
- `score_pending_reviews` task against real DB
- FILTER aggregate syntax (PostgreSQL-only)
- `weekly_trend` JSON aggregation
- `SELECT ... FOR UPDATE SKIP LOCKED` concurrency

### Cross-Tenant Mandatory Test
```python
async def test_all_endpoints_return_404_for_foreign_sku(client, manager_b, sku_a):
    endpoints = [
        f"/api/v1/reviews/summary?sku_id={sku_a.id}",
        f"/api/v1/reviews/history?sku_id={sku_a.id}",
        f"/api/v1/reviews/stats?sku_id={sku_a.id}",
    ]
    for url in endpoints:
        resp = await client.get(url, headers=_auth(manager_b))
        assert resp.status_code == 404
        assert resp.json()["detail"] == "SKU_NOT_FOUND"
```

---

## 4. Performance Considerations

### API Queries
- `idx_reviews_sp_sentiment` covers: `(sku_platform_id, sentiment, review_date)` — used by
  summary (GROUP BY) and history (filter) queries
- `idx_reviews_sp_date` from migration 0003 covers history ORDER BY review_date DESC
- For summary: PostgreSQL FILTER aggregate avoids multiple passes over data

### Celery Task
- `SELECT ... FOR UPDATE SKIP LOCKED` prevents duplicate scoring on concurrent workers
- Batch commit every 32 rows (per score_batch call) — limits transaction size
- `idx_reviews_sentiment_null` partial index makes the WHERE sentinel IS NULL fast
- 1,000 reviews/task × daily = sufficient catch-up for typical ingest volumes

### Model Loading
- Singleton `_SCORER` loaded once per process — ~2-5s warmup amortized over hundreds of batches
- CPU inference for 32 texts ≈ 200-500ms depending on text length
- 1,000 reviews ÷ 32/batch = 32 batches × ~300ms ≈ 10s per task (comfortably within 30-min budget)

---

## 5. Security Hardening

- Sentiment literal is validated as `Literal["positive","neutral","negative"]` by FastAPI
  before reaching repository — f-string injection impossible
- org_id filter on all repository queries (defence-in-depth)
- SKU ownership check at router level (HTTP 404, not 403 — avoids org existence leak)
- Rate limiting: 60 req/min per user (Redis sliding window)
- No PII in logs (review_text not logged, only IDs and counts)

---

## 6. Dependency Notes

- `transformers` must be in `services/processor/requirements.txt`, not in `services/api/`
  (API does not do ML inference — only reads from DB)
- `torch` CPU version in processor container (~700MB) — already included for CLIP
- Pin: `transformers>=4.35.0` (pipeline API stable)
- Pin: `torch>=2.0.0,<3.0.0`

---

## 7. Technical Debt

| Item | Priority | Notes |
|------|----------|-------|
| Total count query for /history | Low | Currently returns len(items), not count of all matching. Fix in v1.1 with COUNT(*) subquery |
| Competitor review monitoring | Future | Same schema, different org_id path — add competitor flag to SKU |
| ClickHouse reviews time-series | Future | For fast aggregation at brand/category level |
| Topic extraction | Future | LDA or KeyBERT on review clusters |
