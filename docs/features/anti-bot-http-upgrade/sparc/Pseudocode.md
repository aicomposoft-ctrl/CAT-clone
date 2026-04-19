# Pseudocode: Anti-Bot HTTP Upgrade

## 1. BaseScraper._get() with curl_cffi routing

```python
class BaseScraper:
    _impersonate: str | None = None   # subclass sets this to "chrome131" etc.
    _cffi_session = None              # lazy init
    _CHROME131_HEADERS = {
        "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Accept-Encoding": "gzip, deflate, br",
    }

    def _get_cffi_session(self):
        if self._cffi_session is None:
            from curl_cffi.requests import AsyncSession
            proxy_url = self._proxy_rotator.get() if self._proxy_rotator else None
            proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
            self._cffi_session = AsyncSession(
                impersonate=self._impersonate,
                proxies=proxies,
            )
        return self._cffi_session

    async def _get(self, url, params=None, headers=None):
        if self._impersonate:
            session = self._get_cffi_session()
            merged_headers = {**self._CHROME131_HEADERS, **(headers or {})}
            resp = await session.get(url, params=params, headers=merged_headers)
            return _CffiResponseAdapter(resp)   # wrap to match httpx Response API
        else:
            # existing httpx path unchanged
            ...
```

## 2. _CffiResponseAdapter — bridge curl_cffi → httpx-compatible interface

```python
class _CffiResponseAdapter:
    """Wraps curl_cffi response to expose .status_code, .json(), .raise_for_status()"""
    def __init__(self, resp):
        self._resp = resp
        self.status_code = resp.status_code
        self.headers = resp.headers

    def json(self):
        return self._resp.json()

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=None,
                response=self,
            )
```

## 3. WildberriesScraper — set impersonate

```python
class WildberriesScraper(BaseScraper):
    _impersonate = "chrome131"   # ← ADD THIS LINE ONLY
    # everything else unchanged
```

## 4. OzonScraper — set impersonate

```python
class OzonScraper(BaseScraper):
    _impersonate = "chrome131"   # ← ADD THIS LINE ONLY
    # _HEADERS dict preserved and merged in BaseScraper._get()
    # everything else unchanged
```

## 5. BrowserPool._start() — patchright with playwright fallback

```python
async def _start(self):
    try:
        from patchright.async_api import async_playwright
        _using_patchright = True
    except ImportError:
        from playwright.async_api import async_playwright
        _using_patchright = False
        logger.warning(
            "BrowserPool: patchright not installed — falling back to playwright. "
            "CDP automation leak NOT patched. Install with: pip install patchright && patchright install chromium"
        )
    if _using_patchright:
        logger.info("BrowserPool: using patchright (Runtime.enable CDP leak patched)")

    self._playwright = await async_playwright().start()
    # rest of _start() unchanged
```

## 6. requirements.txt additions

```
curl-cffi>=0.7.0
patchright>=1.50.0
```

## 7. Error handling — curl_cffi exceptions mapping

curl_cffi raises `curl_cffi.requests.errors.RequestsError` on network failure.
BaseScraper.with_retry() catches generic `Exception` → maps to `ScraperError("API_UNAVAILABLE")`.
No changes needed to with_retry() — existing broad except covers curl_cffi errors.
