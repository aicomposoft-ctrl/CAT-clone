"""
Wildberries scraper.

Uses WB's card API (card.wb.ru) for structured product data.
Falls back gracefully when product is not found or API is unavailable.

Rate limit: 1.0 req/sec.
Image URLs validated against CDN allowlist before fetching (SSRF guard).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

import httpx

import asyncio

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

# WB image CDN allowlist pattern — deterministic URL, prevents SSRF
_WB_IMAGE_CDN_RE = re.compile(
    r"^https://basket-\d{2}\.wbbasket\.ru/vol\d+/part\d+/\d+/images/big/\d+\.jpg$"
)

# WB basket selection: vol range → basket number
_BASKET_MAP: list[tuple[int, int]] = [
    (143, 1), (287, 2), (431, 3), (719, 4), (1007, 5),
    (1061, 6), (1115, 7), (1169, 8), (1313, 9), (1601, 10),
    (1655, 11), (1919, 12), (2045, 13), (2189, 14), (2405, 15),
    (2621, 16), (2837, 17), (3053, 18), (3269, 19),
]
_BASKET_DEFAULT = 20


class WildberriesScraper(BaseScraper):
    """Scraper for Wildberries marketplace."""

    platform = "Wildberries"
    rate_limit = 1.0  # req/sec

    # WB migrated *.wb.ru → *.wildberries.ru in April 2025. Try legacy first
    # (still resolves for many clients); fall back to new domain on connection failure.
    _CARD_APIS = [
        "https://card.wb.ru/cards/v2/detail",
        "https://card.wildberries.ru/cards/v2/detail",
    ]
    _REVIEWS_API_TMPLS = [
        "https://feedbacks2.wb.ru/feedbacks/v1/{nm_id}",
        "https://feedbacks2.wildberries.ru/feedbacks/v1/{nm_id}",
    ]

    def __init__(self, proxy_rotator: Optional[ProxyRotator] = None) -> None:
        from app.core.proxy import get_proxy_rotator
        super().__init__(proxy_rotator or get_proxy_rotator())

    # ── Public methods ─────────────────────────────────────────────────────

    async def collect_content(self, nm_id: str) -> ContentData:
        product = await self._fetch_product(nm_id)
        image_url = _build_image_url(nm_id)
        if not _WB_IMAGE_CDN_RE.match(image_url):
            logger.warning("WB image URL failed allowlist: %s — skipping image", image_url)
            image_url = None

        return ContentData(
            title=sanitize(product.get("name", ""), 500),
            description=sanitize(product.get("description", ""), 5000),
            composition=sanitize(product.get("composition", ""), 2000) or None,
            image_url=image_url,
        )

    async def collect_price(self, nm_id: str) -> PriceData:
        product = await self._fetch_product(nm_id)
        sizes = product.get("sizes", [])
        price_info = sizes[0].get("price", {}) if sizes else {}

        raw_product = price_info.get("product", 0) or 0
        raw_basic = price_info.get("basic", raw_product) or raw_product

        try:
            price = Decimal(str(raw_product)) / 100
            original = Decimal(str(raw_basic)) / 100
        except InvalidOperation:
            raise ScraperError("PARSE_ERROR", f"Invalid price values: {price_info}")

        if original > 0 and original >= price:
            discount = ((original - price) / original * 100).quantize(Decimal("0.01"))
        else:
            discount = Decimal("0.00")
            original = price

        return PriceData(
            price=price,
            original_price=original,
            discount_pct=discount,
            promo_label=sanitize(product.get("promoTextCard", "") or "", 255) or None,
        )

    async def collect_stock(self, nm_id: str) -> StockData:
        product = await self._fetch_product(nm_id)
        total_qty = sum(
            stock.get("qty", 0)
            for size in product.get("sizes", [])
            for stock in size.get("stocks", [])
        )
        return StockData(in_stock=total_qty > 0, total_qty=total_qty)

    async def collect_reviews(self, nm_id: str, take: int = 50) -> list[ReviewData]:
        data: dict | None = None
        last_exc: Optional[ScraperError] = None

        for tmpl in self._REVIEWS_API_TMPLS:
            url = tmpl.format(nm_id=nm_id)

            async def _fetch(u=url):
                resp = await self._get(u, params={"take": take, "skip": 0, "order": "dateDesc"})
                resp.raise_for_status()
                return resp.json()

            try:
                data = await self.with_retry(_fetch)
                break
            except ScraperError as exc:
                if exc.code == "RATE_LIMITED":
                    raise  # rate limit is global, not domain-specific
                last_exc = exc
                logger.debug("WB reviews %s → %s, trying next domain", url, exc.code)
                continue

        if data is None:
            raise ScraperError(
                "API_UNAVAILABLE",
                f"WB reviews API unreachable for nm_id={nm_id}: {last_exc}",
            ) from last_exc

        feedbacks = data.get("feedbacks") or []
        reviews: list[ReviewData] = []

        for fb in feedbacks:
            ext_id = fb.get("id")
            if not ext_id:
                continue  # skip reviews without an ID — can't deduplicate

            try:
                review_date = datetime.fromisoformat(
                    fb.get("createdDate", "2000-01-01")
                ).date()
            except (ValueError, TypeError):
                review_date = datetime(2000, 1, 1).date()

            rating = int(fb.get("productValuation") or 5)
            rating = max(1, min(5, rating))  # clamp 1-5

            reviews.append(ReviewData(
                external_review_id=str(ext_id),
                review_text=sanitize(fb.get("text", ""), 5000),
                rating=rating,
                review_date=review_date,
            ))

        return reviews

    def collect(self, sku_id: str, data_type: DataType) -> ScrapedData:
        if data_type == DataType.CONTENT:
            return asyncio.run(self.collect_content(sku_id))
        if data_type == DataType.PRICE:
            return asyncio.run(self.collect_price(sku_id))
        if data_type == DataType.STOCK:
            return asyncio.run(self.collect_stock(sku_id))
        if data_type == DataType.REVIEWS:
            return asyncio.run(self.collect_reviews(sku_id))
        raise ValueError(f"Unknown DataType: {data_type}")

    # ── Private helpers ────────────────────────────────────────────────────

    async def _fetch_product(self, nm_id: str) -> dict:
        """
        Fetch product data from WB card API, trying each domain in _CARD_APIS.

        Tries legacy wb.ru first (still resolves for most clients as of early 2025),
        then falls back to wildberries.ru if the connection fails.
        NOT_FOUND and RATE_LIMITED are raised immediately without domain fallback.
        """
        params = {"appType": "1", "curr": "rub", "dest": "-1257786", "nm": nm_id}
        last_exc: Optional[ScraperError] = None

        for api_url in self._CARD_APIS:
            async def _fetch(url=api_url):
                resp = await self._get(url, params=params)
                if resp.status_code == 404:
                    # HTTP 404 from this domain means the endpoint may have migrated.
                    # The WB card API returns 200 + empty products[] for missing products,
                    # never HTTP 404. So 404 here = endpoint gone, try next domain.
                    raise ScraperError(
                        "API_UNAVAILABLE",
                        f"HTTP 404 from {url} — endpoint may have migrated",
                    )
                resp.raise_for_status()
                return resp.json()

            try:
                data = await self.with_retry(_fetch)
            except ScraperError as exc:
                if exc.code == "RATE_LIMITED":
                    raise  # rate limit is global — no point trying other domains
                last_exc = exc
                logger.debug(
                    "WBScraper: %s → %s — trying next domain", api_url, exc.code
                )
                continue

            try:
                products = data.get("data", {}).get("products", [])
            except AttributeError as exc:
                raise ScraperError("PARSE_ERROR", f"Unexpected response structure: {exc}") from exc

            if not products:
                # Response arrived but product doesn't exist on WB — definitive.
                raise ScraperError("NOT_FOUND", f"No products found for nm_id={nm_id}")

            return products[0]

        raise ScraperError(
            "API_UNAVAILABLE",
            f"WB card API: all domains unreachable for nm_id={nm_id}. Last: {last_exc}",
        ) from last_exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _select_basket(vol: int) -> int:
    for limit, basket in _BASKET_MAP:
        if vol <= limit:
            return basket
    return _BASKET_DEFAULT


def _build_image_url(nm_id: str) -> str:
    """Construct WB CDN image URL deterministically from nm_id."""
    try:
        nm = int(nm_id)
    except ValueError:
        raise ScraperError("PARSE_ERROR", f"nm_id is not numeric: {nm_id!r}")
    vol = nm // 100000
    part = nm // 1000
    basket = _select_basket(vol)
    return f"https://basket-{basket:02d}.wbbasket.ru/vol{vol}/part{part}/{nm}/images/big/1.jpg"
