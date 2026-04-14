"""
OzonSellerAPIScraper — L0 scraper using Ozon official Seller API.

Uses the authenticated Ozon Seller API endpoints (no proxy needed):
  - Content:  api-seller.ozon.ru/v2/product/list + /v2/product/info
  - Prices:   api-seller.ozon.ru/v4/product/info/prices
  - Stock:    api-seller.ozon.ru/v3/product/info/stocks

Authentication: Client-Id + Api-Key headers (not Bearer).
The token is NEVER logged — all error messages are sanitized before logging.

The `api_token_encrypted` field stores credentials as a JSON string:
  {"client_id": "...", "api_key": "..."}
The `api_token_type` must be "ozon_seller".

This scraper is synchronous (uses httpx sync client) because it is called
from Celery tasks via ScraperRouter, which runs in a sync context.
The async collect_content/collect_price/collect_stock stubs delegate to collect()
for backward compatibility — they should not be called directly in Sprint A.
"""

from __future__ import annotations

import json as _json
import logging
import re
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

# Regex to redact Api-Key values from log messages
_API_KEY_RE = re.compile(r"(Api-Key[\":\s]+)[A-Za-z0-9._\-]+")


def _redact(msg: str) -> str:
    """Replace any Api-Key value with [REDACTED]."""
    return _API_KEY_RE.sub(r"\1[REDACTED]", msg)


class OzonSellerAPIScraper(BaseScraper):
    """
    L0 (Seller API) scraper for Ozon.

    Requires valid Ozon Seller API credentials (Client-Id + Api-Key).
    Does not use proxy rotation — official API endpoints are authenticated
    and do not block by IP.
    """

    platform = "Ozon"
    rate_limit = 5.0  # requests per second (Ozon Seller API limit)
    scraper_level = 0

    _PRODUCT_LIST = "https://api-seller.ozon.ru/v2/product/list"
    _PRODUCT_INFO = "https://api-seller.ozon.ru/v2/product/info"
    _PRICES = "https://api-seller.ozon.ru/v4/product/info/prices"
    _STOCKS = "https://api-seller.ozon.ru/v3/product/info/stocks"

    def __init__(self, token: str) -> None:
        # Do NOT call super().__init__() — we don't need ProxyRotator for L0.
        creds = _json.loads(token)
        self._headers = {
            "Client-Id": creds["client_id"],
            "Api-Key": creds["api_key"],
            "Content-Type": "application/json",
        }

    # ── Unified synchronous collect() — primary interface ─────────────────

    def collect(self, sku_id: str, data_type: DataType) -> ScrapedData:
        """
        Synchronous collect dispatch used by ScraperRouter.

        The sku_id is the Ozon product ID (integer as string).

        Raises:
            ScraperError("TOKEN_INVALID")   — HTTP 401/403
            ScraperError("RATE_LIMITED")    — HTTP 429
            ScraperError("API_UNAVAILABLE") — 5xx / connection error
            ScraperError("NOT_FOUND")       — product not in API response
            ScraperError("PARSE_ERROR")     — unexpected response structure
        """
        if data_type == DataType.CONTENT:
            return self._collect_content(sku_id)
        if data_type == DataType.PRICE:
            return self._collect_price(sku_id)
        if data_type == DataType.STOCK:
            return self._collect_stock(sku_id)
        if data_type == DataType.REVIEWS:
            # Ozon Seller API does not provide a reviews endpoint — fall through
            raise ScraperError(
                "API_UNAVAILABLE",
                "Ozon Seller API does not support reviews; use L1/L2 scraper",
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
        """Execute a synchronous HTTP request with common error handling."""
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.request(
                    method,
                    url,
                    headers=self._headers,
                    json=json,
                    params=params,
                )
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            raise ScraperError("API_UNAVAILABLE", _redact(str(exc))) from exc

        if resp.status_code in (401, 403):
            raise ScraperError("TOKEN_INVALID", "Ozon Seller API: auth error")
        if resp.status_code == 429:
            raise ScraperError("RATE_LIMITED", "Ozon Seller API: 429 Too Many Requests")
        if resp.status_code >= 500:
            raise ScraperError(
                "API_UNAVAILABLE",
                f"Ozon Seller API: {resp.status_code} {_redact(resp.text[:200])}",
            )

        try:
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            raise ScraperError("API_UNAVAILABLE", _redact(str(exc))) from exc
        except Exception as exc:
            raise ScraperError("PARSE_ERROR", f"JSON decode error: {exc}") from exc

    def _collect_content(self, product_id: str) -> ContentData:
        """
        Fetch card content from Ozon Seller API.

        Step 1 — list endpoint to confirm product existence:
          POST /v2/product/list
          {"filter": {"offer_id": [], "product_id": [<id>], "visibility": "ALL"},
           "last_id": "", "limit": 1}

        Step 2 — detail endpoint for full content:
          POST /v2/product/info
          {"product_id": <id>}

        Response has: name, description, primary_image, attributes
        """
        try:
            pid = int(product_id)
        except ValueError as exc:
            raise ScraperError("PARSE_ERROR", f"product_id is not numeric: {product_id!r}") from exc

        # Step 1: verify product exists via list endpoint
        list_body = {
            "filter": {
                "offer_id": [],
                "product_id": [pid],
                "visibility": "ALL",
            },
            "last_id": "",
            "limit": 1,
        }
        list_data = self._request("POST", self._PRODUCT_LIST, json=list_body)
        items = (list_data.get("result") or {}).get("items") or []
        if not items:
            raise ScraperError("NOT_FOUND", f"No product found for product_id={product_id}")

        # Step 2: fetch full product details
        info_body = {"product_id": pid}
        info_data = self._request("POST", self._PRODUCT_INFO, json=info_body)
        result = info_data.get("result") or {}

        # Extract composition from attributes array
        composition: Optional[str] = None
        for attr in result.get("attributes") or []:
            attr_name = str(attr.get("name") or "").lower()
            if "состав" in attr_name or "composition" in attr_name:
                values = attr.get("values") or []
                if values:
                    composition = sanitize(str(values[0].get("value") or ""), 2000)
                break

        image_url: Optional[str] = result.get("primary_image") or None

        return ContentData(
            title=sanitize(result.get("name") or "", 500),
            description=sanitize(result.get("description") or "", 5000),
            composition=composition,
            image_url=image_url,
        )

    def _collect_price(self, product_id: str) -> PriceData:
        """
        Fetch price data from Ozon Seller Prices API.

        POST /v4/product/info/prices
        {"filter": {"offer_id": [], "product_id": [<id>], "visibility": "ALL"},
         "limit": 1, "last_id": ""}

        Response:
          {"result": {"items": [{"price": {"price": "999.00", "old_price": "1199.00"}}]}}
        """
        try:
            pid = int(product_id)
        except ValueError as exc:
            raise ScraperError("PARSE_ERROR", f"product_id is not numeric: {product_id!r}") from exc

        body = {
            "filter": {
                "offer_id": [],
                "product_id": [pid],
                "visibility": "ALL",
            },
            "limit": 1,
            "last_id": "",
        }
        data = self._request("POST", self._PRICES, json=body)

        items = (data.get("result") or {}).get("items") or []
        if not items:
            raise ScraperError("NOT_FOUND", f"No price data for product_id={product_id}")

        price_info = items[0].get("price") or {}

        try:
            price = Decimal(str(price_info.get("price") or 0))
            old_price_raw = price_info.get("old_price") or "0"
            original = Decimal(str(old_price_raw))
        except InvalidOperation as exc:
            raise ScraperError("PARSE_ERROR", f"Invalid price values in response: {exc}") from exc

        # Use old_price as original only when it is greater than current price
        if original > 0 and original >= price:
            discount = ((original - price) / original * 100).quantize(Decimal("0.01"))
        else:
            discount = Decimal("0.00")
            original = price

        return PriceData(
            price=price,
            original_price=original,
            discount_pct=discount,
            promo_label=None,  # Ozon Seller prices API does not expose promo labels
        )

    def _collect_stock(self, product_id: str) -> StockData:
        """
        Fetch warehouse stock from Ozon Seller Stocks API.

        POST /v3/product/info/stocks
        {"filter": {"offer_id": [], "product_id": [<id>], "visibility": "ALL"},
         "limit": 1, "last_id": ""}

        Response:
          {"result": {"items": [{"stocks": [{"present": 10, "reserved": 2, "type": "fbo"}]}]}}

        Totals all warehouse types (fbo, fbs, etc.) to compute overall quantity.
        """
        try:
            pid = int(product_id)
        except ValueError as exc:
            raise ScraperError("PARSE_ERROR", f"product_id is not numeric: {product_id!r}") from exc

        body = {
            "filter": {
                "offer_id": [],
                "product_id": [pid],
                "visibility": "ALL",
            },
            "limit": 1,
            "last_id": "",
        }
        data = self._request("POST", self._STOCKS, json=body)

        items = (data.get("result") or {}).get("items") or []
        if not items:
            raise ScraperError("NOT_FOUND", f"No stock data for product_id={product_id}")

        total_qty = 0
        for stock_entry in items[0].get("stocks") or []:
            total_qty += int(stock_entry.get("present") or 0)

        return StockData(in_stock=total_qty > 0, total_qty=total_qty)

    # ── Backward-compat async stubs ────────────────────────────────────────
    # These satisfy BaseScraper's abstract interface but should not be called
    # directly in Sprint A. ScraperRouter always uses the sync collect() method.

    async def collect_content(self, product_id: str) -> ContentData:  # type: ignore[override]
        return self._collect_content(product_id)

    async def collect_price(self, product_id: str) -> PriceData:  # type: ignore[override]
        return self._collect_price(product_id)

    async def collect_stock(self, product_id: str) -> StockData:  # type: ignore[override]
        return self._collect_stock(product_id)

    async def collect_reviews(self, product_id: str, take: int = 50) -> list[ReviewData]:  # type: ignore[override]
        raise ScraperError(
            "API_UNAVAILABLE",
            "Ozon Seller API does not support reviews; use L1/L2 scraper",
        )
