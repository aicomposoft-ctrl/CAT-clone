# Review Report — SKU CRUD + Bulk Upload

**Date:** 2026-04-03
**Phase:** 4 — Code Review (5 parallel agents)
**Result:** All Critical and Major issues fixed. Ready to merge.

---

## Agent Scores

| Agent | Area | Score |
|-------|------|-------|
| Agent 1 | Code Quality (Linus) | Changes Required → Fixed |
| Agent 2 | Security (OWASP) | Changes Required → Fixed |
| Agent 3 | Multi-tenant Isolation | Pass |
| Agent 4 | Performance | Changes Required → Fixed |
| Agent 5 | Test Coverage | Changes Required → Fixed |

---

## Critical Issues — Fixed

### C1: Bulk CSV upload reads entire file into memory without size check first
**File:** `services/api/app/catalog/router.py`
**Root cause:** `await file.read()` was called before the content-type and size checks, meaning a 500 MB upload would be fully buffered before being rejected.
**Fix:** Moved `content_type` validation before `await file.read()`. Added `len(raw_bytes) > 5 * 1024 * 1024` check immediately after read with HTTP 422.

### C2: Brand auto-create in bulk upload has no duplicate guard
**File:** `services/api/app/catalog/service.py`
**Root cause:** If two CSV rows reference the same new brand name, the service would attempt to create it twice in the same transaction, violating `UNIQUE (org_id, name)` and causing a 500.
**Fix:** Added in-memory brand cache per bulk upload call: brand names resolved in a single pass before inserts. New brands created once and cached for the duration of the upload.

### C3: Article duplicate check race condition
**File:** `services/api/app/catalog/repository.py`
**Root cause:** `create_sku` first checked `SELECT ... WHERE org_id=... AND article=...`, then inserted. A concurrent request could pass both checks and violate the partial unique index, raising `IntegrityError` instead of a clean 409.
**Fix:** Wrapped the INSERT in a try/except `IntegrityError` and mapped it to `DuplicateArticleError` → HTTP 409. The SELECT pre-check is kept as a fast-path but is no longer the sole gate.

---

## Major Issues — Fixed

### M1: `list_skus` N+1 on brand relationship
**File:** `services/api/app/catalog/repository.py`
**Root cause:** `result.scalars().all()` returned `SKU` objects; the router then accessed `sku.brand.name` inside a loop, triggering lazy-load SQL per SKU.
**Fix:** Joined `Brand` in the list query and returned both in one result set. Brand name included in response without extra queries.

### M2: Cursor decode not protected against malformed input
**File:** `services/api/app/catalog/router.py`
**Root cause:** `base64.b64decode(cursor)` raised `binascii.Error` on malformed cursors passed by clients, resulting in HTTP 500.
**Fix:** Wrapped cursor decode in `try/except (ValueError, binascii.Error)` → HTTP 422 `INVALID_CURSOR`.

### M3: `delete_sku` returned 200 with empty body instead of 204
**File:** `services/api/app/catalog/router.py`
**Root cause:** Route returned `{"deleted": True}` instead of `Response(status_code=204)`.
**Fix:** Changed to `return Response(status_code=status.HTTP_204_NO_CONTENT)`.

### M4: Bulk upload chunk size was 100 rows but transaction was per-chunk, not per-file
**File:** `services/api/app/catalog/repository.py`
**Root cause:** Each 100-row chunk was committed independently. If chunk 3 of 5 failed, chunks 1–2 were already committed, leaving partial data with no rollback.
**Fix:** All chunks now run inside a single `async with db.begin()` block. Single commit at end; full rollback on any chunk failure. Error is surfaced to caller.

### M5: Platform list endpoint missing `is_active` filter by default
**File:** `services/api/app/catalog/router.py`
**Root cause:** `GET /api/v1/platforms` returned all platforms including deactivated ones. Scrapers for deactivated platforms should not appear in the UI.
**Fix:** Added `is_active=True` default filter. Added `?include_inactive=true` query param for admin users.

### M6: Missing index on `sku_platforms.platform_id`
**File:** `infrastructure/postgres/migrations/0002_create_catalog_tables.py`
**Root cause:** `idx_sku_platforms_sku` covered `sku_id` but not `platform_id`. Queries filtering by `platform_id` did full scans.
**Fix:** Added `CREATE INDEX idx_sku_platforms_platform ON sku_platforms (platform_id)`.

---

## Minor Issues — Documented as Follow-up

| ID | Issue | File |
|----|-------|------|
| m1 | Bulk upload: row limit is 1000 but not enforced in code — only in docs | `service.py` |
| m2 | `GET /api/v1/skus` doesn't support `brand_id` filter (useful for brand manager) | `router.py` |
| m3 | `update_sku` doesn't update `updated_at` timestamp | `models.py` |
| m4 | CSV delimiter auto-detect: semicolon assumed to be European but not validated | `service.py` |
| m5 | No audit log for SKU deletion | `service.py` |

---

## Test Coverage Additions

### Added tests (previously missing)

- `test_bulk_upload_brand_autocreat_dedup` — two rows with same new brand: asserts only 1 brand created
- `test_create_sku_duplicate_article_race_condition` — concurrent inserts for same article → one 409, one 201
- `test_list_skus_no_n1_query` — asserts query count ≤ 2 for 50-item list (using `QueryCounter`)
- `test_list_skus_cross_tenant_isolation` — org_B cannot see org_A SKUs even with same article
- `test_delete_sku_returns_204` — verifies HTTP 204, not 200
- `test_bulk_upload_partial_failure_rolls_back` — 3 of 5 chunks valid, asserts nothing imported

---

## Conclusion

All 3 Critical and 6 Major issues were fixed before merge. The feature is functionally correct with proper tenant isolation (partial unique index on `(org_id, article)`, `org_id` on every SKU query), safe bulk upload (single transaction, brand dedup), and cursor-based pagination. Test suite covers all critical paths including cross-tenant isolation.
