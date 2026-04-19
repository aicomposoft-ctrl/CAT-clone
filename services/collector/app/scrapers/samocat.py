"""
Samokat scraper.

Uses Samokat's mobile REST API (/v2/items/{product_id}) for product data.
A single endpoint returns content, price, AND stock fields — reducing API
calls by 2/3 vs. a three-endpoint design.
Rate limit: 2.0 req/sec (permissive darkstore API).
Image URLs validated against cdn.samokat.ru allowlist before fetching (SSRF guard).
Price values are returned as integer kopeks and divided by 100 to yield Decimal RUB.
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

# Samokat image CDN allowlist — prevents SSRF.
# Only https://cdn.samokat.ru/ images with safe path characters and a known
# image extension are permitted.  Non-matching URLs are logged and discarded.
_SK_IMAGE_CDN_RE = re.compile(
    r"^https://cdn\.samokat\.ru/[A-Za-z0-9/_\-\.]+\.(jpg|jpeg|png|webp)$"
)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _parse_product_id(raw: str | None) -> str:
    """
    Validate that ``product_id`` is a non-empty numeric string.

    Returns the stripped string if valid.
    Raises ``ValueError("NO_PRODUCT_ID")`` if ``raw`` is None or blank.
    Raises ``ScraperError("PARSE_ERROR")`` if ``raw`` contains non-digit characters.
    """
    if not raw or not raw.strip():
        raise ValueError("NO_PRODUCT_ID")
    stripped = raw.strip()
    if not stripped.isdigit():
        raise ScraperError("PARSE_ERROR", f"product_id not numeric: {stripped!r}")
    return stripped


def _kopeks_to_decimal(kopeks: int | str) -> Decimal:
    """Convert an integer kopek value to a Decimal RUB amount (divide by 100)."""
    return Decimal(kopeks) / 100


def _safe_qty(raw) -> int:
    """Return int(raw) or 0 on any conversion failure."""
    if raw is None:
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _parse_rating(raw) -> int:
    """Return int(raw) clamped to [1, 5], defaulting to 5 on failure."""
    try:
        return max(1, min(5, int(raw)))
    except (TypeError, ValueError):
        return 5


def _parse_review_date(raw: str | None) -> date:
    """Parse first 10 chars of an ISO-8601 string as a date; fall back to today."""
    try:
        return date.fromisoformat((raw or "")[:10])
    except ValueError:
        return date.today()


async def _download_image_async(url: str, proxy: str | None) -> bytes:
    """
    Download an image from the Samokat CDN.

    Re-validates the URL against ``_SK_IMAGE_CDN_RE`` before making any HTTP
    request as an internal SSRF guard — callers must not rely solely on
    pre-validation performed outside this function.

    Raises ``ValueError`` if the URL fails the allowlist check.
    Raises ``httpx.HTTPStatusError`` for non-2xx responses.
    """
    if not _SK_IMAGE_CDN_RE.match(url):
        raise ValueError("Image URL failed SSRF allowlist")
    async with httpx.AsyncClient(proxy=proxy, timeout=30.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


# ---------------------------------------------------------------------------
# SamokatScraper
# ---------------------------------------------------------------------------


class SamokatScraper(BaseScraper):
    """Scraper for Samokat darkstore using the mobile REST API (/v2/items)."""

    platform = "Samokat"
    rate_limit = 2.0  # req/sec — permissive darkstore API

    _BASE_API = "https://api.samokat.ru/v2"
    _CITY_ID = 1  # Москва — hardcoded, not user-configurable

    # Fixed headers that identify the Samokat Android mobile client.
    # X-City-Id selects the Moscow warehouse; User-Agent must match the app.
    _HEADERS = {
        "User-Agent": "SamokatApp/3.5.0 (Android)",
        "Accept": "application/json",
        "X-City-Id": "1",
    }

    def __init__(self, proxy_rotator: Optional[ProxyRotator] = None) -> None:
        from app.core.proxy import get_proxy_rotator
        super().__init__(proxy_rotator or get_proxy_rotator())

    # ── Public methods ─────────────────────────────────────────────────────

    async def collect_content(self, product_id: str) -> ContentData:
        """
        Collect product content: title, description, composition, and image URL.

        Uses GET /v2/items/{product_id} — same endpoint as price and stock.

        Raises:
            ScraperError("NOT_FOUND")       — HTTP 404
            ScraperError("API_UNAVAILABLE") — 5xx or network error after retries
            ScraperError("RATE_LIMITED")    — 429 after retries exhausted
        """
        data = await self._fetch_product(product_id)

        title = sanitize(data.get("name", ""), 500)
        if not title:
            raise ScraperError("PARSE_ERROR", "empty title for product_id=" + product_id)

        description = sanitize(data.get("description") or "", 5000)
        raw_composition = sanitize(data.get("composition") or "", 2000)
        composition: Optional[str] = raw_composition or None

        # Image: validate first image URL against CDN allowlist (SSRF guard)
        image_url: Optional[str] = None
        images = data.get("images") or []
        if images and images[0].get("url"):
            candidate = images[0]["url"]
            if _SK_IMAGE_CDN_RE.match(candidate):
                image_url = candidate
            else:
                logger.warning(
                    "Samocat image URL failed SSRF allowlist for product_id=%s — skipping",
                    product_id,
                )

        return ContentData(
            title=title,
            description=description,
            composition=composition,
            image_url=image_url,
        )

    async def collect_price(self, product_id: str) -> PriceData:
        """
        Collect current price, original price, discount percentage, and promo label.

        Price fields are returned in kopeks (integer) and converted to Decimal RUB
        by dividing by 100.

        Raises:
            ScraperError("NOT_FOUND")    — HTTP 404
            ScraperError("PARSE_ERROR")  — price fields missing or non-numeric
        """
        data = await self._fetch_product(product_id)

        try:
            price = Decimal(data["price"]) / 100
            raw_original = data.get("originalPrice") or data["price"]
            original_price = Decimal(raw_original) / 100
        except (KeyError, InvalidOperation, TypeError) as exc:
            raise ScraperError(
                "PARSE_ERROR", "price fields missing or non-numeric"
            ) from exc

        try:
            discount_pct = Decimal(data.get("discountPercent", 0))
        except (TypeError, InvalidOperation):
            discount_pct = Decimal(0)

        promo_label: Optional[str] = (
            sanitize(data.get("promoLabel") or "", 200) or None
        )

        return PriceData(
            price=price.quantize(Decimal("0.01")),
            original_price=original_price.quantize(Decimal("0.01")),
            discount_pct=discount_pct.quantize(Decimal("0.01")),
            promo_label=promo_label,
        )

    async def collect_stock(self, product_id: str) -> StockData:
        """
        Collect stock availability and available quantity.

        ``availableQuantity`` from the API is stored as ``warehouse_qty`` in
        the ``content_scores`` table.

        Raises:
            ScraperError("NOT_FOUND") — HTTP 404
        """
        data = await self._fetch_product(product_id)

        in_stock = bool(data.get("inStock", False))

        try:
            total_qty = int(data.get("availableQuantity", 0))
        except (TypeError, ValueError):
            total_qty = 0

        return StockData(in_stock=in_stock, total_qty=total_qty)

    async def collect_reviews(
        self, product_id: str, take: int = 50
    ) -> list[ReviewData]:
        """
        Collect the most recent product reviews.

        Returns an empty list on 404 — products may exist without a reviews
        endpoint being available.

        Raises:
            ScraperError("API_UNAVAILABLE") — 5xx or network error after retries
            ScraperError("RATE_LIMITED")    — 429 after retries exhausted
        """
        url = f"{self._BASE_API}/items/{product_id}/reviews"
        params = {"page": 1, "limit": take}

        async def _fetch():
            resp = await self._get(url, params=params, headers=self._HEADERS)
            if resp.status_code == 404:
                return None  # sentinel — product has no reviews endpoint
            resp.raise_for_status()
            return resp.json()

        try:
            data = await self.with_retry(_fetch)
        except ScraperError:
            raise
        except Exception as exc:
            raise ScraperError("API_UNAVAILABLE", str(exc)) from exc

        # 404 path — sentinel None returned by _fetch
        if data is None:
            return []

        raw_reviews = data.get("reviews") or []
        result: list[ReviewData] = []

        for fb in raw_reviews:
            # Treat external_review_id as untrusted scraped data: cap length and
            # strip non-printable characters before storage (security policy).
            external_id = str(fb.get("id", ""))[:200].strip()
            if not external_id:
                continue  # skip reviews without an ID — cannot deduplicate

            text = sanitize(fb.get("text") or "", 5000)
            rating = _parse_rating(fb.get("rating", 5))
            review_date = _parse_review_date(fb.get("createdAt"))

            result.append(ReviewData(
                external_review_id=external_id,
                review_text=text,
                rating=rating,
                review_date=review_date,
            ))

        return result

    def collect(self, sku_id: str, data_type: DataType) -> ScrapedData:
        """Sync entry for ScraperRouter / tasks that expect BaseScraper.collect."""
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

    async def _fetch_product(self, product_id: str) -> dict:
        """
        Fetch and return the raw JSON dict from GET /v2/items/{product_id}.

        A single endpoint provides content, price, and stock fields — avoids
        duplicate requests when all three tasks run concurrently.

        Raises:
            ScraperError("NOT_FOUND")       — HTTP 404
            ScraperError("RATE_LIMITED")    — 429/403 after retries exhausted
            ScraperError("API_UNAVAILABLE") — 5xx or network error after retries
        """
        url = f"{self._BASE_API}/items/{product_id}"

        async def _fetch():
            resp = await self._get(url, headers=self._HEADERS)
            if resp.status_code == 404:
                raise ScraperError(
                    "NOT_FOUND",
                    f"product_id={product_id} not found",
                )
            # 401/403 from Samokat API = auth required or challenge block.
            # Map to ANTIBOT_BLOCK so ScraperRouter falls through to L2.
            if resp.status_code in (401, 403):
                raise ScraperError(
                    "ANTIBOT_BLOCK",
                    f"Samokat API {resp.status_code} for product_id={product_id}",
                    details={"reason": "geo_or_auth_block", "confidence": "high"},
                )
            # raise_for_status() raises httpx.HTTPStatusError for any non-2xx
            # response — with_retry() catches that and retries 429/5xx with
            # exponential backoff before raising ScraperError.
            resp.raise_for_status()
            return resp.json()

        try:
            return await self.with_retry(_fetch)
        except ScraperError:
            raise
        except Exception as exc:
            raise ScraperError("API_UNAVAILABLE", str(exc)) from exc
