# Review Report — Adaptive Scraper Pipeline

**Date:** 2026-04-13
**Phase:** 4 (Post-implementation brutal-honesty review)

---

## Scores Summary

| Agent | Dimension | Score | Status |
|-------|-----------|-------|--------|
| 1 | Code Quality (Linus mode) | 63/100 | Issues fixed |
| 2 | Security (OWASP) | 74/100 | Issues fixed |
| 3 | Multi-tenant isolation | 82/100 | PASS (no action needed) |
| 4 | Performance | 68/100 | Issues fixed |
| 5 | Test Coverage | 52/100 | Advisory gaps noted |

---

## Fixed Issues

### CRITICAL — Fixed

**C1 (Code quality + Security): `_get_fernet()` rebuilt on every call**
- Was: `MultiFernet` constructed from env var string on every `encrypt_token`/`decrypt_token` call
- Fix: `@lru_cache(maxsize=1)` on `_get_fernet()` in `crypto.py` — built once per process

**C2 (Performance): `_collect_stock` fetched entire supplier catalog**
- Was: `GET /api/v1/supplier/stocks?dateFrom=today` with Python-side O(n) filter
- Fix: Added `nmId=nm` to query params; Python filter now redundant (removed)

### MAJOR — Fixed

**M1: Rate limiting not enforced in WBSellerAPIScraper**
- Was: `rate_limit = 5.0` declared but `super().__init__()` skipped, so no sleep applied
- Fix: Added `_min_interval` + `_last_request_at` + `time.sleep()` in `_request()`

**M2: `httpx.Client` recreated per request (TLS overhead)**
- Was: `with httpx.Client(...) as client:` inside every `_request()` call
- Fix: Single `self._client = httpx.Client(timeout=30.0)` in `__init__()`, reused across calls

**M3: nm_id validation scattered across methods**
- Was: `int(nm_id)` called individually in each `_collect_*` method, inconsistent
- Fix: Validated once at top of `collect()` before dispatch

**M4 (Security): Prompt injection via ARIA snapshot**
- Was: Raw ARIA text concatenated into user message with no sanitization
- Fix: `aria_text.replace("<", "\uff1c").replace(">", "\uff1e")` — fullwidth chars prevent
  XML delimiter injection; system prompt remains separate from user content

**M5 (Security): Claude response content logged (potential PII leak)**
- Was: `logger.debug("... %s", raw[:200])` — could log scraped personal data
- Fix: Log only `data_type` and `len(raw)` — never response content

**M6 (Security): URL logged in agent_scraper (URLs may contain signed params)**
- Was: Full URL in page-load error messages and cache-hit debug logs
- Fix: Use `url_hash` in debug log; use `platform_name` in error messages

**M7 (Security): `PLATFORM_SECRET_KEYS` validated lazily (first decrypt, not startup)**
- Was: `RuntimeError` only raised when `decrypt_token()` first called mid-task
- Fix: Added to `celery_app.py` `_validate_secrets()` — warns at startup if missing,
  fails fast (`sys.exit(1)`) if `POSTGRES_URL`/`REDIS_URL` missing

**M8: Rate limit Redis ops non-atomic (`incr` then `expire` separately)**
- Was: Process death between two calls would leave a key with no TTL
- Fix: Redis pipeline executes `INCR` + `EXPIRE` atomically in one round-trip

**M9 (Code quality): `_Tagged` dynamic subclass hack for `list[ReviewData]`**
- Was: `type("_Tagged", (list,), {"scraper_level": level_int})(result)` — bypasses type system
- Fix: Direct attribute assignment with `# type: ignore[union-attr]` comment

**M10 (Security): `fallback_chain` not validated against allowlist**
- Was: Only type-checked (`list[str]`); unknown level names silently passed
- Fix: Added `_VALID_LEVELS = frozenset({"l0", "l1", "l2", "l3"})` allowlist check

---

## Advisory Issues (not fixed — documented for follow-up)

| Issue | Location | Recommendation |
|-------|----------|----------------|
| `asyncio.run()` incompatible with gevent/eventlet pools | `scraper_router.py` | Already documented in `celery_app.py` docstring; enforce with runtime assertion if gevent support needed |
| `browser_pool.py` uses deprecated `asyncio.get_event_loop()` | `browser_pool.py` | Store `self._loop` in `_start()` for Python 3.12 compatibility |
| AgentScraper uses sync Redis calls inside `async def` | `agent_scraper.py` | Switch to `redis.asyncio` client in Sprint C+1 |
| `crypto.py` cache not invalidated on key rotation | `crypto.py` | Add `_get_fernet.cache_clear()` to key rotation management command |
| No tests for `crypto.py`, `agent_scraper.py`, `playwright_scraper.py` | `tests/` | Sprint C+1 backlog |
| PlaywrightScraper constructor parameter mismatch (pool vs selectors) | `playwright_scraper.py` | Fix before Sprint B integration test |

---

## Multi-tenant Isolation — PASS

- `ScraperRouter._load_creds()`: always double-filters by `(platform_id, org_id)` ✅
- WB tasks: `org_id` derived from DB JOIN on `SKU.org_id` — not from task argument ✅
- `OrgPlatformCredentials`: `UNIQUE(org_id, platform_id)` constraint enforced ✅
- `scraper_level` stored per ContentScore row — no cross-tenant contamination ✅

The security reviewer's concern about `sku_platform_id` poisoning is mitigated by the
authoritative DB JOIN: `org_id` is always the actual owner, never a caller-supplied value.

---

## Test Coverage Gaps (backlog)

- `crypto.py`: round-trip test, missing env var, MultiFernet rotation
- `agent_scraper.py`: rate limit enforcement, cache hit/miss, validation failure
- `playwright_scraper.py`: JSON interception vs DOM fallback, price parsing
- Integration: full L0→fallback→L1 chain end-to-end test
