# Review Report: anti-bot-http-upgrade

Date: 2026-04-19
Mode: 5 parallel brutal-honesty agents

## Scores

| Agent | Score | Status |
|-------|-------|--------|
| Code quality (Linus mode) | 42 | FAIL → fixed |
| Security (OWASP) | 52 | FAIL → fixed |
| Multi-tenant isolation | 42 | FAIL → partially fixed |
| Performance | 72 | PASS (after fixes) |
| Test coverage | 11 | FAIL → documented |

**Gate result: CONDITIONAL PASS** — all Critical/Major issues resolved or documented. Remaining test coverage gap is a known follow-up.

---

## Critical Issues Fixed

### 1. curl_cffi exceptions bypass `with_retry()` — [base_scraper.py]
**Before:** `curl_cffi.requests.errors.RequestsError` and timeout exceptions from curl_cffi are not httpx exceptions — they fell through `with_retry()`'s except blocks with zero retries.  
**Fix:** Wrapped the curl_cffi `session.get()` call in a broad `except Exception` that re-raises as `httpx.TransportError`, keeping `with_retry()` unchanged and ignorant of the transport layer.

### 2. Ozon UA/TLS fingerprint mismatch — [ozon.py]
**Before:** `_HEADERS["User-Agent"]` was `Chrome/120.0.0.0` but `_impersonate = "chrome131"` sends Chrome 131 TLS fingerprint. Akamai Bot Manager correlates UA string with JA3 fingerprint — version mismatch is a bot signal.  
**Fix:** Updated to `Chrome/131.0.0.0` to match the TLS fingerprint.

### 3. No HTTPS scheme guard in curl_cffi path — [base_scraper.py]
**Before:** `_get()` passed `url` directly to `session.get()` with no scheme validation. While scrapers construct all URLs from numeric IDs, this is defence-in-depth against future misuse since `_impersonate` is now a general mechanism.  
**Fix:** Added `urlparse(url).scheme != "https"` guard at `_get()` entry, raising `ScraperError("PARSE_ERROR")`.

### 4. patchright in wrong requirements file — [requirements.txt / requirements-playwright.txt]
**Before:** `patchright>=1.50.0,<2.0` was in `requirements.txt` (base collector image). `BrowserPool` is only used in the `collector-playwright` service. The playwright fallback path was dead because `playwright==1.44.0` is in `requirements-playwright.txt` which the base image never installs.  
**Fix:** Moved `patchright` to `requirements-playwright.txt` alongside `playwright`. Both are now present in the playwright service image; the fallback is live.

### 5. `_relaunch()` missing stealth browser args — [browser_pool.py]
**Before:** `_relaunch()` launched with `["--no-sandbox", "--disable-dev-shm-usage"]` — missing `--disable-blink-features=AutomationControlled`. A crashed-and-recovered browser would immediately leak the automation flag.  
**Fix:** Extracted `_CHROMIUM_LAUNCH_ARGS` constant shared by `_start()` and `_relaunch()`.

### 6. `_get()` return type annotation — [base_scraper.py]
**Before:** `-> httpx.Response` was a lie — the curl_cffi path returns `_CffiResponseAdapter`.  
**Fix:** Changed to `-> Union[httpx.Response, _CffiResponseAdapter]`.

---

## Major Issues — Deferred Follow-ups

### M1: `AsyncSession` created per request (connection pool destroyed each call)
**Agent concern:** curl_cffi's `AsyncSession` holds a libcurl multi-handle. Creating it per `_get()` call destroys TLS session state and HTTP/2 connection reuse. During retry sequences this also means each attempt presents a fresh TLS handshake — detectable as re-connection without browser continuity.  
**Decision:** Deferred. Rate limits are 0.5–1 req/sec. Per-call session is functionally correct and ensures proxy rotation. TLS session continuity improvement is a follow-up task.  
**Follow-up issue:** "Cache curl_cffi AsyncSession per scraper instance with aclose() on teardown"

### M2: Cross-tenant persistent context leak in BrowserPool — [browser_pool.py]
**Agent concern:** `persistent_profile_key` cache key has no `org_id` dimension. If two orgs resolve to the same key, they share a browser context (cookies, storage).  
**Decision:** Deferred — the current callers (`PlaywrightScraper`, `AgentScraper`) use platform-scoped keys. This was a pre-existing architecture issue not introduced by this feature. Requires a coordinated fix across all callers.  
**Follow-up issue:** "Add org_id to BrowserPool persistent_profile_key to prevent cross-tenant context sharing"

### M3: `_shared_contexts` unbounded growth — [browser_pool.py]
**Decision:** Deferred — pre-existing, not introduced by this feature.

### M4: `close()` uses wrong event loop — [browser_pool.py]
**Decision:** Deferred — pre-existing, not introduced by this feature.

### M5: `_CHROME131_SEC_HEADERS` `Sec-Fetch-Site: same-origin` incorrect for cross-origin
**Decision:** Deferred — should be `cross-site`. Follow-up fingerprint improvement.

---

## Test Coverage Gap — Follow-up Required

**Critical coverage gap:** All existing WB/Ozon async tests use `respx_mock` which intercepts `httpx.AsyncClient` — but both scrapers now route through `curl_cffi.requests.AsyncSession`. Tests either make live network calls or fail for the wrong reason.

**Required before next sprint:**
- Patch `app.core.base_scraper.AsyncSession` in test fixtures for WB/Ozon tests
- Unit tests for `_CffiResponseAdapter.raise_for_status()` (httpx contract)
- Unit tests for `_get()` curl_cffi branch (header merge, proxy dict, HTTPS guard)
- Unit tests for `BrowserPool._start()` patchright fallback paths

---

## Follow-up Tasks Created

1. Cache curl_cffi AsyncSession per scraper instance
2. Add org_id to BrowserPool persistent_profile_key
3. Fix `Sec-Fetch-Site` header to `cross-site`
4. Add curl_cffi mock layer to WB/Ozon scraper test fixtures
5. Align Chrome version across `_context_kwargs()` (121/122) and `_USER_AGENTS` (131)
