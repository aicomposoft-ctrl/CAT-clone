"""
Lenta scraper.

Migrated 2026-05-04 from dead /api/v1/ to /api-gateway/v1/ flow.

Session flow (DevTools-confirmed, 2026-05-04):
  1. POST https://lenta.com/api/rest/sessionGet   → qauth cookie / session token
  2. GET  /api-gateway/v1/region/user             → region context
  3. GET  /api-gateway/v1/delivery/mode           → delivery mode
  4. GET  /api-gateway/v1/catalog/items/{id}      → product data (candidate)

Without step 1 the gateway returns 403 (Qrator qauth challenge).
On 403/401 → ANTIBOT_BLOCK so ScraperRouter escalates to L2 Playwright.

All candidate endpoint URLs and HTTP status codes are logged at INFO level so
we can confirm which path works after the first live run.

Image CDN: cdn.lentochka.lenta.com (primary) + lenta.com/images/ (legacy).
Price values: integer kopeks ÷ 100 = Decimal RUB.
"""

from __future__ import annotations

import asyncio
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
from app.core.proxy import ProxyRotator
from app.core.sanitize import sanitize
from app.scrapers.samocat import (
    _kopeks_to_decimal,  # noqa: F401 — re-exported for task imports
    _parse_product_id,   # noqa: F401 — re-exported; lenta_reviews_task imports this
    _parse_rating,
    _parse_review_date,
    _safe_qty,
)

logger = logging.getLogger(__name__)

# Lenta image CDN allowlist — SSRF guard.
# Covers both the new CDN (cdn.lentochka.lenta.com) and legacy (lenta.com/images/).
# SVG is intentionally excluded (can contain inline JS → XSS risk).
_LT_IMAGE_CDN_RE = re.compile(
    r"^https://(cdn\.lentochka\.lenta\.com|lenta\.com/images)"
    r"/[A-Za-z0-9/_\-\.%=&]*\.(jpg|jpeg|png|webp)(\?[A-Za-z0-9=&%_\-]*)?$"
)

_SESSION_URL = "https://lenta.com/api/rest/sessionGet"
_GATEWAY_BASE = "https://lenta.com/api-gateway/v1"


async def _download_image_async(url: str, proxy: str | None) -> bytes:
    """
    Download an image from the Lenta CDN.

    Re-validates the URL against _LT_IMAGE_CDN_RE before any HTTP request.
    Raises ValueError if the URL fails the allowlist check.
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
    """Scraper for Lenta using /api-gateway/v1/ with session initialization."""

    platform = "Lenta"
    rate_limit = 1.0  # req/sec — conservative for traditional retailer

    _HEADERS = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Origin": "https://lenta.com",
        "Referer": "https://lenta.com/",
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
            ScraperError("API_UNAVAILABLE") — gateway unreachable after retries
            ScraperError("ANTIBOT_BLOCK")   — 401/403 from Qrator qauth
            ScraperError("PARSE_ERROR")     — empty title
        """
        data = await self._fetch_product(product_id)

        title = sanitize(
            data.get("name") or data.get("title") or data.get("itemName") or "", 500
        )
        if not title:
            raise ScraperError("PARSE_ERROR", f"empty title for product_id={product_id}")

        description = sanitize(
            data.get("description") or data.get("shortDescription") or "", 5000
        )

        # Composition: dedicated field or attributes list
        composition: Optional[str] = None
        raw_comp = (
            data.get("composition")
            or data.get("compound")
            or data.get("ingredients")
        )
        if raw_comp:
            composition = sanitize(str(raw_comp), 2000) or None
        else:
            for attr in (
                data.get("attributes") or
                data.get("properties") or
                data.get("characteristics") or []
            ):
                attr_name = (attr.get("name") or attr.get("key") or "").lower()
                if "состав" in attr_name or "ингредиент" in attr_name:
                    composition = sanitize(str(attr.get("value") or ""), 2000) or None
                    break

        # Image: validate against CDN allowlist (SSRF guard)
        image_url: Optional[str] = None
        images = data.get("images") or data.get("photos") or []
        if isinstance(images, list) and images:
            first = images[0]
            candidate = first.get("url") or first.get("src") if isinstance(first, dict) else str(first)
        elif isinstance(images, str):
            candidate = images
        else:
            candidate = (
                data.get("imageUrl") or data.get("image") or data.get("previewImage")
            )

        if candidate and _LT_IMAGE_CDN_RE.match(str(candidate)):
            image_url = str(candidate)
        elif candidate:
            logger.warning(
                "Lenta image URL failed SSRF allowlist for product_id=%s — skipping. "
                "CDN domain: %s",
                product_id,
                str(candidate).split("/")[2] if "/" in str(candidate) else "unknown",
            )

        logger.info(
            "Lenta collect_content product_id=%s title=%r image_url=%s composition_len=%s",
            product_id,
            title[:60],
            "present" if image_url else "absent",
            len(composition) if composition else 0,
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

        Tries both kopek-format (integer ÷ 100) and ruble-format (decimal string).

        Raises:
            ScraperError("NOT_FOUND")    — HTTP 404
            ScraperError("PARSE_ERROR")  — price fields missing or non-numeric
        """
        data = await self._fetch_product(product_id)

        # Try kopek fields first (legacy format), then ruble fields (gateway format)
        raw_price = (
            data.get("price")
            or data.get("currentPrice")
            or data.get("salePrice")
            or data.get("regularPrice")
        )
        raw_original = (
            data.get("originalPrice")
            or data.get("regularPrice")
            or data.get("basePrice")
            or raw_price
        )

        if raw_price is None:
            raise ScraperError("PARSE_ERROR", f"price field missing for product_id={product_id}")

        try:
            # Detect kopek format: integer > 1000 and no decimal point
            price_str = str(raw_price)
            if "." not in price_str and int(price_str) > 1000:
                price = Decimal(price_str) / 100
                original_price = Decimal(str(raw_original)) / 100
            else:
                price = Decimal(price_str).quantize(Decimal("0.01"))
                original_price = Decimal(str(raw_original)).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ScraperError("PARSE_ERROR", f"invalid price value: {raw_price!r}") from exc

        if original_price > Decimal("0") and original_price >= price:
            discount_pct = (
                (original_price - price) / original_price * 100
            ).quantize(Decimal("0.01"))
        else:
            discount_pct = Decimal("0.00")
            original_price = price

        promo_label: Optional[str] = (
            sanitize(
                data.get("promoLabel") or data.get("badge") or data.get("promo") or "",
                200,
            ) or None
        )

        logger.info(
            "Lenta collect_price product_id=%s price=%s original=%s discount=%s%%",
            product_id, price, original_price, discount_pct,
        )

        return PriceData(
            price=price.quantize(Decimal("0.01")),
            original_price=original_price.quantize(Decimal("0.01")),
            discount_pct=discount_pct.quantize(Decimal("0.01")),
            promo_label=promo_label,
        )

    async def collect_stock(self, product_id: str) -> StockData:
        """
        Collect stock availability.

        Raises:
            ScraperError("NOT_FOUND") — HTTP 404
        """
        data = await self._fetch_product(product_id)

        in_stock = bool(
            data.get("inStock")
            or data.get("available")
            or data.get("isAvailable")
            or data.get("is_available")
        )

        total_qty = _safe_qty(
            data.get("availableQuantity")
            or data.get("quantity")
            or data.get("stock")
            or 0
        )

        logger.info(
            "Lenta collect_stock product_id=%s in_stock=%s qty=%s",
            product_id, in_stock, total_qty,
        )

        return StockData(in_stock=in_stock, total_qty=total_qty)

    async def collect_reviews(
        self, product_id: str, take: int = 50
    ) -> list[ReviewData]:
        """
        Collect the most recent product reviews via /api-gateway/v1/.

        Returns an empty list on 404 — product may exist without a reviews endpoint.

        Raises:
            ScraperError("API_UNAVAILABLE") — 5xx or network error after retries
            ScraperError("RATE_LIMITED")    — 429 after retries exhausted
        """
        session_headers = await self._init_session()

        candidate_urls = [
            f"{_GATEWAY_BASE}/catalog/items/{product_id}/reviews",
            f"{_GATEWAY_BASE}/catalog/product/{product_id}/reviews",
            f"{_GATEWAY_BASE}/reviews?itemId={product_id}&limit={take}",
        ]

        for url in candidate_urls:
            params = {"page": 1, "limit": take}
            try:
                async def _fetch(u=url, p=params):
                    resp = await self._get(u, params=p, headers=session_headers)
                    logger.info("Lenta reviews endpoint=%s status=%s", u, resp.status_code)
                    if resp.status_code == 404:
                        return None
                    if resp.status_code in (401, 403):
                        raise ScraperError(
                            "ANTIBOT_BLOCK",
                            f"Lenta reviews {resp.status_code} for {u}",
                        )
                    resp.raise_for_status()
                    return resp.json()

                data = await self.with_retry(_fetch)
            except ScraperError as exc:
                if exc.code == "ANTIBOT_BLOCK":
                    raise
                logger.debug("Lenta reviews %s → %s, trying next", url, exc.code)
                continue

            if data is None:
                return []

            raw_reviews = (
                data.get("reviews") or
                data.get("items") or
                data.get("data") or []
            )
            result: list[ReviewData] = []
            for fb in raw_reviews:
                external_id = str(
                    fb.get("id") or fb.get("reviewId") or fb.get("uuid") or ""
                )[:200].strip()
                if not external_id:
                    continue
                text = sanitize(
                    fb.get("text") or fb.get("comment") or fb.get("body") or "", 5000
                )
                rating = _parse_rating(fb.get("rating") or fb.get("grade") or 5)
                review_date = _parse_review_date(
                    fb.get("createdAt") or fb.get("dateCreated") or fb.get("date")
                )
                result.append(ReviewData(
                    external_review_id=external_id,
                    review_text=text,
                    rating=rating,
                    review_date=review_date,
                ))
            return result

        return []

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

    async def _init_session(self) -> dict:
        """
        Initialize a Lenta session via POST /api/rest/sessionGet.

        Returns merged headers dict (base headers + session token if obtained).
        Falls back to base headers only if session init fails — the caller will
        then likely get a 403 and escalate to L2 Playwright.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    _SESSION_URL,
                    json={},
                    headers=self._HEADERS,
                )
                logger.info(
                    "Lenta session init endpoint=%s status=%s",
                    _SESSION_URL,
                    resp.status_code,
                )
                if resp.status_code == 200:
                    try:
                        body = resp.json()
                    except Exception:
                        body = {}
                    # Extract session token from various possible locations
                    _data_obj = body.get("data")
                    token = (
                        body.get("token")
                        or body.get("sessionToken")
                        or body.get("accessToken")
                        or (_data_obj.get("token") if isinstance(_data_obj, dict) else None)
                    )
                    # Also capture qauth cookie from response
                    qauth = resp.cookies.get("qauth") or resp.cookies.get("QAUTH")

                    headers = dict(self._HEADERS)
                    if token:
                        headers["X-Session-Token"] = str(token)
                        logger.info("Lenta session token obtained (%d chars)", len(str(token)))
                    if qauth:
                        headers["Cookie"] = f"qauth={qauth}"
                        logger.info("Lenta qauth cookie obtained")
                    return headers
        except Exception as exc:
            logger.warning("Lenta session init failed: %s — proceeding without session", exc)

        return dict(self._HEADERS)

    async def _fetch_product(self, product_id: str) -> dict:
        """
        Fetch product data from Lenta /api-gateway/v1/.

        Tries multiple candidate endpoints in order, logging each attempt.
        Falls back to ANTIBOT_BLOCK on persistent 403 so ScraperRouter
        escalates to L2 Playwright which carries a real browser session.

        Candidate endpoints (order: most likely first based on DevTools patterns):
          GET  /api-gateway/v1/catalog/items/{id}
          GET  /api-gateway/v1/catalog/product/{id}
          POST /api-gateway/v1/catalog/items  (body: {"ids": [id]})
          GET  /api-gateway/v1/products/{id}
          GET  /api-gateway/v1/sku/{id}

        Raises:
            ScraperError("NOT_FOUND")       — 404 confirmed
            ScraperError("ANTIBOT_BLOCK")   — 401/403 on all candidates
            ScraperError("API_UNAVAILABLE") — network/5xx on all candidates
        """
        session_headers = await self._init_session()

        # (method, url, body_or_None)
        candidates: list[tuple[str, str, dict | None]] = [
            ("GET",  f"{_GATEWAY_BASE}/catalog/items/{product_id}",   None),
            ("GET",  f"{_GATEWAY_BASE}/catalog/product/{product_id}", None),
            ("POST", f"{_GATEWAY_BASE}/catalog/items",                {"ids": [product_id]}),
            ("GET",  f"{_GATEWAY_BASE}/products/{product_id}",        None),
            ("GET",  f"{_GATEWAY_BASE}/sku/{product_id}",             None),
        ]

        last_status: int = 0
        antibot = False

        for method, url, body in candidates:
            try:
                async def _fetch(m=method, u=url, b=body):
                    if m == "POST":
                        resp = await self._post(u, json=b, headers=session_headers)
                    else:
                        resp = await self._get(u, headers=session_headers)
                    logger.info(
                        "Lenta _fetch_product method=%s endpoint=%s status=%s",
                        m, u, resp.status_code,
                    )
                    return resp

                resp = await self.with_retry(_fetch)
            except ScraperError as exc:
                logger.debug("Lenta %s %s → ScraperError %s", method, url, exc.code)
                continue
            except Exception as exc:
                logger.debug("Lenta %s %s → %s", method, url, exc)
                continue

            last_status = resp.status_code

            if resp.status_code == 404:
                raise ScraperError("NOT_FOUND", f"product_id={product_id} not found at {url}")

            if resp.status_code in (401, 403):
                antibot = True
                logger.warning(
                    "Lenta %s → %s (Qrator qauth block) — trying next candidate",
                    url, resp.status_code,
                )
                continue

            if resp.status_code == 200:
                try:
                    data = resp.json()
                except Exception as exc:
                    logger.warning("Lenta %s returned non-JSON: %s", url, exc)
                    continue

                # POST /catalog/items returns a list — unwrap first element
                if isinstance(data, list):
                    if not data:
                        raise ScraperError("NOT_FOUND", f"product_id={product_id} empty list")
                    data = data[0]
                elif isinstance(data, dict):
                    # Some endpoints wrap result in .data or .item
                    data = data.get("item") or data.get("data") or data.get("product") or data

                if not isinstance(data, dict) or not data:
                    logger.warning("Lenta %s returned unexpected shape", url)
                    continue

                logger.info(
                    "Lenta _fetch_product success: method=%s url=%s keys=%s",
                    method, url, list(data.keys())[:10],
                )
                return data

        # All candidates exhausted
        if antibot:
            raise ScraperError(
                "ANTIBOT_BLOCK",
                f"Lenta 401/403 on all candidates for product_id={product_id}. "
                "ScraperRouter will escalate to L2 Playwright.",
            )
        raise ScraperError(
            "API_UNAVAILABLE",
            f"All Lenta /api-gateway/v1/ endpoints failed for product_id={product_id}. "
            f"Last HTTP status: {last_status}. Check logs for per-endpoint details.",
        )

    async def _post(self, url: str, json: dict | None = None, headers: dict | None = None) -> httpx.Response:
        """Minimal async POST via httpx — used for /catalog/items batch endpoint."""
        proxy = self._proxy.next() if self._proxy else None
        async with httpx.AsyncClient(proxy=proxy, timeout=20.0) as client:
            return await client.post(url, json=json, headers=headers or self._HEADERS)
