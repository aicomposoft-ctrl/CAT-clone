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

### Major
_None._

### Findings
- **SSRF guard** ✅ `_SK_IMAGE_CDN_RE` re-validates inside `_download_image_async` (double check: caller + callee). Redundant outer check in content task removed without weakening defence — the inner check in `_download_image_async` is the authoritative guard.
- **Image URLs not written to logs** ✅ `logger.warning` for SSRF failure does not include `content.image_url` (untrusted scraped data).
- **Proxy rotation** ✅ All HTTP calls go through `BaseScraper._get()` which rotates proxy and User-Agent.
- **A03: No SQL injection** ✅ All DB writes use SQLAlchemy ORM / pg_insert with parameterised values.
- **Input validation** ✅ `_parse_product_id` rejects non-numeric external IDs before any HTTP call.

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

### Critical
_None._

### Findings
- **53 tests, all passing** ✅
- Happy path, NOT_FOUND, RATE_LIMITED, API_UNAVAILABLE, NO_PRODUCT_ID, PARSE_ERROR covered per task.
- Cross-tenant isolation test present for all 4 tasks.
- SSRF image URL test present.
- MinIO upload failure non-fatal test present (updated to reflect single asyncio.run contract).
- `_parse_product_id`, `_kopeks_to_decimal`, `_safe_qty`, `_parse_rating`, `_parse_review_date` all have unit-level tests.

### Minor
- No test for `collect_samocat_content_all` orchestrator dispatch (group() call). Acceptable given orchestrator is thin DB-read + Celery dispatch.

---

## Summary

| Category | Critical | Major | Minor |
|----------|----------|-------|-------|
| Code Quality | 0 | 5 fixed | 1 deferred |
| Security | 0 | 0 | — |
| Multi-tenant | 0 | 0 | — |
| Performance | 0 | 1 fixed | 1 deferred |
| Test Coverage | 0 | 0 | 1 deferred |

**Decision: MERGE READY** — all Critical and Major issues resolved before commit.
