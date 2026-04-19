"""
Abstract base class for all CAT scrapers.

Every scraper must:
  - Declare `platform` class attribute matching Platform.name in DB.
  - Set `rate_limit` (requests per second).
  - Implement the four abstract collect_* methods.
  - Use `_get()` for all HTTP requests — handles rate limiting, proxy, and retry.

New in Sprint A:
  - `scraper_level` class attribute (0=seller API, 1=L1 scraper, 2=L2, 3=L3)
  - `DataType` enum for use with unified `collect()` method
  - `ScrapedData` union type returned by `collect()`
  - `collect()` abstract method — unified entry point for ScraperRouter

Anti-bot upgrade (anti-bot-http-upgrade feature):
  - Subclasses set `_impersonate = "chrome131"` to enable curl_cffi TLS impersonation.
  - When `_impersonate` is set, `_get()` uses curl_cffi AsyncSession instead of httpx.
  - curl_cffi replicates Chrome 131 JA3/JA4/HTTP2 fingerprints, bypassing Akamai/Cloudflare
    TLS-layer detection that blocks plain httpx.
  - Scrapers without `_impersonate` (Lenta, Samocat) continue using httpx unchanged.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional, Union

import httpx

from app.core.proxy import ProxyRotator

logger = logging.getLogger(__name__)

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

# Sec-Ch-Ua headers matching Chrome 131 — required alongside TLS impersonation
# to present a consistent browser identity to Akamai/Cloudflare header inspection.
_CHROME131_SEC_HEADERS = {
    "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Accept-Encoding": "gzip, deflate, br",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ContentData:
    title: str
    description: str
    composition: Optional[str]
    image_url: Optional[str]


@dataclass
class PriceData:
    price: Decimal
    original_price: Decimal
    discount_pct: Decimal
    promo_label: Optional[str]


@dataclass
class StockData:
    in_stock: bool
    total_qty: int


@dataclass
class ReviewData:
    external_review_id: str
    review_text: str
    rating: int
    review_date: date


# Union type for all possible return values from collect()
ScrapedData = Union[ContentData, PriceData, StockData, list[ReviewData]]


class DataType(Enum):
    """Selects which data to collect in the unified collect() interface."""
    CONTENT = "content"
    PRICE = "price"
    STOCK = "stock"
    REVIEWS = "reviews"


class ScraperError(Exception):
    """Domain error raised by scrapers with a machine-readable code."""

    def __init__(self, code: str, message: str = "", *, details: Optional[dict] = None) -> None:
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(f"{code}: {message}")


# ---------------------------------------------------------------------------
# curl_cffi response adapter — bridges curl_cffi → httpx-compatible interface
# ---------------------------------------------------------------------------

class _CffiResponseAdapter:
    """
    Wraps a curl_cffi response object to expose the same interface as httpx.Response.

    BaseScraper.with_retry() catches httpx.HTTPStatusError — raise_for_status()
    must preserve this contract.  We raise httpx.HTTPStatusError with a minimal
    stub request object to avoid crashing httpx internals (request=None would).
    """

    def __init__(self, resp) -> None:
        self._resp = resp
        self.status_code: int = resp.status_code
        self.headers = resp.headers

    def json(self):
        return self._resp.json()

    @property
    def text(self) -> str:
        return self._resp.text

    @property
    def content(self) -> bytes:
        return self._resp.content

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            # Build a minimal stub request so httpx internals don't crash on None
            stub_request = httpx.Request("GET", str(getattr(self._resp, "url", "https://unknown")))
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=stub_request,
                response=self,  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# Base scraper
# ---------------------------------------------------------------------------

class BaseScraper(ABC):
    platform: str
    rate_limit: float  # requests per second
    scraper_level: int = 1  # 0=seller API, 1=L1, 2=L2, 3=L3
    _impersonate: Optional[str] = None  # set to "chrome131" in WB/Ozon scrapers

    def __init__(self, proxy_rotator: ProxyRotator) -> None:
        self._proxy = proxy_rotator
        self._ua_idx = 0
        # Serialise requests: 1 concurrent call respects rate_limit sleep
        self._semaphore = asyncio.Semaphore(1)

    def _next_ua(self) -> str:
        ua = _USER_AGENTS[self._ua_idx % len(_USER_AGENTS)]
        self._ua_idx += 1
        return ua

    async def _get(self, url: str, **kwargs) -> httpx.Response:
        """
        Async GET with rate limiting, proxy rotation, and user-agent rotation.

        When `_impersonate` is set on the subclass, routes through curl_cffi
        AsyncSession with Chrome 131 TLS/JA3/HTTP2 impersonation.  Proxy is
        passed per-request (not frozen at session init) so ProxyRotator works.
        """
        async with self._semaphore:
            await asyncio.sleep(1.0 / self.rate_limit)
            proxy = self._proxy.next()
            headers = kwargs.pop("headers", {})
            headers.setdefault("User-Agent", self._next_ua())

            if self._impersonate:
                try:
                    from curl_cffi.requests import AsyncSession
                except ImportError as exc:
                    raise ScraperError(
                        "API_UNAVAILABLE", "curl_cffi not installed"
                    ) from exc
                proxies = {"http": proxy, "https": proxy} if proxy else None
                merged_headers = {**_CHROME131_SEC_HEADERS, **headers}
                async with AsyncSession(impersonate=self._impersonate) as session:
                    resp = await session.get(
                        url,
                        headers=merged_headers,
                        proxies=proxies,
                        timeout=30,
                        **kwargs,
                    )
                return _CffiResponseAdapter(resp)

            async with httpx.AsyncClient(proxy=proxy, timeout=30.0, follow_redirects=True) as client:
                return await client.get(url, headers=headers, **kwargs)

    async def with_retry(self, coro_fn, max_retries: int = 3):
        """
        Retry an async callable on transient HTTP errors with exponential backoff.
        Raises ScraperError("RATE_LIMITED") after exhausting retries on 429.
        Raises ScraperError("API_UNAVAILABLE") after exhausting retries on 5xx/connection error.
        """
        last_exc = None
        for attempt in range(max_retries):
            try:
                return await coro_fn()
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code == 429:
                    if attempt == max_retries - 1:
                        raise ScraperError("RATE_LIMITED", str(exc)) from exc
                elif exc.response.status_code >= 500:
                    if attempt == max_retries - 1:
                        raise ScraperError("API_UNAVAILABLE", str(exc)) from exc
                elif exc.response.status_code in (401, 403):
                    # Anti-bot / auth challenge — signal ScraperRouter to try L2
                    raise ScraperError(
                        "ANTIBOT_BLOCK",
                        f"HTTP {exc.response.status_code} — anti-bot or auth challenge",
                    ) from exc
                else:
                    raise  # other 4xx: don't retry
                await asyncio.sleep(2 ** attempt)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt == max_retries - 1:
                    raise ScraperError("API_UNAVAILABLE", str(exc)) from exc
                await asyncio.sleep(2 ** attempt)

        raise ScraperError("API_UNAVAILABLE", str(last_exc))

    @abstractmethod
    async def collect_content(self, nm_id: str) -> ContentData: ...

    @abstractmethod
    async def collect_price(self, nm_id: str) -> PriceData: ...

    @abstractmethod
    async def collect_stock(self, nm_id: str) -> StockData: ...

    @abstractmethod
    async def collect_reviews(self, nm_id: str, take: int = 50) -> list[ReviewData]: ...

    @abstractmethod
    def collect(self, sku_id: str, data_type: DataType) -> ScrapedData:
        """
        Unified synchronous entry point used by ScraperRouter.

        Implementations dispatch to the appropriate collect_* method.
        Must be synchronous — called from Celery tasks which use sync sessions.
        """
        ...
