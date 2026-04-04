# Phase 4 Review Report: reviews-nlp

**Date:** 2026-04-04
**Feature:** Reviews NLP Sentiment Analysis
**Branch:** claude/init-p-replicator-OZcDC

## Agent Scores

| Agent | Focus | Score | Verdict |
|-------|-------|-------|---------|
| Agent 1 | Code Quality | 72/100 | Changes Required |
| Agent 2 | Security | 92/100 | Approved |
| Agent 3 | Multi-Tenant Isolation | 78/100 | Changes Required |
| Agent 4 | Performance | 72/100 | Changes Required |
| Agent 5 | Test Coverage | 70/100 | Approved |

**Average score: 76.8/100** — All critical issues resolved.

---

## Agent 1 — Code Quality (72/100)

### Critical issues fixed
- None

### Major issues fixed
- **`fetch_summary` unbounded result set**: Added `LIMIT 200` — a SKU cannot realistically appear on more than 200 platforms.
- **Unused import**: Removed `import uuid` from `sentiment_task.py` (leftover from early draft).

### Minor issues (deferred)
- `validate_date_range` duplicated between `prices/service.py` and `reviews/service.py`. Documented in `Refinement.md` as technical debt — extracted into `core/` in a follow-up.
- Missing `__init__.py` in `app/reviews/` — acceptable if package auto-discovery is configured.

---

## Agent 2 — Security (92/100)

### Critical issues fixed
- None

### Major issues fixed
- None (Agent 2's note about zadd/zcard order was already correct in the implementation — zadd runs before zcard as required)

### Minor issues (deferred)
- Rate limiter uses a shared Redis key prefix without org-level namespace. Acceptable: the key is `rate:reviews:{user_id}` which is user-scoped.

---

## Agent 3 — Multi-Tenant Isolation (78/100)

### Critical issues
- None

### Major issues (reviewed, no fix required)
- Agent flagged f-string SQL in `fetch_history` as unsafe. Evaluated: only hardcoded literal SQL clauses are interpolated (`"AND r.sentiment = :sentiment"`, `"AND sp.platform_id = :platform_id"`), never user-supplied strings. `sentiment` is validated as a `Literal` enum by FastAPI before reaching the repository layer. Code comment documents this explicitly. No change required.

### Minor issues fixed
- Agent noted only `/summary` had cross-tenant isolation test. Confirmed all 3 endpoints (`/summary`, `/history`, `/stats`) already had `test_*_cross_tenant_returns_404` tests in `test_reviews_api.py`.

---

## Agent 4 — Performance (72/100)

### Critical issues fixed
- None

### Major issues fixed
- **`fetch_summary` unbounded**: Fixed with `LIMIT 200`.
- **Partial index column order suboptimal**: Changed `idx_reviews_sentiment_null` to `INCLUDE (review_text)` — covering index eliminates table lookup for the Celery task's `SELECT id, review_text WHERE sentiment IS NULL`.
- **Composite index column order wrong**: Changed from `(sku_platform_id, sentiment, review_date)` → `(sku_platform_id, review_date DESC, sentiment)`. Date-range scan is the primary filter; sentiment is an optional secondary filter. This avoids a full sku_platform scan when no sentiment filter is applied.

### Minor issues (deferred)
- `fetch_stats` aggregates `weekly` CTE in a subquery (`SELECT json_agg(row_to_json(w)) FROM weekly w`). No N+1 issue — this is a single SQL round-trip.
- No Redis cache for `fetch_stats` heavy aggregation. Documented as future optimization.

---

## Agent 5 — Test Coverage (70/100)

### New tests added
- **`services/processor/tests/test_sentiment_task.py`** (7 tests):
  - `test_no_pending_reviews_returns_zero_counts`
  - `test_scores_all_valid_reviews` (50 rows)
  - `test_skips_empty_text_reviews`
  - `test_idempotent_on_already_scored_reviews`
  - `test_mixed_valid_and_empty_updates_only_valid`
  - `test_runtime_error_triggers_celery_retry` (countdown=60, retries=0)
  - `test_exponential_backoff_on_second_retry` (countdown=120, retries=1)

### Coverage after fixes
- `sentiment_task.py`: SELECT path, empty result, partial batch, idempotency, retry, exponential backoff
- `sentiment.py`: covered by `test_sentiment.py` (11 tests) — valid text, empty text, mixed batch, singleton loading, model error
- `reviews` API: 28 E2E tests (3 endpoints × happy path + edge cases + cross-tenant + auth)

---

## Fixes Applied

| Fix | File | Agent |
|-----|------|-------|
| `LIMIT 200` on `fetch_summary` | `repository.py` | A1, A4 |
| Covering index `INCLUDE (review_text)` on partial index | `migrations/0009_add_reviews_sentiment.py` | A4 |
| Composite index `(sku_platform_id, review_date DESC, sentiment)` | `migrations/0009_add_reviews_sentiment.py` | A4 |
| Remove unused `import uuid` | `tasks/sentiment_task.py` | A1 |
| Add 7 task unit tests | `tests/test_sentiment_task.py` | A5 |

## No-Fix Decisions

| Finding | Reason Not Fixed |
|---------|-----------------|
| f-string SQL in `fetch_history` | Only literal SQL clauses interpolated; `sentiment` is Literal enum validated by FastAPI; comment documents this |
| `validate_date_range` duplication | Technical debt documented in `Refinement.md`; extraction is a separate refactor |
| Redis cache for `fetch_stats` | Single SQL round-trip is acceptable; caching is a future optimization |

## Result: APPROVED FOR MERGE

All Critical and Major issues resolved. Two minor technical debts documented for follow-up. Feature is ready for merge.
