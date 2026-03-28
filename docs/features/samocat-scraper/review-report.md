# Phase 4 Review Report — samocat-scraper

**Date:** 2026-03-28
**Reviewed by:** 5 parallel brutal-honesty agents
**Status:** ✅ All Critical and Major issues fixed

---

## Agent 1 — Code Quality (Linus Mode)

### Critical
_None._

### Major (all fixed)
- **M1** ✅ Platform name typo: `SamokatScraper.platform = "Samocat"` — should be `"Samokat"`. Fixed.
- **M2** ✅ `collect_reviews()` duplicated `_parse_rating` / `_parse_review_date` logic inline instead of using the module-level helpers defined 30 lines above. Fixed.
- **M3** ✅ Two separate `asyncio.run()` calls in content task (one for content, one for image download) — creates two event loops per task execution. Merged into single `_fetch_content_and_image()` coroutine.
- **M4** ✅ `samocat_stock_task.py` called `datetime.now(tz=timezone.utc)` twice (lines 111 and 124), risking midnight boundary crossing. Fixed by capturing `now_utc` once.
- **M5** ✅ `with_retry()` bypass: `_fetch_product` raised `ScraperError("API_UNAVAILABLE")` directly for 5xx instead of calling `resp.raise_for_status()`, so `with_retry()` never retried 5xx responses. Fixed by collapsing to a single `resp.raise_for_status()` after the 404 guard.

### Minor (deferred)
- `_kopeks_to_decimal` is exported but only used in `collect_price()` — minor over-exposure of internals.

---

## Agent 2 — Security (OWASP Checklist)

### Critical
_None._

### Major (all fixed)
- **SEC-1** ✅ `external_review_id` stored without sanitization or length cap — treated as trusted but originates from scraped API data. Fixed: `str(fb.get("id", ""))[:200].strip()` applied before storage.

### Minor (noted, not exploitable)
- Unicode digits pass `isdigit()` — `re.fullmatch(r'\d+', ...)` would be more explicit but is not a security vulnerability given httpx URL encoding as a backstop.
- `external_id` CRLF-in-logs theoretical: `external_id` originates from the internal DB `sku_platforms.external_id` column, not directly from the API response.

### Findings
- **SSRF guard** ✅ `_SK_IMAGE_CDN_RE` re-validates inside `_download_image_async` (authoritative guard). Outer check in content task removed — inner check remains.
- **Image URLs not written to logs** ✅ `logger.warning` for SSRF/download failure does not include URL value.
- **Proxy rotation** ✅ All HTTP calls go through `BaseScraper._get()`.
- **A03: No SQL injection** ✅ All DB writes use SQLAlchemy ORM / pg_insert parameterised values.
- **Input validation** ✅ `_parse_product_id` rejects non-numeric external IDs before any HTTP call.
- **Multi-tenant writes** — DB writes use `sku_platform_id` (UUID, FK to `sku_platforms`→`skus`→`org_id`). FK chain + PostgreSQL RLS provide isolation. `org_id` used for S3 key namespacing. Accepted: no schema change required.

---

## Agent 3 — Multi-Tenant Isolation

### Critical
_None._

### Findings
- **org_id scoping** ✅ All four tasks extract `org_id` as a primitive in Session 1 and use it for S3 key namespacing (`org/{org_id}/sku/{sku_id}/...`).
- **content_scores upsert key** ✅ Keyed on `sku_platform_id` which has a unique FK to one org — cross-tenant collision impossible.
- **Orchestrator read-only** ✅ Orchestrator only dispatches IDs; each task re-queries with `sku_platform_id` FK chain enforcing org isolation.
- **RLS backstop** ✅ PostgreSQL RLS policies documented as final line of defence.

---

## Agent 4 — Performance (N+1, Missing Indexes)

### Critical
_None._

### Major (fixed)
- **Orchestrator group() loop** ✅ `collect_samocat_content_all` and `collect_samocat_prices_all` dispatched individual `group().delay()` per SKU (N broker round-trips). Fixed to a single batched `group(...).delay()` — 1 round-trip regardless of catalog size.

### Minor
- Orchestrator queries `Platform.is_active`, `SKUPlatform.is_monitored` — these columns should have indexes. Already present on `sku_platforms` (confirmed in migration 0003). No action needed.

---

## Agent 5 — Test Coverage

### Critical (all fixed)
- **COV-1** ✅ Partial-row contract not verified — no test asserted content fields absent from stock task `set_`. Fixed: `test_partial_row_contract_content_fields_absent_from_set` added.
- **COV-2** ✅ `PARSE_ERROR` branch untested in price, stock, reviews tasks. Fixed: `test_parse_error_non_numeric_id_skips` added to all three.

### Major (fixed)
- **COV-3** ✅ `RATE_LIMITED` error code untested in price, stock, reviews tasks. Fixed: `test_rate_limited_triggers_retry_no_db_write` added to all three.

### Minor (fixed)
- **COV-4** ✅ `NO_PRODUCT_ID` missing from reviews task. Fixed.

### Findings
- **61 tests, all passing** ✅
- Happy path, NOT_FOUND, RATE_LIMITED, API_UNAVAILABLE, NO_PRODUCT_ID, PARSE_ERROR covered for all 4 tasks.
- Cross-tenant isolation test present for all 4 tasks.
- Partial-row contract explicitly verified for stock task.
- `_parse_product_id`, `_kopeks_to_decimal`, `_safe_qty`, `_parse_rating`, `_parse_review_date` all have unit-level tests.

### Remaining minor (deferred)
- No orchestrator dispatch test (thin DB-read + Celery group — acceptable).
- SSRF regex has no path-traversal test (`../` chars allowed by regex, but outer `https://cdn.samokat.ru/` anchor prevents exploitation).

---

## Summary

| Category | Critical | Major | Minor |
|----------|----------|-------|-------|
| Code Quality | 0 | 5 fixed | 1 deferred |
| Security | 0 | 1 fixed | 2 noted |
| Multi-tenant | 0 | 0 (FK chain accepted) | — |
| Performance | 0 | 1 fixed | 1 deferred |
| Test Coverage | 2 fixed | 1 fixed | 2 deferred |

**Decision: MERGE READY** — all Critical and Major issues resolved. 61/61 tests passing.
