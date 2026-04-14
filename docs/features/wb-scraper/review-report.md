# Review Report — WB Scraper

**Date:** 2026-03-27
**Phase:** 4 — Code Review (5 parallel agents)
**Result:** All Critical and Major issues fixed. Ready to merge.

---

## Agent Scores

| Agent | Area | Score |
|-------|------|-------|
| Agent 1 | Code Quality | Changes Required → Fixed |
| Agent 2 | Security (OWASP) | Changes Required → Fixed |
| Agent 3 | Multi-tenant Isolation | Changes Required → Fixed |
| Agent 4 | Performance | Changes Required → Fixed |
| Agent 5 | Test Coverage | Changes Required → Fixed |

---

## Critical Issues — Fixed

### C1: `sp.sku.org_id` accessed after session close → `DetachedInstanceError`
**Files:** All 4 task files
**Root cause:** Tasks fetched `SKUPlatform` (ORM object) in one `with get_db_session()` block, then accessed `sp.sku.org_id` (lazy relationship) after the session was closed. SQLAlchemy's default `expire_on_commit=True` means the relationship is expired and raises `DetachedInstanceError` at runtime.
**Fix:** Changed all 4 tasks to extract primitive values `(sp_id, nm_id, org_id)` — or `(sp_id, sku_id, nm_id, org_id)` for the content task — using a tuple column query within the session. No ORM relationship traversal after session close.

### C2: Double-retry in `collect_wb_content`
**File:** `wb_content_task.py`
**Root cause:** Decorator had `autoretry_for=(ScraperError,)` AND the exception handler called `raise self.retry(...)` manually. Two independent retry mechanisms on the same exception = unpredictable retry multiplication.
**Fix:** Removed `autoretry_for=(ScraperError,)`. The manual `self.retry()` in the exception handler handles all retry logic consistently with the other 3 task files.

### C3: Sync `httpx.get()` blocking worker thread for image downloads
**File:** `wb_content_task.py`
**Root cause:** `httpx.get(content.image_url, timeout=30.0)` is a blocking call inside a Celery prefork worker. A 30-second CDN timeout ties up the entire worker process. Also bypassed proxy rotation.
**Fix:** Added `_download_image_async(url, proxy)` async function; image download now uses `asyncio.run(_download_image_async(...))` with proxy from `get_proxy_rotator().next()`.

### C4: Orchestrator missing `Platform.is_active` filter
**File:** `wb_orchestrator.py`
**Root cause:** `_load_wb_sku_platforms` filtered on `Platform.name` and `SKUPlatform.is_monitored` but not `Platform.is_active`. Deactivated platforms would still dispatch tasks.
**Fix:** Added `Platform.is_active.is_(True)` to the query filter.

### C5: Missing PARSE_ERROR test (Specification gap)
**File:** `test_wb_scraper.py`
**Fix:** Added `test_scraper_raises_parse_error_on_null_data` — sends `{"data": null}` and asserts `ScraperError("PARSE_ERROR")`.

### C6: No cross-tenant isolation test (mandatory per testing rules)
**File:** `test_wb_tasks.py`
**Fix:** Added `TestCollectWbContent.test_cross_tenant_isolation` — verifies the content score written uses `sp_a_id`, not `sp_b_id`.

### C7: `collect_wb_stock` API_UNAVAILABLE path had no test (no DB write verification)
**File:** `test_wb_tasks.py`
**Fix:** Added `TestCollectWbStock.test_api_unavailable_no_db_write`.

---

## Major Issues — Fixed

### M1: Reviews task — N+1 INSERT loop
**Fix:** Replaced per-review `db.execute()` loop with a single bulk `pg_insert(Review).values([...]).on_conflict_do_nothing()`.

### M2: Orchestrator loaded full ORM objects into memory
**Fix:** Changed `_load_wb_sku_platforms()` to select only `SKUPlatform.id` column and return `list[str]`. Full ORM objects no longer held in orchestrator memory.

### M3: `_build_image_url` crashes on non-numeric `nm_id`
**Fix:** Added `try/except ValueError` around `int(nm_id)` — raises `ScraperError("PARSE_ERROR")` instead.

### M4: Missing composite index on `price_snapshots(sku_platform_id, collected_at)`
**Fix:** Added `CREATE INDEX idx_price_snapshots_sp_time ON price_snapshots (sku_platform_id, collected_at DESC)` in migration 0003. Removed redundant single-column indexes on that table.

### M5: `sanitize()` HTML regex doesn't match multiline tags
**Fix:** Added `re.DOTALL` flag to `_HTML_TAG_RE`. Multiline tags like `<script\ntype=...>` are now stripped.

### M6: Missing tests — empty `sizes: []`, `collected_at` on PriceSnapshot, retry count
**Fix:** Added `test_collect_price_empty_sizes_returns_zero`, `test_collect_stock_empty_sizes_out_of_stock`, `test_collected_at_is_set`, `test_scraper_rate_limited_retry_count` (asserts `call_count == 3`).

### M7: 1-digit basket URL not tested for CDN allowlist
**Fix:** Added `test_wb_image_cdn_re_rejects_one_digit_basket`.

---

## Minor Issues — Documented (follow-up)

| # | Issue | Priority |
|---|-------|----------|
| m1 | `httpx.AsyncClient` created per request in `base_scraper._get()` — no connection reuse | Follow-up |
| m2 | Per-task `WildberriesScraper` instantiation means rate limiter not shared across concurrent tasks | Follow-up |
| m3 | `REDIS_URL` startup validation absent in collector service (`_db.py` lazy-initializes) | Follow-up |
| m4 | Redis keys not namespaced by org_id | Follow-up |
| m5 | Orchestrator dispatches in tight loop — no chunking for broker pressure at >10k SKUs | Follow-up |
| m6 | `proxy.py:67` logs `PROXY_LIST_URL` which may contain credentials | Follow-up |

---

## Final Test Count

| Suite | Tests | Pass |
|-------|-------|------|
| `test_wb_scraper.py` | 35 | 35 ✓ |
| `test_wb_tasks.py` | 25 | 25 ✓ |
| **Total** | **60** | **60 ✓** |
