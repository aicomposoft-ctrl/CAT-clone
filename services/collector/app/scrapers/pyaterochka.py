"""
Pyaterochka (5ka.ru) scraper.

Uses the public catalog REST API (/api/v1/products/{plu}) for product data.
No authentication required — standard CORS-accessible JSON API.
Rate limit: 2.0 req/sec (conservative — mid-size retailer).
Image URLs validated against images.5ka.ru allowlist before fetching (SSRF guard).
Price values are returned as decimal strings (e.g. "129.99") in RUB.

PLU (Product Lookup Unit) is the numeric product identifier — matches external_id
in the sku_platforms table.  To find a product's PLU: browse 5ka.ru, open the
product page, the URL is /product/{slug}-{plu}/ or check Network tab for the API call.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import date
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
from app.core.proxy import ProxyRotator
from app.core.sanitize import sanitize

logger = logging.getLogger(__name__)

# Pyaterochka image CDN allowlist — SSRF guard.
# Domain-anchored only: any path/query params are allowed once the origin is trusted.
# 5ka CDN hosts include images.5ka.ru, cdn.5ka.ru, static.5ka.ru, img.5ka.ru.
_5KA_IMAGE_CDN_RE = re.compile(
    r"^https://([a-z0-9\-]+\.)?5ka\.ru/"
)


def _parse_price(raw) -> Decimal:
    """Parse a price value that may be a string, int, or float into Decimal RUB."""
    if raw is None:
        raise ScraperError("PARSE_ERROR", "price field is None")
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ScraperError("PARSE_ERROR", f"invalid price value: {raw!r}") from exc


def _parse_review_date(raw: str | None) -> date:
    """Parse first 10 chars of an ISO-8601 string as a date; fall back to today."""
    try:
        return date.fromisoformat((raw or "")[:10])
    except ValueError:
        return date.today()


async def _download_image_async(url: str, proxy: str | None) -> bytes:
    """
    Download an image from the Pyaterochka CDN.

    Re-validates the URL against _5KA_IMAGE_CDN_RE before any HTTP request
    as an internal SSRF guard.

    Raises ValueError if the URL fails the allowlist check.
    Raises httpx.HTTPStatusError for non-2xx responses.
    """
    if not _5KA_IMAGE_CDN_RE.match(url):
        raise ValueError("Image URL failed SSRF allowlist")
    async with httpx.AsyncClient(proxy=proxy, timeout=30.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


# ---------------------------------------------------------------------------
# PyaterochkaScraper
# ---------------------------------------------------------------------------


class PyaterochkaScraper(BaseScraper):
    """Scraper for Pyaterochka (5ka.ru) using the public catalog REST API."""

    platform = "Пятёрочка"
    rate_limit = 2.0  # req/sec — mid-size retailer, not a high-volume marketplace

    _BASE_API = "https://5ka.ru/api/v1"

    # Standard browser headers — 5ka.ru doesn't require special auth headers.
    _HEADERS = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Referer": "https://5ka.ru/",
    }

    def __init__(self, proxy_rotator: Optional[ProxyRotator] = None) -> None:
        from app.core.proxy import get_proxy_rotator
        super().__init__(proxy_rotator or get_proxy_rotator())

    # ── Public methods ─────────────────────────────────────────────────────

    async def collect_content(self, plu: str) -> ContentData:
        """
        Collect product content: title, description, composition, and image URL.

        Uses GET /api/v1/products/{plu}/ — same endpoint as price and stock.

        Raises:
            ScraperError("NOT_FOUND")       — HTTP 404
            ScraperError("API_UNAVAILABLE") — 5xx or network error after retries
            ScraperError("RATE_LIMITED")    — 429 after retries exhausted
        """
        data = await self._fetch_product(plu)

        title = sanitize(data.get("name", ""), 500)
        if not title:
            raise ScraperError("PARSE_ERROR", f"empty title for plu={plu}")

        # Description: prefer "description" field, fall back to "category" path
        description = sanitize(data.get("description") or data.get("subtitle") or "", 5000)

        # Composition: 5ka often stores this in "attributes" list
        composition: Optional[str] = None
        for attr in data.get("attributes") or []:
            if "состав" in (attr.get("title") or "").lower():
                composition = sanitize(attr.get("value") or "", 2000) or None
                break

        # Image: validate first image URL against CDN allowlist (SSRF guard).
        # Search API: images = {"medium": "https://...", "large": "https://..."}
        # Detail API: images may also be a list [{url: "..."}]
        image_url: Optional[str] = None
        images = data.get("images") or data.get("image") or {}
        if isinstance(images, dict):
            candidate = images.get("large") or images.get("medium") or images.get("small")
        elif isinstance(images, list) and images:
            first = images[0]
            candidate = first.get("url") if isinstance(first, dict) else str(first)
        elif isinstance(images, str):
            candidate = images
        else:
            candidate = None

        if candidate and _5KA_IMAGE_CDN_RE.match(str(candidate)):
            image_url = str(candidate)
        elif candidate:
            logger.warning(
                "Pyaterochka image URL failed SSRF allowlist for plu=%s — skipping", plu
            )

        return ContentData(
            title=title,
            description=description,
            composition=composition,
            image_url=image_url,
        )

    async def collect_price(self, plu: str) -> PriceData:
        """
        Collect current price, original price, discount percentage, and promo label.

        Search API response format:
          "special_price": {"price": "129.99", "discount": "30", "label": "Акция"}  — promo price
          "regular_price": {"price": "185.99"}                                        — normal price
        Detail API may also use top-level "price" / "promo_price" fields.

        Raises:
            ScraperError("NOT_FOUND")    — HTTP 404
            ScraperError("PARSE_ERROR")  — price fields missing or non-numeric
        """
        data = await self._fetch_product(plu)

        # Unified extraction: works for both detail API and search API response shapes
        special = data.get("special_price") or {}
        regular = data.get("regular_price") or {}

        raw_price = (
            special.get("price") or
            regular.get("price") or
            data.get("promo_price") or
            data.get("price")
        )
        raw_original = regular.get("price") or raw_price

        price = _parse_price(raw_price)
        original_price = _parse_price(raw_original)

        if original_price > Decimal("0") and original_price >= price:
            discount_pct = (
                (original_price - price) / original_price * 100
            ).quantize(Decimal("0.01"))
        else:
            discount_pct = Decimal("0.00")
            original_price = price

        promo_label: Optional[str] = (
            sanitize(
                data.get("promo_text") or
                special.get("label") or
                data.get("label") or
                "",
                255,
            ) or None
        )

        return PriceData(
            price=price,
            original_price=original_price,
            discount_pct=discount_pct,
            promo_label=promo_label,
        )

    async def collect_stock(self, plu: str) -> StockData:
        """
        Collect stock availability.

        5ka.ru API does not expose warehouse quantity — only in_stock flag derived
        from whether the product is available for purchase.
        """
        data = await self._fetch_product(plu)

        # "is_available" flag or infer from price presence
        in_stock = bool(
            data.get("is_available") or
            data.get("in_stock") or
            (data.get("regular_price") and data["regular_price"].get("price"))
        )

        return StockData(in_stock=in_stock, total_qty=0)

    async def collect_reviews(self, plu: str, take: int = 50) -> list[ReviewData]:
        """
        Collect the most recent product reviews.

        5ka.ru product reviews endpoint: /api/v2/products/{plu}/reviews/
        Returns an empty list if reviews are unavailable or the product doesn't exist.

        Raises:
            ScraperError("API_UNAVAILABLE") — 5xx or network error after retries
            ScraperError("RATE_LIMITED")    — 429 after retries exhausted
        """
        url = f"https://5ka.ru/api/v2/products/{plu}/reviews/"
        params = {"records_per_page": min(take, 50), "page_num": 1}

        async def _fetch():
            resp = await self._get(url, params=params, headers=self._HEADERS)
            if resp.status_code == 404:
                return None  # no reviews endpoint for this product
            resp.raise_for_status()
            return resp.json()

        try:
            data = await self.with_retry(_fetch)
        except ScraperError as exc:
            if exc.code in ("NOT_FOUND",):
                return []
            raise

        if data is None:
            return []

        results = data if isinstance(data, list) else data.get("results") or []
        reviews: list[ReviewData] = []

        for item in results:
            ext_id = item.get("id") or item.get("review_id")
            if not ext_id:
                continue

            try:
                review_date = _parse_review_date(item.get("created_at") or item.get("date"))
            except Exception:  # noqa: BLE001
                review_date = date.today()

            raw_rating = item.get("rating") or item.get("grade") or 5
            rating = max(1, min(5, int(raw_rating)))

            reviews.append(ReviewData(
                external_review_id=str(ext_id),
                review_text=sanitize(item.get("text") or item.get("body") or "", 5000),
                rating=rating,
                review_date=review_date,
            ))

        return reviews

    def collect(self, sku_id: str, data_type: DataType) -> ScrapedData:
        """Sync entry point for ScraperRouter."""
        if data_type == DataType.CONTENT:
            return asyncio.run(self.collect_content(sku_id))
        if data_type == DataType.PRICE:
            return asyncio.run(self.collect_price(sku_id))
        if data_type == DataType.STOCK:
            return asyncio.run(self.collect_stock(sku_id))
        if data_type == DataType.REVIEWS:
            return asyncio.run(self.collect_reviews(sku_id))
        raise ScraperError("PARSE_ERROR", f"Unknown DataType: {data_type}")

    # ── Private helpers ────────────────────────────────────────────────────

    async def _fetch_product(self, plu: str) -> dict:
        """
        Fetch product data from 5ka.ru.

        Tries two endpoints in order:
          1. Product detail API: GET /api/v1/products/{plu}/
             — can return 403 if CF protection is active.
          2. Search API: GET /api/v2/search/?search_text={plu}&records_per_page=3
             — public endpoint, no CF block observed.

        Raises:
            ScraperError("NOT_FOUND")       — product not found on either endpoint
            ScraperError("API_UNAVAILABLE") — all endpoints failed after retries
            ScraperError("RATE_LIMITED")    — HTTP 429
        """
        if not plu or not str(plu).strip().isdigit():
            raise ScraperError("PARSE_ERROR", f"plu is not numeric: {plu!r}")

        # --- Attempt 1: product detail API ---
        detail_url = f"{self._BASE_API}/products/{plu}/"
        try:
            async def _fetch_detail():
                resp = await self._get(detail_url, headers=self._HEADERS)
                if resp.status_code == 404:
                    raise ScraperError("NOT_FOUND", f"product plu={plu} not found (detail API)")
                if resp.status_code == 403:
                    raise ScraperError("API_UNAVAILABLE", f"403 from detail API — trying search fallback")
                resp.raise_for_status()
                return resp.json()

            return await self.with_retry(_fetch_detail)
        except ScraperError as exc:
            if exc.code not in ("API_UNAVAILABLE", "RATE_LIMITED"):
                raise
            if exc.code == "RATE_LIMITED":
                raise
            logger.info(
                "PyaterochkaScraper: detail API blocked for plu=%s (%s) — trying search API",
                plu, exc.message if hasattr(exc, "message") else exc,
            )

        # --- Attempt 2: public search API (not behind CF) ---
        search_url = "https://5ka.ru/api/v2/search/"
        params = {"records_per_page": 3, "page_num": 1, "search_text": plu}

        async def _fetch_search():
            resp = await self._get(search_url, params=params, headers=self._HEADERS)
            if resp.status_code == 404:
                raise ScraperError("NOT_FOUND", f"product plu={plu} not found (search API)")
            resp.raise_for_status()
            return resp.json()

        data = await self.with_retry(_fetch_search)

        results = data.get("results") or []
        # Match by PLU (the search_text IS the PLU, so first result is correct)
        for item in results:
            if str(item.get("plu") or item.get("id") or "") == str(plu):
                return item
        if results:
            # Take first result if no exact PLU match (shouldn't happen for numeric search)
            return results[0]

        raise ScraperError("NOT_FOUND", f"product plu={plu} not found in search results")
