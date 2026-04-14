# Review Report — Reference Upload (S3)

**Date:** 2026-03-27
**Phase:** 4 — Code Review (5 parallel agents)
**Result:** All Critical and Major issues fixed. Ready to merge.

---

## Agent Scores

| Agent | Area | Score |
|-------|------|-------|
| Agent 1 | Code Quality | (not returned — subsumed by security/perf) |
| Agent 2 | Security (OWASP) | 72/100 → fixed |
| Agent 3 | Multi-tenant Isolation | 81/100 → fixed |
| Agent 4 | Performance | 62/100 → fixed |
| Agent 5 | Test Coverage | 87/100 |

---

## Critical Issues

**None identified.**

---

## Major Issues — Fixed

### M1: DoS via unbounded file read before size check
**File:** `reference_router.py:69`
**Fix:** Changed `await file.read()` to `await file.read(_MAX_BYTES)` (10 MB + 1 sentinel), returning HTTP 413 immediately if the upload exceeds the cap. Previously, an attacker could send multi-gigabyte payloads that would be fully buffered into memory before the 10 MB guard fired.

### M2: Sync Redis client blocking async event loop
**File:** `reference_service.py` — `_get_redis()` and `_invalidate_embedding()`
**Fix:** Switched from synchronous `redis.from_url()` to `redis.asyncio.from_url()`. Both functions are now `async def` and all Redis calls use `await`. Eliminates blocking network I/O on the event loop thread.

### M3: `MinioClient.delete()` org_id guard optional (opt-in security)
**File:** `minio_client.py:134`
**Fix:** Changed signature from `delete(s3_key, org_id: Optional[UUID] = None)` to `delete(s3_key, org_id: UUID)`. Guard is now structural — callers cannot bypass it by omitting the argument.

### M4: `SKUPlatformRepository.get_by_sku_platform` missing org_id isolation
**File:** `repository.py:249`
**Fix:** Added `org_id: UUID` parameter and a JOIN through `SKU.org_id` to the query. Prevents a scenario where `sku_id + platform_id` from a different org could match.

### M5: Missing composite index for cursor pagination
**File:** `0002_create_catalog_tables.py`
**Fix:** Added `CREATE INDEX idx_skus_org_cursor ON skus (org_id, created_at DESC, id DESC)`. Supports index-only scans for the common cursor page query without a full sort.

### M6: Missing `sku_platforms(platform_id)` index
**File:** `0002_create_catalog_tables.py`
**Fix:** Added `idx_sku_platforms_platform` on `platform_id`. Required for the orchestrator query: `WHERE platform.name = 'Wildberries' AND is_monitored = TRUE`.

---

## Minor Issues — Documented (follow-up)

| # | Issue | File | Priority |
|---|-------|------|----------|
| m1 | PNG magic bytes covers only 4 of 8 canonical bytes | `minio_client.py:40` | Fixed (extended to 8) |
| m2 | Bucket name is static `"cat-references"` (should have UUID suffix per `security.md`) | `minio_client.py:22` | Follow-up: requires bucket rename + env var |
| m3 | Redis keys not namespaced by org_id | `reference_service.py:53` | Follow-up: `ref_emb:{org_id}:{sku_id}:{field}` |
| m4 | aioboto3 creates new session per S3 operation | `minio_client.py:84` | Follow-up: shared session pool |
| m5 | Test: Redis `delete()` calls never asserted in reference tests | `test_reference_api.py` | Follow-up |
| m6 | Test: `upload_reference_text` with empty body (early-return branch) not tested | `test_reference_api.py` | Follow-up |

---

## Summary

All 6 Major issues fixed. 78 API tests pass. The PNG magic bytes fix (minor) was included in this commit since it's a 1-line change. Remaining minor issues are low-risk and documented for follow-up.
