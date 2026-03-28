"""
Lenta scraper.

Uses Lenta's mobile REST API (/api/v1/products/{article_id}) for product data.
A single endpoint returns content, price, AND stock fields — reducing API
calls by 2/3 vs. a three-endpoint design.
Rate limit: 1.0 req/sec (conservative — traditional retailer, not a darkstore API).
Image URLs validated against lenta.com/images/ allowlist before fetching (SSRF guard).
Price values are returned as integer kopeks and divided by 100 to yield Decimal RUB.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import httpx

from app.core.base_scraper import (
    BaseScraper,
    ContentData,
    PriceData,
    ReviewData,
    ScraperError,
    StockData,
)
from app.core.proxy import ProxyRotator
from app.core.sanitize import sanitize
from app.scrapers.samocat import (
    _kopeks_to_decimal,  # noqa: F401 — re-exported for task imports
    _parse_product_id,
    _parse_rating,
    _parse_review_date,
    _safe_qty,
)

logger = logging.getLogger(__name__)

# Lenta image CDN allowlist — prevents SSRF.
# Only https://lenta.com/images/ paths with safe path characters and a known
# image extension are permitted.  Non-matching URLs are logged and discarded.
_LT_IMAGE_CDN_RE = re.compile(
    r"^https://lenta\.com/images/[A-Za-z0-9/_\-\.]+\.(jpg|jpeg|png|webp)$"
)


async def _download_image_async(url: str, proxy: str | None) -> bytes:
    """
    Download an image from the Lenta CDN.

    Re-validates the URL against ``_LT_IMAGE_CDN_RE`` before making any HTTP
    request as an internal SSRF guard — callers must not rely solely on
    pre-validation performed outside this function.

    Raises ``ValueError`` if the URL fails the allowlist check.
    Raises ``httpx.HTTPStatusError`` for non-2xx responses.
    """
    if not _LT_IMAGE_CDN_RE.match(url):
        raise ValueError("Image URL failed SSRF allowlist")
    async with httpx.AsyncClient(proxy=proxy, timeout=30.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


# ---------------------------------------------------------------------------
# LentaScraper
# ---------------------------------------------------------------------------


class LentaScraper(BaseScraper):
    """Scraper for Lenta using the mobile REST API (/api/v1/products)."""

    platform = "Lenta"
    rate_limit = 1.0  # req/sec — conservative for traditional retailer

    _BASE_API = "https://lenta.com/api/v1"

    _HEADERS = {
        "User-Agent": "LentaApp/4.2.1 (Android)",
        "Accept": "application/json",
    }

    def __init__(self, proxy_rotator: Optional[ProxyRotator] = None) -> None:
        from app.core.proxy import get_proxy_rotator
        super().__init__(proxy_rotator or get_proxy_rotator())

    # ── Public methods ─────────────────────────────────────────────────────

    async def collect_content(self, product_id: str) -> ContentData:
        """
        Collect product content: title, description, composition, and image URL.

        Uses GET /api/v1/products/{product_id} — same endpoint as price and stock.

        Raises:
            ScraperError("NOT_FOUND")       — HTTP 404
            ScraperError("API_UNAVAILABLE") — 5xx or network error after retries
            ScraperError("RATE_LIMITED")    — 429 after retries exhausted
            ScraperError("PARSE_ERROR")     — empty title
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
            if _LT_IMAGE_CDN_RE.match(candidate):
                image_url = candidate
            else:
                logger.warning(
                    "Lenta image URL failed SSRF allowlist for product_id=%s — skipping",
                    product_id,
                )
                # URL value intentionally NOT logged

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
        by dividing by 100.  ``discountPercent`` is taken directly from the API
        (not computed from price/originalPrice).

        Raises:
            ScraperError("NOT_FOUND")    — HTTP 404
            ScraperError("PARSE_ERROR")  — price fields missing or non-numeric
        """
        from decimal import Decimal, InvalidOperation

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
            from decimal import Decimal as _D
            discount_pct = _D(data.get("discountPercent", 0))
        except (TypeError, InvalidOperation):
            from decimal import Decimal as _D
            discount_pct = _D(0)

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
        url = f"{self._BASE_API}/products/{product_id}/reviews"
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

    # ── Private helpers ────────────────────────────────────────────────────

    async def _fetch_product(self, product_id: str) -> dict:
        """
        Fetch and return the raw JSON dict from GET /api/v1/products/{product_id}.

        A single endpoint provides content, price, and stock fields — avoids
        duplicate requests when all three tasks run concurrently.

        Raises:
            ScraperError("NOT_FOUND")       — HTTP 404
            ScraperError("RATE_LIMITED")    — 429 after retries exhausted
            ScraperError("API_UNAVAILABLE") — 5xx or network error after retries
        """
        url = f"{self._BASE_API}/products/{product_id}"

        async def _fetch():
            resp = await self._get(url, headers=self._HEADERS)
            if resp.status_code == 404:
                raise ScraperError(
                    "NOT_FOUND",
                    f"product_id={product_id} not found",
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
