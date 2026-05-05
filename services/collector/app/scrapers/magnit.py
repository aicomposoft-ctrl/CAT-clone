"""
Magnit (magnit.ru) scraper.

Uses the public Magnit catalog REST API (/api/v1/product/{id}) for product data.
No authentication required — JSON API accessible via standard browser headers.
Rate limit: 1.5 req/sec (conservative — large traditional retailer).
Image URLs validated against magnitimages.ru / magnit.ru allowlist before fetching (SSRF guard).
Price values are returned as decimal strings in RUB.

Product ID is the numeric identifier visible in the product page URL or catalog API.
To find a product's ID: open magnit.ru, navigate to the product, check the URL or
Network tab for the numeric product id.
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

# Magnit image CDN allowlist — SSRF guard.
# Domain-anchored only: any path/query params are allowed once the origin is trusted.
# We do NOT require a specific file extension — Magnit CDN serves images without
# extension or with query params (e.g. ?w=800) appended after the extension.
_MAGNIT_IMAGE_CDN_RE = re.compile(
    r"^https://([a-z0-9\-]+\.)?(magnit\.ru|magnitimages\.ru)/"
)


def _parse_price(raw) -> Decimal:
    """Parse a price value (string, int, or float) into Decimal RUB."""
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
    Download an image from the Magnit CDN.

    Re-validates the URL against _MAGNIT_IMAGE_CDN_RE before any HTTP request.
    Raises ValueError if the URL fails the allowlist check.
    """
    if not _MAGNIT_IMAGE_CDN_RE.match(url):
        raise ValueError("Image URL failed SSRF allowlist")
    async with httpx.AsyncClient(proxy=proxy, timeout=30.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


# ---------------------------------------------------------------------------
# MagnitScraper
# ---------------------------------------------------------------------------


class MagnitScraper(BaseScraper):
    """Scraper for Magnit (magnit.ru) using the public catalog REST API."""

    platform = "Магнит"
    rate_limit = 1.5  # req/sec — conservative for large traditional retailer

    _BASE_API = "https://magnit.ru/api/v1"

    # Standard browser headers — Magnit uses basic anti-scraping, not Qrator/Akamai.
    _HEADERS = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Referer": "https://magnit.ru/",
        "Origin": "https://magnit.ru",
    }

    def __init__(self, proxy_rotator: Optional[ProxyRotator] = None) -> None:
        from app.core.proxy import get_proxy_rotator
        super().__init__(proxy_rotator or get_proxy_rotator())

    # ── Public methods ─────────────────────────────────────────────────────

    async def collect_content(self, product_id: str) -> ContentData:
        """
        Collect product content: title, description, composition, and image URL.

        Raises:
            ScraperError("NOT_FOUND")       — HTTP 404
            ScraperError("API_UNAVAILABLE") — 5xx or network error after retries
            ScraperError("RATE_LIMITED")    — 429 after retries exhausted
        """
        data = await self._fetch_product(product_id)

        title = sanitize(data.get("name") or data.get("title") or "", 500)
        if not title:
            raise ScraperError("PARSE_ERROR", f"empty title for product_id={product_id}")

        description = sanitize(data.get("description") or "", 5000)

        # Composition: check dedicated field or attributes list
        composition: Optional[str] = None
        raw_comp = data.get("composition") or data.get("compound")
        if raw_comp:
            composition = sanitize(str(raw_comp), 2000) or None
        else:
            for attr in data.get("attributes") or data.get("properties") or []:
                attr_name = (attr.get("name") or attr.get("key") or "").lower()
                if "состав" in attr_name:
                    composition = sanitize(str(attr.get("value") or ""), 2000) or None
                    break

        # Image: validate against CDN allowlist (SSRF guard)
        image_url: Optional[str] = None
        images = data.get("images") or data.get("photos") or []
        if isinstance(images, list) and images:
            first = images[0]
            candidate = first.get("url") if isinstance(first, dict) else str(first)
        elif isinstance(images, str):
            candidate = images
        else:
            candidate = data.get("image") or data.get("imageUrl")

        if candidate and _MAGNIT_IMAGE_CDN_RE.match(str(candidate)):
            image_url = str(candidate)
        elif candidate:
            logger.warning(
                "Magnit image URL failed SSRF allowlist for product_id=%s — skipping",
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

        Raises:
            ScraperError("NOT_FOUND")    — HTTP 404
            ScraperError("PARSE_ERROR")  — price fields missing or non-numeric
        """
        data = await self._fetch_product(product_id)

        # Magnit returns prices as "price" (current) and "oldPrice" / "regularPrice"
        raw_price = (data.get("price") or data.get("currentPrice") or
                     data.get("priceValue"))
        raw_original = (data.get("oldPrice") or data.get("regularPrice") or
                        data.get("originalPrice") or raw_price)

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
            sanitize(data.get("promo") or data.get("badge") or "", 255) or None
        )

        return PriceData(
            price=price,
            original_price=original_price,
            discount_pct=discount_pct,
            promo_label=promo_label,
        )

    async def collect_stock(self, product_id: str) -> StockData:
        """
        Collect stock availability.

        Magnit doesn't expose warehouse quantity via the catalog API —
        only whether the product is available.
        """
        data = await self._fetch_product(product_id)

        in_stock = bool(
            data.get("inStock") or
            data.get("available") or
            data.get("is_available") or
            (data.get("price") is not None)
        )

        return StockData(in_stock=in_stock, total_qty=0)

    async def collect_reviews(self, product_id: str, take: int = 50) -> list[ReviewData]:
        """
        Collect public product reviews from Magnit.

        Endpoint confirmed via DevTools (2026-05-04):
        GET /webgate/v1/listing/object-reviews
            ?service=dostavka&objectType=product&objectId={id}&limit=10&page=N

        Pagination: API caps at ~10 items per page regardless of limit param.
        Uses page (0-based) not offset.

        Raises:
            ScraperError("API_UNAVAILABLE") — 5xx or network error after retries
            ScraperError("RATE_LIMITED")    — 429 after retries exhausted
        """
        url = "https://magnit.ru/webgate/v1/listing/object-reviews"
        collected: list[ReviewData] = []
        page = 0
        page_size = 10  # API caps here regardless of limit param

        while len(collected) < take:
            params = {
                "service": "dostavka",
                "objectType": "product",
                "objectId": product_id,
                "limit": page_size,
                "page": page,
            }

            async def _fetch(p=params):
                resp = await self._get(url, params=p, headers=self._HEADERS)
                if resp.status_code in (404, 410):
                    return None
                resp.raise_for_status()
                return resp.json()

            data = await self.with_retry(_fetch)

            if data is None:
                break

            raw_items: list = data.get("reviews") or []
            if not raw_items:
                break

            for item in raw_items:
                ext_id = item.get("reviewId") or item.get("id") or item.get("uuid")
                if not ext_id:
                    continue

                raw_rating = item.get("rating") or item.get("grade") or item.get("score") or 5
                rating = max(1, min(5, int(raw_rating)))

                collected.append(ReviewData(
                    external_review_id=str(ext_id),
                    review_text=sanitize(
                        item.get("comment") or item.get("text") or item.get("body") or "", 5000
                    ),
                    rating=rating,
                    review_date=_parse_review_date(
                        item.get("dateCreated") or item.get("createdAt") or item.get("date")
                    ),
                ))

            if len(raw_items) < page_size:
                break  # last page
            page += 1

        logger.info(
            "MagnitScraper: collected %d reviews for product_id=%s", len(collected), product_id
        )
        return collected[:take]

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

    async def _fetch_product(self, product_id: str) -> dict:
        """
        Fetch product data from Magnit catalog API.

        Tries several endpoint patterns in order — Magnit has redesigned their API
        multiple times and the correct path depends on the product type/category.

        Known patterns (probed 2026-04-20):
          /api/v1/product/{id}/          → 301→404 (endpoint doesn't exist)
          /api/v1/catalog/product/{id}/  → TBD
          /api/v1/products/{id}/         → TBD
          /api/v2/catalog/product/{id}/  → TBD

        TODO: Run DevTools on magnit.ru product page to find the real API call.
              The correct path will appear as a JSON XHR/Fetch with the product data.

        Raises:
            ScraperError("NOT_FOUND")       — product confirmed not found
            ScraperError("API_UNAVAILABLE") — all endpoints unreachable
            ScraperError("RATE_LIMITED")    — HTTP 429
        """
        if not product_id or not str(product_id).strip().isdigit():
            raise ScraperError("PARSE_ERROR", f"product_id is not numeric: {product_id!r}")

        # Candidates in order of probability (update based on DevTools findings)
        candidate_urls = [
            f"https://magnit.ru/api/v1/catalog/product/{product_id}/",
            f"https://magnit.ru/api/v2/catalog/product/{product_id}/",
            f"https://magnit.ru/api/v1/products/{product_id}/",
            f"https://magnit.ru/api/v1/product/detail/{product_id}/",
        ]

        last_exc: ScraperError | None = None
        for url in candidate_urls:
            try:
                async def _fetch(u=url):
                    resp = await self._get(u, headers=self._HEADERS)
                    if resp.status_code == 404:
                        raise ScraperError("NOT_FOUND", f"404 from {u}")
                    if resp.status_code in (301, 302, 303):
                        # Follow only if Location points to a different path
                        raise ScraperError("API_UNAVAILABLE", f"{resp.status_code} redirect from {u} — endpoint may not exist")
                    resp.raise_for_status()
                    return resp.json()

                return await self.with_retry(_fetch)
            except ScraperError as exc:
                if exc.code == "RATE_LIMITED":
                    raise
                last_exc = exc
                logger.debug("MagnitScraper: %s → %s — trying next", url, exc.code)
                continue

        # HTML fallback: Magnit product pages include Product JSON-LD with
        # name/description/image/offers; this keeps L1 alive when API paths drift.
        try:
            page_url = (
                f"https://magnit.ru/product/{product_id}"
                "?shopCode=992301&shopType=6"
            )
            resp = await self._get(page_url, headers=self._HEADERS)
            resp.raise_for_status()
            product = _extract_product_from_ldjson(resp.text)
            if product is not None:
                return product
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "MagnitScraper HTML fallback failed for product_id=%s: %s",
                product_id,
                exc,
            )

        raise ScraperError(
            "API_UNAVAILABLE",
            f"All Magnit API endpoints failed for product_id={product_id}. "
            f"Run DevTools on magnit.ru to find the real API path. Last: {last_exc}",
        ) from last_exc


def _extract_product_from_ldjson(html: str) -> Optional[dict]:
    """Extract product fields from schema.org Product JSON-LD + Nuxt SSR payload."""
    blocks = re.findall(
        r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for block in blocks:
        try:
            payload = json.loads(block.strip())
        except Exception:
            continue

        obj = payload
        if isinstance(payload, list):
            obj = next(
                (
                    x
                    for x in payload
                    if isinstance(x, dict)
                    and str(x.get("@type", "")).lower() == "product"
                ),
                None,
            )
        if not isinstance(obj, dict):
            continue
        if str(obj.get("@type", "")).lower() != "product":
            continue

        offers = obj.get("offers")
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        offers = offers if isinstance(offers, dict) else {}

        image = obj.get("image")
        if isinstance(image, list):
            image = image[0] if image else None

        price = offers.get("price")
        original_price = offers.get("highPrice") or offers.get("price")
        return {
            "name": obj.get("name"),
            "description": obj.get("description"),
            "composition": _extract_composition_from_nuxt(html),
            "images": [image] if image else [],
            "price": price,
            "currentPrice": price,
            "oldPrice": original_price,
        }
    return None


def _extract_composition_from_nuxt(html: str) -> Optional[str]:
    """
    Extract product composition from the Nuxt SSR inline payload.

    Magnit renders composition in a Nuxt serialized state as:
      "Состав",[],"stringType","<composition text>"
    The text may contain escaped \\n characters (soft line breaks from label printing).
    """
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, flags=re.IGNORECASE | re.DOTALL)
    big = max(scripts, key=len) if scripts else ""
    m = re.search(
        r'"Состав"\s*,\s*\[\]\s*,\s*"stringType"\s*,\s*"(.*?)"',
        big,
        flags=re.DOTALL,
    )
    if not m:
        return None
    raw = m.group(1)
    # Join hyphenated line breaks (label printing splits words: "нату-\nральный" → "натуральный")
    composition = re.sub(r"-\\+n", "", raw)
    # Remove remaining soft line breaks
    composition = re.sub(r"\\+n", " ", composition).strip()
    return composition or None
