# Review Report — lenta-scraper

**Date:** 2026-03-31
**Phase:** 4 — brutal-honesty-review (5 agents)
**Gate result:** ✅ PASS — no Critical or Major issues. Ready to merge.

---

## Agent Scores

| Agent | Focus | Score | Status |
|-------|-------|-------|--------|
| 1 | Code Quality (Linus mode) | 88/100 | PASS |
| 2 | Security (OWASP) | 95/100 | PASS |
| 3 | Multi-tenant isolation | 96/100 | PASS |
| 4 | Performance | 82/100 | PASS |
| 5 | Test coverage | 91/100 | PASS |

---

## Agent 1 — Code Quality

**Score: 88/100**

### Positive
- Clean docstrings on every public method with explicit error codes.
- `_LT_IMAGE_CDN_RE` regex is tight and SSRF-resistant.
- `with_retry()` wiring is consistent with WB/Ozon/Samocat patterns.
- Partial-row contract (stock vs content fields in ON CONFLICT) documented clearly.
- Orchestrator cross-org rationale documented inline — rare and appreciated.

### Minor Issues
- **M-1** `lenta.py` imports private helpers (`_kopeks_to_decimal`, `_parse_product_id`, `_parse_rating`, `_parse_review_date`, `_safe_qty`) from `samocat.py`. These are private symbols (leading `_`). Coupling two scrapers via private imports is a smell — future Samocat refactors can silently break Lenta. **Fix:** extract shared helpers to `app/core/scraper_utils.py` or promote to `BaseScraper`.
- **M-2** `asyncio.run()` inside sync Celery tasks works but will fail if the worker runs with `--pool=gevent` or inside an existing event loop. Document the constraint or use `nest_asyncio` as a guard. (Currently this is the same pattern as Samocat/Ozon/WB — consistent, but still fragile.)
- **Minor** `_LT_IMAGE_CDN_RE` character class `[A-Za-z0-9/_\-\.]`: `\-` inside `[]` is unambiguous but conventionally the dash goes last. No functional impact.

---

## Agent 2 — Security (OWASP)

**Score: 95/100**

### Positive
- SSRF guard at **two layers**: allowlist check in `collect_content` before storing the URL, and re-validation inside `_download_image_async` before making the HTTP call. Defense-in-depth is correct.
- Image URL value is **never logged** on allowlist failure — avoids leaking potentially crafted URLs to log aggregators.
- `sanitize()` applied to all text fields (title, description, composition, review text, promo_label).
- Length caps on all text fields match storage column constraints.
- No secrets in code; `get_proxy_rotator()` centralises credential access.
- `external_review_id` capped at 200 chars with strip() — correct treatment of untrusted scraped data.
- Rate limit 1.0 req/sec enforced via `BaseScraper.rate_limit` — not removable by callers.

### No Issues
No OWASP A01–A10 violations found.

---

## Agent 3 — Multi-Tenant Isolation

**Score: 96/100**

### Positive
- Every task joins `SKU` to extract `org_id` as a **primitive within the session** — no ORM object escapes session boundary, no DetachedInstanceError possible.
- S3 key namespaced as `org/{org_id}/sku/{sku_id}/lenta/main.jpg` — cross-org image collision impossible.
- `content_scores` upsert keyed on `sku_platform_id` (FK → one org_id) — conflict-update cannot overwrite another org's row.
- `reviews` bulk upsert similarly keyed on `sku_platform_id + external_review_id`.
- `price_snapshots` insertion uses `sp_id` bound to one org — no cross-tenant write.
- Orchestrator pattern (read-only ID dispatch, per-task re-scope) documented with rationale.

### Minor
- **M-3** `PriceSnapshot` model: `org_id` is not stored as a direct column — it is derivable only via `sku_platform_id → sku → org`. This makes analytics queries (e.g. "all prices for org X") require a JOIN. No security issue (can't leak data), but add a `org_id` indexed column to `price_snapshots` in a future migration for query efficiency.

---

## Agent 4 — Performance

**Score: 82/100**

### Positive
- Orchestrator selects **only IDs** (not full ORM objects) — memory footprint is flat regardless of catalog size.
- Reviews bulk upsert uses a single `db.execute(stmt)` for all rows — no per-review loop.
- `Celery group()` dispatches content + stock + review tasks **concurrently** per SKU.

### Minor Issues
- **M-4** Each of the three per-SKU tasks (`collect_lenta_content`, `collect_lenta_price`, `collect_lenta_stock`) calls `_fetch_product()` independently → **3 HTTP requests** to `GET /api/v1/products/{product_id}` for the same product during a daily run. The API is single-endpoint (returns content+price+stock in one response), so 2 of the 3 calls are redundant. A short-lived Redis TTL cache (60 s) keyed on `product_id` inside `_fetch_product` would cut calls to 1. Acceptable for current scale; worth addressing at >10k SKUs.
- **M-5** No index on `content_scores.scored_at` in the migration for Lenta-written rows — same gap exists for WB/Ozon/Samocat. The ML pipeline's `WHERE collected_description IS NOT NULL AND scored_at = today` filter is unindexed. Add composite index `(sku_platform_id, scored_at)` if not already present.

---

## Agent 5 — Test Coverage

**Score: 91/100**

### Positive
- 58 tests covering all 4 tasks (content=13, price=10, stock=11, reviews=13, scraper=11).
- Every error code path is tested: NOT_FOUND, RATE_LIMITED, API_UNAVAILABLE, NO_PRODUCT_ID, PARSE_ERROR.
- Cross-tenant isolation tested in content, price, stock, reviews tasks.
- Partial-row contract verified: `set_` in ON CONFLICT contains **only** `in_stock` and `warehouse_qty`.
- Kopeks-to-Decimal conversion and zero-discount fallback tested.
- SSRF image URL rejection tested (s3_key=None, upsert proceeds).

### Minor Issues
- **M-6** No scraper-level test for `collect_reviews` with malformed `createdAt` date (e.g. non-ISO string). `_parse_review_date` handles this in Samocat tests but Lenta tests only cover the happy path for date parsing.
- **M-7** Orchestrator tests (`collect_lenta_content_all`, `collect_lenta_prices_all`) are not present — only per-task tests exist. Samocat has the same gap. Add at minimum: empty catalog → no group dispatched; one SKU → group called with correct task signatures.

---

## Summary

| Severity | Count | Items |
|----------|-------|-------|
| Critical | 0 | — |
| Major | 0 | — |
| Minor | 7 | M-1 through M-7 |

### Decision: ✅ MERGE

All minor issues are follow-up tasks. No blockers.

### Follow-up tasks (future sprint)
- [ ] Extract shared scraper helpers to `app/core/scraper_utils.py` (M-1)
- [ ] Add `asyncio.run()` guard / document `--pool=prefork` requirement (M-2)
- [ ] Add `org_id` indexed column to `price_snapshots` (M-3)
- [ ] Add Redis TTL cache in `_fetch_product` to deduplicate 3→1 HTTP calls (M-4)
- [ ] Add composite index `(sku_platform_id, scored_at)` on `content_scores` (M-5)
- [ ] Test `_parse_review_date` with malformed input in Lenta tests (M-6)
- [ ] Add orchestrator-level tests (M-7)
