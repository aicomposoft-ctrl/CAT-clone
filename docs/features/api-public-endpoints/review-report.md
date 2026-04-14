# Review Report — API Public Endpoints

> **Date:** 2026-04-04 | **Status:** PASS (after fixes)

---

## Review Scores

| Agent | Dimension | Pre-fix | Post-fix |
|-------|-----------|---------|----------|
| A1 | Code Quality | Changes Required | PASS |
| A2 | Security | Changes Required | PASS (rate limiting deferred) |
| A3 | Multi-tenant | PASS | PASS |
| A4 | Performance | Changes Required | PASS |
| A5 | Test Coverage | FAIL | PASS |

---

## Fixed Issues

| Severity | Issue | Fix |
|----------|-------|-----|
| Critical | `/alerts` unbounded fetch — no LIMIT | Added page/page_size pagination |
| Critical | No cross-tenant isolation test | Added `test_cross_tenant_isolation` |
| Major | `HTTPException` raised in `service.py` | Moved to `router.py`, service raises `KeyError` |
| Major | `/prices` no pagination | Added page/page_size + count query |
| Major | `/reviews/summary` no pagination | Added page/page_size + LIMIT |
| Major | Duplicate index on `key_hash` | Removed redundant `create_index` (UNIQUE already creates it) |
| Major | No expired key test | Added `test_expired_api_key_returns_401` |

---

## Known Deferred Issues (follow-up tasks)

| Issue | Priority | Notes |
|-------|----------|-------|
| Rate limiting on public endpoints | HIGH | TODO in `deps.py` line 159. Implement Redis sliding window before production. Rate key should be `rate:apikey:{key_hash[:16]}` |
| SHA-256 without server-side pepper | MEDIUM | Add `HMAC-SHA256(API_KEY_PEPPER, full_key)` — requires new env var. Current 240-bit entropy is strong but no rainbow table protection on DB breach |
| `update_last_used` shared session | LOW | `asyncio.create_task()` may use closed session. Logged as WARNING, non-blocking. Fix: use dedicated short-lived session |
| f-string SQL interpolation pattern | LOW | Server-controlled strings only (no user input), no injection risk, but fragile pattern |

---

## Approved

Feature is cleared for merge with the following conditions:
1. Rate limiting must be implemented before production traffic is enabled on `/api/v1/public/*`
2. SHA-256 pepper is recommended before the first org creates API keys in production
