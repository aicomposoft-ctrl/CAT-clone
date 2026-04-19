# Specification: Anti-Bot HTTP Upgrade

## User Stories

### US-1: curl_cffi for WB L1 scraper
**As a** CAT collector task  
**I want** the WB L1 scraper to use curl_cffi with Chrome TLS impersonation  
**So that** `card.wb.ru/cards/v2/detail` requests are not blocked by Cloudflare TLS fingerprint check

**Acceptance Criteria:**
- `WildberriesScraper._get()` uses `curl_cffi.requests.AsyncSession(impersonate="chrome131")`
- Request includes `Sec-Ch-Ua`, `Sec-Ch-Ua-Mobile`, `Sec-Ch-Ua-Platform` headers matching Chrome 131
- Existing `_CARD_APIS` fallback chain (wb.ru → wildberries.ru) preserved
- `ProxyRotator` proxy still applied when set
- All existing unit tests pass

### US-2: curl_cffi for Ozon L1 scraper
**As a** CAT collector task  
**I want** the Ozon L1 scraper to use curl_cffi with Chrome TLS impersonation  
**So that** `composer-api.bx` requests have correct JA3/JA4/HTTP2 fingerprint for Akamai

**Acceptance Criteria:**
- `OzonScraper._get()` uses `curl_cffi.requests.AsyncSession(impersonate="chrome131")`
- Existing `_HEADERS` dict (x-o3-app-name, x-o3-app-version) preserved and merged
- `_parse_widget_states` logic unchanged
- 403/429 error handling unchanged

### US-3: Shared curl_cffi session in BaseScraper
**As a** developer  
**I want** curl_cffi session management in `BaseScraper`  
**So that** all L1 scrapers benefit from TLS impersonation without per-scraper changes

**Acceptance Criteria:**
- `BaseScraper._get()` accepts optional `impersonate` parameter
- When `impersonate` is set, uses `curl_cffi.requests.AsyncSession`; otherwise falls back to `httpx`
- Session reuse within a single scraper instance (not per-request)
- Proxy configuration works identically for both clients

### US-4: patchright in BrowserPool
**As a** Playwright L2/L3 scraper  
**I want** BrowserPool to use `patchright` instead of `playwright`  
**So that** CDP Runtime.enable leak is patched and L2 is not detected as automation

**Acceptance Criteria:**
- `BrowserPool._start()` imports from `patchright.async_api` instead of `playwright.async_api`
- Fallback to `playwright` if `patchright` not installed (warning logged)
- All existing `BrowserPool.acquire()` call sites unchanged
- `PlaywrightScraper` and `OpenAIAgentScraper` unaffected (use pool via interface)

## BDD Scenarios

### Scenario 1: WB L1 with curl_cffi
```gherkin
Given WildberriesScraper is initialised
When collect_price("114805666") is called
Then the HTTP request uses curl_cffi AsyncSession with impersonate="chrome131"
And the request URL is "https://card.wb.ru/cards/v2/detail"
And the response is parsed into PriceData
```

### Scenario 2: curl_cffi proxy passthrough
```gherkin
Given a ProxyRotator with proxy_url="http://proxy:8080"
And WildberriesScraper is initialised with that rotator
When collect_content is called
Then the curl_cffi session uses proxies={"http": proxy_url, "https": proxy_url}
```

### Scenario 3: patchright BrowserPool startup
```gherkin
Given patchright is installed
When BrowserPool._start() is called
Then browser is launched via patchright.async_api.async_playwright
And no playwright.async_api import is used
```

### Scenario 4: patchright fallback
```gherkin
Given patchright is NOT installed
When BrowserPool._start() is called
Then a warning is logged: "patchright not installed — falling back to playwright"
And browser is launched via playwright.async_api.async_playwright
```

## Out of Scope
- Lenta/Samocat auth token investigation
- curl_cffi for Lenta/Samocat (their issue is auth, not TLS fingerprint)
- Custom JA3 fingerprint tuning
- HTTP/2 pseudo-header order customisation
