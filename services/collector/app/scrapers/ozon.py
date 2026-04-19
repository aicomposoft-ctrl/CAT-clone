"""
Ozon scraper.

Uses Ozon's composer API (double-JSON widgetStates pattern) for product data.
Rate limit: 0.5 req/sec (1 request per 2 seconds — more conservative than WB).
Image URLs validated against Ozon CDN allowlist before fetching (SSRF guard).
"""

from __future__ import annotations

import asyncio
import json
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

# Ozon image CDN allowlist — prevents SSRF. Path segments use full alphanumeric
# hashes (not hex-only), so we use [a-z0-9] not [a-f0-9].
_OZ_IMAGE_CDN_RE = re.compile(
    r"^https://ir\.ozone\.ru/s3/multimedia-[a-z0-9]+/[a-z0-9]+/(?:wc\d+/)?[a-z0-9]+\.jpg$"
)

# Widget name prefixes present in Ozon composer API responses
_KNOWN_WIDGETS = [
    "webProductHeading-",
    "webPrice-",
    "webDetailSKU-",
    "webGallery-",
    "webAddToCart-",
    "webReviewList-",
]


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _parse_widget_states(data: dict) -> dict:
    """
    Parse Ozon's double-JSON widgetStates structure.

    The outer response contains ``widgetStates: dict[str, str]`` where each
    value is a JSON-encoded string that must be parsed again.  We find each
    known widget by name prefix and return the parsed dicts keyed by prefix.
    """
    raw = data.get("widgetStates", {})
    result: dict = {}
    for key, value in raw.items():
        for prefix in _KNOWN_WIDGETS:
            if key.startswith(prefix):
                try:
                    result[prefix] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    pass  # skip malformed widget — non-fatal
                break
    return result


def _parse_price_str(s: str | None) -> Decimal:
    """
    Parse an Ozon price string to Decimal.

    Ozon returns prices as locale-formatted strings, e.g. ``"1\xa0299\xa0₽"``.
    Strips currency symbols, non-breaking spaces (U+00A0), regular spaces, and
    normalises comma decimal separators to dots.

    Returns ``Decimal("0")`` for blank or unparseable input.
    """
    if not s:
        return Decimal("0")
    # Remove non-breaking spaces and regular spaces first
    cleaned = s.replace("\xa0", "").replace(" ", "")
    # Keep only digits, comma, and dot
    cleaned = re.sub(r"[^\d.,]", "", cleaned)
    # Normalise decimal separator
    cleaned = cleaned.replace(",", ".")
    if not cleaned:
        return Decimal("0")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal("0")


def _parse_item_id(raw: str | None) -> str:
    """
    Validate that ``item_id`` is a non-empty numeric string.

    Returns the stripped string if valid.
    Raises ``ValueError("NO_ITEM_ID")`` if empty.
    Raises ``ScraperError("PARSE_ERROR")`` if non-numeric.
    """
    if not raw or not raw.strip():
        raise ValueError("NO_ITEM_ID")
    stripped = raw.strip()
    if not stripped.isdigit():
        raise ScraperError("PARSE_ERROR", f"item_id is not numeric: {stripped!r}")
    return stripped


async def _download_image_async(url: str, proxy: str | None) -> bytes:
    """
    Download an image from the Ozon CDN.

    Re-validates the URL against ``_OZ_IMAGE_CDN_RE`` before making any HTTP
    request as an internal SSRF guard — callers must not rely solely on
    pre-validation done outside this function.

    Raises ``ValueError`` if URL fails the allowlist check.
    """
    if not _OZ_IMAGE_CDN_RE.match(url):
        raise ValueError(f"Image URL failed SSRF allowlist: {url}")
    async with httpx.AsyncClient(proxy=proxy, timeout=30.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


# ---------------------------------------------------------------------------
# OzonScraper
# ---------------------------------------------------------------------------

class OzonScraper(BaseScraper):
    """Scraper for Ozon marketplace using the composer API (widgetStates)."""

    platform = "Ozon"
    rate_limit = 0.5  # req/sec — 1 request per 2 seconds
    _impersonate = "chrome131"  # curl_cffi TLS impersonation to bypass Akamai Bot Manager

    COMPOSER_API = "https://www.ozon.ru/api/composer-api.bx/page/json/v2"
    PRODUCT_URL = "/product/{item_id}/"
    REVIEWS_URL = "/product/{item_id}/reviews/"

    # Required headers to bypass Ozon's User-Agent and app-version filtering
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "x-o3-app-name": "pdp",
        "x-o3-app-version": "2.68.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9",
    }

    def __init__(self, proxy_rotator: Optional[ProxyRotator] = None) -> None:
        from app.core.proxy import get_proxy_rotator
        super().__init__(proxy_rotator or get_proxy_rotator())

    # ── Public methods ─────────────────────────────────────────────────────

    async def collect_content(self, item_id: str) -> ContentData:
        """Collect product content (title, description, composition, image)."""
        widgets = await self._fetch_product_page(item_id)

        # Title from heading widget
        heading = widgets.get("webProductHeading-", {})
        title = sanitize(heading.get("title", ""), 500)
        if not title:
            raise ScraperError("PARSE_ERROR", "empty title")

        # Description — prefer plain text, fall back to rich HTML content
        sku_widget = widgets.get("webDetailSKU-", {})
        desc_plain = sku_widget.get("description", "")
        desc_rich = sku_widget.get("richContent", "")
        description = sanitize(desc_plain or desc_rich, 5000)

        # Composition — search characteristics list for "Состав" entry
        composition: Optional[str] = None
        for char in sku_widget.get("characteristics", []):
            if "состав" in char.get("name", "").lower():
                values = char.get("values", [])
                composition = sanitize(", ".join(str(v) for v in values), 2000) or None
                break

        # Image URL — first image from gallery widget, validated against CDN allowlist
        gallery = widgets.get("webGallery-", {})
        images = gallery.get("images", [])
        image_url: Optional[str] = images[0].get("url") if images else None
        if image_url and not _OZ_IMAGE_CDN_RE.match(image_url):
            logger.warning("Ozon image URL failed allowlist: %s — skipping image", image_url)
            image_url = None

        return ContentData(
            title=title,
            description=description,
            composition=composition,
            image_url=image_url,
        )

    async def collect_price(self, item_id: str) -> PriceData:
        """Collect current price, original price, discount, and promo label."""
        widgets = await self._fetch_product_page(item_id)

        price_widget = widgets.get("webPrice-", {})
        # Some response versions nest price data under a "price" key
        price_data = price_widget.get("price", price_widget)

        # Ozon uses "cardPrice" for club/promo price, falling back to "price"
        raw_price: str = price_data.get("cardPrice") or price_data.get("price", "")
        raw_original: str = price_data.get("originalPrice") or raw_price
        promo_label: Optional[str] = price_data.get("promoText") or None

        price = _parse_price_str(raw_price)
        original = _parse_price_str(raw_original)

        if original == 0:
            # Widget absent or product unlisted — return zeros, not an error
            return PriceData(
                price=Decimal("0"),
                original_price=Decimal("0"),
                discount_pct=Decimal("0"),
                promo_label=None,
            )

        if price == 0:
            # Club price widget absent — no discount applies
            price = original

        if original > price:
            discount = (original - price) / original * 100
        else:
            discount = Decimal("0")

        return PriceData(
            price=price.quantize(Decimal("0.01")),
            original_price=original.quantize(Decimal("0.01")),
            discount_pct=discount.quantize(Decimal("0.01")),
            promo_label=promo_label,
        )

    async def collect_stock(self, item_id: str) -> StockData:
        """Collect stock availability and quantity from the add-to-cart widget."""
        widgets = await self._fetch_product_page(item_id)

        cart_widget = widgets.get("webAddToCart-", {})

        # availability: 1 = available, 0 = out of stock
        availability = cart_widget.get("availability", 0)
        try:
            count = int(cart_widget.get("count", 0))
        except (ValueError, TypeError):
            count = 0

        # Both conditions must hold: Ozon may report availability=1 with count=0
        # (e.g., item available to order but no warehouse stock)
        in_stock = availability == 1 and count > 0
        total_qty = count if in_stock else 0

        return StockData(in_stock=in_stock, total_qty=total_qty)

    async def collect_reviews(self, item_id: str, take: int = 50) -> list[ReviewData]:
        """Collect the most recent product reviews."""
        params = {"url": f"/product/{item_id}/reviews/", "page": 1}

        async def _fetch():
            resp = await self._get(
                self.COMPOSER_API,
                params=params,
                headers=self._HEADERS,
            )
            resp.raise_for_status()
            return resp.json()

        try:
            data = await self.with_retry(_fetch)
        except ScraperError:
            raise

        widgets = _parse_widget_states(data)
        review_widget = widgets.get("webReviewList-", {})
        feedbacks = review_widget.get("reviews", [])

        result: list[ReviewData] = []
        for fb in feedbacks[:take]:
            ext_id = fb.get("id")
            if not ext_id:
                continue  # skip reviews without an ID — can't deduplicate

            text = sanitize(fb.get("text", ""), 5000)

            try:
                rating = max(1, min(5, int(fb.get("score", 5))))
            except (ValueError, TypeError):
                rating = 5

            # Accept either "publishedAt" or "createdAt", take first 10 chars (date part)
            date_str = (fb.get("publishedAt") or fb.get("createdAt") or "")[:10]
            try:
                review_date = date.fromisoformat(date_str)
            except ValueError:
                continue  # skip reviews with unparseable date

            result.append(ReviewData(
                external_review_id=str(ext_id),
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

    async def _fetch_product_page(self, item_id: str) -> dict:
        """
        Fetch and parse the composer API response for a product page.

        Returns a dict of parsed widget states keyed by widget name prefix.

        Raises:
            ScraperError("NOT_FOUND")       — product doesn't exist or was delisted
            ScraperError("RATE_LIMITED")    — 429/403 after retries exhausted
            ScraperError("API_UNAVAILABLE") — 503 or network error
        """
        params = {"url": f"/product/{item_id}/"}

        async def _fetch():
            resp = await self._get(
                self.COMPOSER_API,
                params=params,
                headers=self._HEADERS,
            )
            # Treat 429 and 403 as rate-limited — raise so with_retry() handles backoff
            if resp.status_code in (429, 403):
                resp.raise_for_status()
            # 503 or other 5xx — treat as unavailable
            if resp.status_code == 503 or resp.status_code >= 500:
                raise ScraperError(
                    "API_UNAVAILABLE",
                    f"Ozon composer API returned HTTP {resp.status_code}",
                )
            if resp.status_code != 200:
                raise ScraperError(
                    "API_UNAVAILABLE",
                    f"Unexpected HTTP status {resp.status_code} for item_id={item_id}",
                )
            return resp.json()

        try:
            data = await self.with_retry(_fetch)
        except ScraperError:
            raise
        except Exception as exc:
            raise ScraperError("API_UNAVAILABLE", str(exc)) from exc

        widgets = _parse_widget_states(data)

        if "webProductHeading-" not in widgets:
            # Product doesn't exist or was delisted — heading widget is always present
            # for live products; its absence is a reliable NOT_FOUND signal.
            raise ScraperError(
                "NOT_FOUND",
                f"webProductHeading widget absent for item_id={item_id}",
            )

        return widgets
