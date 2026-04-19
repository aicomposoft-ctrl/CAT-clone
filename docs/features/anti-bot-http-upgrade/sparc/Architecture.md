# Architecture: Anti-Bot HTTP Upgrade

## Change Surface

```
services/collector/
├── app/
│   ├── core/
│   │   ├── base_scraper.py       ← ADD curl_cffi support in _get() + with_retry()
│   │   └── browser_pool.py       ← REPLACE playwright import with patchright
│   └── scrapers/
│       ├── wildberries.py        ← SET impersonate="chrome131", add Sec-Ch-Ua headers
│       └── ozon.py               ← SET impersonate="chrome131", keep _HEADERS
└── requirements.txt              ← ADD curl-cffi>=0.7.0, patchright>=1.50.0
```

## curl_cffi Integration Design

### Option A: Replace httpx in BaseScraper._get() (chosen)

Replace the `httpx.AsyncClient` used in `BaseScraper._get()` with `curl_cffi.requests.AsyncSession` when an `impersonate` string is provided.

```
BaseScraper
├── _client: httpx.AsyncClient | None          (existing, for non-impersonating scrapers)
├── _cffi_session: AsyncSession | None         (new, for impersonating scrapers)
├── _impersonate: str | None                   (new class attribute, default None)
└── _get(url, params, headers) → Response      (modified: route to cffi or httpx)
```

**Why not replace httpx entirely:** Lenta and Samocat don't need TLS impersonation (their issue is auth). Keeping httpx for them avoids unnecessary dependency.

### curl_cffi AsyncSession lifecycle

```python
# In BaseScraper.__init__ (or lazily on first _get call):
if self._impersonate:
    from curl_cffi.requests import AsyncSession
    self._cffi_session = AsyncSession(impersonate=self._impersonate)
```

Session is reused across requests (connection pooling). Closed in `__del__` or `aclose()`.

### Proxy mapping

curl_cffi uses `proxies={"http": url, "https": url}` — different from httpx's `proxy=url`. BaseScraper will normalise the ProxyRotator output to both formats.

## patchright Integration Design

### BrowserPool._start() change

```python
# Before:
from playwright.async_api import async_playwright

# After:
try:
    from patchright.async_api import async_playwright
    logger.info("BrowserPool: using patchright (CDP leak patched)")
except ImportError:
    from playwright.async_api import async_playwright
    logger.warning("BrowserPool: patchright not installed — falling back to playwright")
```

One-line change. All downstream `BrowserPool.acquire()`, `PlaywrightScraper`, `OpenAIAgentScraper` are unaffected.

## Anti-Bot Protection Stack (post-upgrade)

```
Request attempt
│
├── L1 (curl_cffi)
│   ├── Chrome 131 TLS fingerprint (JA3/JA4)    ← NEW: bypasses TLS check
│   ├── HTTP/2 with correct ALPN/settings        ← NEW: bypasses HTTP/2 fingerprint
│   ├── Sec-Ch-Ua headers                        ← NEW: browser identity headers
│   └── Proxy support (when configured)
│
├── L2 (patchright BrowserPool)
│   ├── Runtime.enable CDP patch                 ← NEW: main automation leak fixed
│   ├── Console.enable patch                     ← NEW
│   ├── --disable-blink-features=AutomationControlled ← existing stealth init
│   └── Persistent profile key per platform
│
└── L3 (OpenAI AgentScraper)
    └── Unchanged — accessibility tree + GPT extraction
```

## Dependencies

| Package | Version | Why |
|---------|---------|-----|
| `curl-cffi` | >=0.7.0 | Chrome TLS/JA3/JA4/HTTP2 impersonation for L1 |
| `patchright` | >=1.50.0 | CDP Runtime.enable patch for L2/L3 Playwright |

Both are pure Python wheels (curl_cffi ships with pre-built libcurl binaries). No system-level deps beyond what Playwright already requires.

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| curl_cffi API changes | Low | Pin to >=0.7.0, <1.0 |
| patchright lags playwright releases | Medium | Fallback to playwright on ImportError |
| Ozon sensor.js still blocks L1 | High | L2 patchright is second chance; L3 is backstop |
| WB changes TLS detection method | Medium | L2/L3 backstops remain |
