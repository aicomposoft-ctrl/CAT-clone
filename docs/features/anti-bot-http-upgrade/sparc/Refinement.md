# Refinement: Anti-Bot HTTP Upgrade

## Edge Cases

### E1: curl_cffi not installed
If `curl-cffi` is missing but `_impersonate` is set:
- `_get_cffi_session()` raises ImportError
- Scraper raises `ScraperError("API_UNAVAILABLE", "curl_cffi not installed")`
- Router falls back to L2 as expected
- **Resolution:** curl_cffi added to requirements.txt — ImportError shouldn't happen in production

### E2: patchright not installed in collector-playwright image
- BrowserPool logs warning and falls back to playwright
- L2 still works, just without CDP patch
- **Resolution:** patchright added to requirements.txt; fallback prevents hard failure

### E3: curl_cffi session proxy rotation
- Current ProxyRotator returns a single proxy URL per call
- curl_cffi session is initialised once with one proxy
- If proxy expires mid-session, requests fail
- **Resolution:** Re-create cffi session on next request cycle (task-level, not per-request)
- **Deferral:** Full proxy rotation for curl_cffi is a follow-up task

### E4: Ozon sensor.js still fires at L1
- curl_cffi fixes TLS fingerprint but Ozon may still run sensor.js JavaScript challenge
- In that case, L1 still gets 403 and falls back to L2
- **This is expected and acceptable** — curl_cffi improves L1 odds, L2/L3 remain backstops
- **Resolution:** No special handling needed; router chain works correctly

### E5: curl_cffi AsyncSession not closed
- `_cffi_session` is created lazily, never explicitly closed
- In Celery task context, scraper instance is created per-task and GC'd after
- curl_cffi AsyncSession has no async context manager requirement for cleanup
- **Resolution:** Acceptable for Celery short-lived tasks; add explicit close() if memory issues arise

### E6: httpx.HTTPStatusError in raise_for_status adapter
- `_CffiResponseAdapter.raise_for_status()` re-raises as `httpx.HTTPStatusError`
- `BaseScraper.with_retry()` catches `httpx.HTTPStatusError` for retry logic
- Must maintain this contract
- **Resolution:** Adapter raises httpx exception — with_retry() unchanged

## Testing Strategy

### Unit tests (no network)
- Mock `curl_cffi.requests.AsyncSession.get` → return fake response object
- Assert `WildberriesScraper._fetch_product` calls session with correct URL/params
- Assert `OzonScraper._fetch_product_page` calls session with correct headers

### Integration smoke test
- `scripts/test_scrapers_local.py` — run manually after deployment
- Check `scraper_level` in DB: if level=1 appears for WB/Ozon, L1 is working

### Regression guard
- Existing e2e tests (`test_catalog_api.py`, `test_reference_api.py`) — must still pass
- These test the API layer, not the scraper — they mock the scraper calls, so no impact

## Rollback Plan

If curl_cffi causes unexpected failures:
1. Remove `_impersonate = "chrome131"` from WildberriesScraper and OzonScraper
2. Scrapers revert to httpx silently
3. Zero data loss — router handles failures gracefully

If patchright causes BrowserPool startup failure:
1. `pip uninstall patchright` in collector-playwright image
2. Fallback to playwright activates automatically
3. Zero downtime — BrowserPool already has fallback branch
