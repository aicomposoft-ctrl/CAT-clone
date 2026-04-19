"""
WBSellerAPIScraper — L0 scraper using Wildberries official Seller Content API.

Uses the authenticated WB Seller API endpoints (no proxy needed):
  - Content:  content-api.wildberries.ru/content/v2/get/cards/list
  - Prices:   discounts-prices-api.wildberries.ru/api/v2/list/goods/filter
  - Stock:    statistics-api.wildberries.ru/api/v1/supplier/stocks (warehouse stock)

Authentication: Bearer token passed at construction time.
The token is NEVER logged — all error messages are sanitized before logging.

This scraper is synchronous (uses httpx sync client) because it is called
from Celery tasks via ScraperRouter, which runs in a sync context.
The async collect_content/collect_price/collect_stock stubs delegate to collect()
for backward compatibility — they should not be called directly in Sprint A.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

import httpx

from app.core.base_scraper import (
    BaseScraper,
    ContentData,
    DataType,
    PriceData,
    ReviewData,
    ScrapedData,
    ScraperError,
    StockData,
)
from app.core.sanitize import sanitize

logger = logging.getLogger(__name__)

# Regex to redact Bearer tokens from log messages
_BEARER_RE = re.compile(r"Bearer [A-Za-z0-9._\-]+")


def _redact(msg: str) -> str:
    """Replace any Bearer token value with [REDACTED]."""
    return _BEARER_RE.sub("Bearer [REDACTED]", msg)


class WBSellerAPIScraper(BaseScraper):
    """
    L0 (Seller API) scraper for Wildberries.

    Requires a valid WB Seller API token. Does not use proxy rotation —
    official API endpoints are authenticated and do not block by IP.
    """

    platform = "Wildberries"
    rate_limit = 5.0  # requests per second (WB Seller API limit)
    scraper_level = 0

    _CARDS_LIST = "https://content-api.wildberries.ru/content/v2/get/cards/list"
    _PRICES = "https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter"
    _STOCKS = "https://statistics-api.wildberries.ru/api/v1/supplier/stocks"

    def __init__(self, token: str) -> None:
        # Do NOT call super().__init__() — we don't need ProxyRotator for L0.
        self._token = token
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        # Reuse a single httpx.Client for connection pooling (TLS handshake once)
        self._client = httpx.Client(timeout=30.0)
        self._min_interval = 1.0 / self.rate_limit  # seconds between requests
        self._last_request_at: float = 0.0

    # ── Unified synchronous collect() — primary interface ─────────────────

    def collect(self, sku_id: str, data_type: DataType) -> ScrapedData:
        """
        Synchronous collect dispatch used by ScraperRouter.

        Raises:
            ScraperError("TOKEN_INVALID")  — HTTP 401
            ScraperError("RATE_LIMITED")   — HTTP 429
            ScraperError("API_UNAVAILABLE") — 5xx / connection error
            ScraperError("NOT_FOUND")      — product not in API response
            ScraperError("PARSE_ERROR")    — unexpected response structure
        """
        # Validate nm_id is numeric once before dispatching
        try:
            int(sku_id)
        except (ValueError, TypeError):
            raise ScraperError("PARSE_ERROR", f"WB nm_id must be numeric, got: {sku_id!r}")

        if data_type == DataType.CONTENT:
            return self._collect_content(sku_id)
        if data_type == DataType.PRICE:
            return self._collect_price(sku_id)
        if data_type == DataType.STOCK:
            return self._collect_stock(sku_id)
        if data_type == DataType.REVIEWS:
            # WB Seller API does not provide a reviews endpoint — fall through
            raise ScraperError(
                "API_UNAVAILABLE",
                "WB Seller API does not support reviews; use L1/L2 scraper",
            )
        raise ScraperError("PARSE_ERROR", f"Unknown DataType: {data_type}")

    # ── Private implementation helpers ─────────────────────────────────────

    def _request(
        self,
        method: str,
        url: str,
        *,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        """Execute a synchronous HTTP request with rate limiting and common error handling."""
        # Enforce rate_limit (requests per second) without ProxyRotator semaphore
        elapsed = time.monotonic() - self._last_request_at
        wait = self._min_interval - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

        try:
            resp = self._client.request(
                method,
                url,
                headers=self._headers,
                json=json,
                params=params,
            )
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            raise ScraperError("API_UNAVAILABLE", _redact(str(exc))) from exc

        if resp.status_code == 401:
            raise ScraperError("TOKEN_INVALID", "WB Seller API: 401 Unauthorized")
        if resp.status_code == 429:
            raise ScraperError("RATE_LIMITED", "WB Seller API: 429 Too Many Requests")
        if resp.status_code >= 500:
            raise ScraperError(
                "API_UNAVAILABLE",
                f"WB Seller API: {resp.status_code} {_redact(resp.text[:200])}",
            )

        try:
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            raise ScraperError("API_UNAVAILABLE", _redact(str(exc))) from exc
        except Exception as exc:
            raise ScraperError("PARSE_ERROR", f"JSON decode error: {exc}") from exc

    def _collect_content(self, nm_id: str) -> ContentData:
        """
        Fetch card content from WB Seller Content API.

        Request body:
          {"settings": {"cursor": {"limit": 1}, "filter": {"nmIDs": [<nm_id>]}}}

        Response:
          {"cards": [{"title": ..., "description": ..., "characteristics": [...], "photos": [...]}]}
        """
        body = {
            "settings": {
                "cursor": {"limit": 1},
                "filter": {"nmIDs": [int(nm_id)]},
            }
        }
        data = self._request("POST", self._CARDS_LIST, json=body)

        cards = data.get("cards") or []
        if not cards:
            raise ScraperError("NOT_FOUND", f"No cards returned for nm_id={nm_id}")

        card = cards[0]
        returned_nm = card.get("nmID") or card.get("nmId") or "unknown"
        returned_title = (card.get("title") or "")[:80]
        logger.info(
            "WBSellerAPIScraper._collect_content: queried nm_id=%s → returned nmID=%s title=%r",
            nm_id,
            returned_nm,
            returned_title,
        )

        # Extract composition from characteristics array
        composition: Optional[str] = None
        for char in card.get("characteristics") or []:
            for key, value in char.items():
                if "состав" in key.lower() or "composition" in key.lower():
                    composition = sanitize(str(value), 2000)
                    break
            if composition:
                break

        # Use first photo URL if available
        photos = card.get("photos") or []
        image_url: Optional[str] = photos[0].get("big") if photos else None

        return ContentData(
            title=sanitize(card.get("title") or "", 500),
            description=sanitize(card.get("description") or "", 5000),
            composition=composition,
            image_url=image_url,
        )

    def _collect_price(self, nm_id: str) -> PriceData:
        """
        Fetch price data from WB Discounts & Prices API.

        GET /api/v2/list/goods/filter?nmId=<nm_id>
        Response: {"data": {"listGoods": [{"nmID": ..., "sizes": [{"price": ..., "discountedPrice": ...}]}]}}
        """
        data = self._request("GET", self._PRICES, params={"nmId": int(nm_id), "limit": 1})

        goods = (data.get("data") or {}).get("listGoods") or []
        if not goods:
            raise ScraperError("NOT_FOUND", f"No price data for nm_id={nm_id}")

        good = goods[0]
        sizes = good.get("sizes") or []
        size = sizes[0] if sizes else {}

        try:
            # /api/v2/list/goods/filter returns prices in KOPECKS — divide by 100.
            raw_discounted = size.get("discountedPrice") or size.get("price") or 0
            raw_base = size.get("price") or raw_discounted
            price = Decimal(str(raw_discounted)) / 100
            original = Decimal(str(raw_base)) / 100
        except InvalidOperation as exc:
            raise ScraperError("PARSE_ERROR", f"Invalid price values in response: {exc}") from exc

        if original > 0 and original >= price:
            discount = ((original - price) / original * 100).quantize(Decimal("0.01"))
        else:
            discount = Decimal("0.00")
            original = price

        return PriceData(
            price=price,
            original_price=original,
            discount_pct=discount,
            promo_label=None,  # WB Seller prices API does not expose promo labels
        )

    def _collect_stock(self, nm_id: str) -> StockData:
        """
        Fetch warehouse stock from WB Statistics API.

        GET /api/v1/supplier/stocks?dateFrom=<today>&nmId=<nm_id>
        Response: [{"nmId": ..., "quantity": ..., "inWayToClient": ..., ...}]
        """
        try:
            nm = int(nm_id)
        except ValueError as exc:
            raise ScraperError("PARSE_ERROR", f"nm_id is not numeric: {nm_id!r}") from exc

        today = date.today().isoformat()
        # Pass nmId as filter to avoid fetching the entire supplier catalog
        data = self._request("GET", self._STOCKS, params={"dateFrom": today, "nmId": nm})

        total_qty = 0
        if isinstance(data, list):
            for entry in data:
                total_qty += int(entry.get("quantity") or 0)
        else:
            logger.warning(
                "WBSellerAPIScraper._collect_stock: unexpected response type %s", type(data)
            )

        return StockData(in_stock=total_qty > 0, total_qty=total_qty)

    # ── Backward-compat async stubs ────────────────────────────────────────
    # These satisfy BaseScraper's abstract interface but should not be called
    # directly in Sprint A. ScraperRouter always uses the sync collect() method.

    async def collect_content(self, nm_id: str) -> ContentData:  # type: ignore[override]
        return self._collect_content(nm_id)

    async def collect_price(self, nm_id: str) -> PriceData:  # type: ignore[override]
        return self._collect_price(nm_id)

    async def collect_stock(self, nm_id: str) -> StockData:  # type: ignore[override]
        return self._collect_stock(nm_id)

    async def collect_reviews(self, nm_id: str, take: int = 50) -> list[ReviewData]:  # type: ignore[override]
        raise ScraperError(
            "API_UNAVAILABLE",
            "WB Seller API does not support reviews; use L1/L2 scraper",
        )
