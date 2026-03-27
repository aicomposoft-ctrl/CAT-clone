# Validation Report — Reference Upload (S3)

**Date:** 2026-03-27 | **Result:** PASS (conditional)

---

## Scores

| Story | Agent 1 (Completeness) | Agent 2 (Feasibility/Security) | Status |
|-------|------------------------|-------------------------------|--------|
| US-R01: Image Upload | 88/100 | — | PASS |
| US-R02: Text Upload | 76/100 | — | PASS |
| US-R03: Presigned URL | 65/100 | — | PASS |
| Technical Feasibility | — | 84/100 | PASS |
| Multi-tenant Isolation | — | 91/100 | PASS |
| Security (OWASP) | — | 79/100 | PASS |

**No BLOCKED items (score < 50). Overall: PASS.**

---

## Mandatory Pre-Implementation Fixes

### CRITICAL
1. **WebP magic bytes check** — `is_valid_magic()` must check `content[8:12] == b"WEBP"` in addition to `content[:4] == b"RIFF"`. WAV/AVI files (valid RIFF containers) would otherwise pass.

### MAJOR
2. **Race condition** — `await db.flush()` required between `SKURepository.update()` and `compute_clip_embedding.delay()`. Celery worker must not start before DB row is visible.
3. **S3 delete guard** — assert `s3_key.startswith(f"org/{org_id}/")` before deletion.
4. **Content-Type allowlist** — reject uploads with `Content-Type` outside `image/jpeg, image/png, image/webp` as first-pass filter.

---

## BDD Gaps (add to Phase 3 implementation tests)

- Cross-org isolation for US-R02 and US-R03
- Viewer can GET presigned URL (US-R03)
- 401 scenarios for all endpoints
- `INVALID_IMAGE_MAGIC` scenario
- `reference_composition` max length validation (1000 chars)
- Partial text update (only description OR only composition)
