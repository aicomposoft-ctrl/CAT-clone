"""
PlaywrightScraper — L2 scraper using Playwright headless Chromium.

Strategy per collect():
  1. Load page with networkidle wait (30 s timeout).
  2. Intercept all JSON XHR/fetch responses and attempt typed extraction.
  3. Fall back to CSS selector extraction using platform.selectors config.
  4. On any failure: save debug screenshot to MinIO, raise ScraperError.

Note on instantiation:
  PlaywrightScraper does NOT call super().__init__() — BaseScraper.__init__
  requires a ProxyRotator which L2 does not need (proxy is handled at the
  BrowserPool/context level).  The abstract collect_content/price/stock/reviews
  stubs raise ScraperError("API_UNAVAILABLE") with a clear message to prevent
  silent misuse from legacy callers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from urllib.parse import urlparse, quote_plus
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional
from uuid import uuid4

from app.core.base_scraper import (
    ContentData,
    DataType,
    PriceData,
    ReviewData,
    ScrapedData,
    ScraperError,
    StockData,
)
from app.core.anti_bot import AntiBotAssessment, classify_page_state, classify_parse_failure
from app.core.browser_pool import BrowserPool
from app.core.sanitize import sanitize

logger = logging.getLogger(__name__)

# Playwright page-load timeout (ms)
_LOAD_TIMEOUT_MS = 30_000
# CSS selector extraction timeout (ms)
_SELECTOR_TIMEOUT_MS = 5_000
# MinIO bucket for debug screenshots
_DEBUG_BUCKET = "cat-debug"


class PlaywrightScraper:
    """
    L2 scraper using Playwright headless Chromium.

    Args:
        platform:        Platform ORM object (needs .name attribute).
        selectors:       Dict of CSS selectors from platform config, e.g.
                         {"title": ".product-title", "price": ".price-value"}.
        browser_pool:    BrowserPool singleton from get_browser_pool().
        platform_config: Optional platform-level config from platforms.platform_config:
            geolocation:      {"latitude": 55.7558, "longitude": 37.6173}
                              Passed to Playwright context — enables location-aware sites.
            geo_init_url:     URL to navigate to BEFORE the product URL (e.g. "https://samokat.ru")
                              Establishes a geo-gated session (delivery zone, store selection).
            geo_init_wait_ms: ms to wait after geo_init_url load for JS to settle (default 2500).
    """

    scraper_level: int = 2
    rate_limit: float = 0.5  # requests per second (1 req every 2 s)

    def __init__(
        self,
        platform,
        selectors: dict,
        browser_pool: BrowserPool,
        platform_config: Optional[dict] = None,
    ) -> None:
        self._platform = platform
        self._platform_name: str = getattr(platform, "name", str(platform))
        self._selectors: dict = selectors or {}
        self._pool = browser_pool
        self._platform_config: dict = platform_config or {}
        self._attempt_kind: str = "shared_warm"

    # ── Public API ─────────────────────────────────────────────────────────

    async def collect(self, url: str, data_type: DataType) -> ScrapedData:
        """
        Collect data for the given URL.

        Args:
            url:       Full product page URL (not nm_id — use ScraperRouter with
                       sku_platform.url for L2).
            data_type: Which data to collect.

        Returns:
            ScrapedData matching data_type.

        Raises:
            ScraperError("PARSE_ERROR")    — page loaded but data not found.
            ScraperError("API_UNAVAILABLE") — page failed to load / timeout.
            ScraperError("ANTIBOT_BLOCK")  — anti-bot page detected.
        """
        return await self.collect_with_strategy(url, data_type)

    async def collect_with_strategy(
        self,
        url: str,
        data_type: DataType,
        *,
        fresh_context: bool = False,
        attempt_kind: str = "shared_warm",
    ) -> ScrapedData:
        proxy = self._build_proxy()

        # Geolocation context — required for geo-gated platforms (e.g. Samokat).
        # Permissions must be granted BEFORE navigation for the site's JS to receive them.
        geolocation = self._platform_config.get("geolocation")
        permissions = ["geolocation"] if geolocation else None

        self._attempt_kind = attempt_kind
        async with self._pool.acquire(
            proxy=proxy,
            geolocation=geolocation,
            permissions=permissions,
            persistent_profile_key=None if fresh_context else f"l2:{self._platform_name}",
            profile_variant="fresh" if fresh_context else "default",
        ) as page:
            intercepted: list[dict] = []

            # Wire up network interception BEFORE any navigation so we catch
            # both the geo-init warm-up request AND the product page XHR calls.
            async def _on_response(response) -> None:
                try:
                    ct = response.headers.get("content-type", "")
                    if 200 <= response.status < 300:
                        body = None
                        if "application/json" in ct:
                            body = await response.json()
                        else:
                            # Some marketplaces return JSON payloads with wrong
                            # content-type (e.g. text/plain). Parse best-effort.
                            text = (await response.text() or "").strip()
                            if text.startswith("{") or text.startswith("["):
                                try:
                                    body = json.loads(text)
                                except Exception:
                                    body = None
                        if body is not None:
                            intercepted.append({"url": response.url, "body": body})
                except Exception:
                    pass  # best-effort; malformed JSON is silently dropped

            page.on("response", _on_response)

            # Geo-init: navigate to the platform homepage to establish a
            # location-aware session (e.g. Samokat delivery zone) BEFORE
            # loading the product URL.  The geolocation set on the context
            # is provided to the page automatically by the browser.
            geo_init_url = self._platform_config.get("geo_init_url")
            if geo_init_url:
                try:
                    await page.goto(
                        geo_init_url, wait_until="networkidle", timeout=_LOAD_TIMEOUT_MS
                    )
                    wait_ms = int(self._platform_config.get("geo_init_wait_ms", 2500))
                    await asyncio.sleep(wait_ms / 1000)
                    # Clear intercepted data from the homepage — we only want product data
                    intercepted.clear()
                    logger.debug(
                        "PlaywrightScraper: geo-init complete for %s via %s",
                        self._platform_name,
                        geo_init_url,
                    )
                except Exception as exc:
                    # Non-fatal: log and continue — product page may still load
                    logger.warning(
                        "PlaywrightScraper: geo-init failed for %s (%s): %s — continuing",
                        self._platform_name,
                        geo_init_url,
                        exc,
                    )
            else:
                # Generic warm-up: hit platform root first to establish cookies/session.
                root = _root_url(url)
                if root:
                    try:
                        await page.goto(root, wait_until="domcontentloaded", timeout=_LOAD_TIMEOUT_MS)
                        await asyncio.sleep(1.0)
                        intercepted.clear()
                    except Exception:
                        # Non-fatal; continue to product page.
                        pass

            # Yandex search warm-up: navigate to Yandex before the product page so the
            # visit appears as organic search traffic.  Anti-bot systems check the Referer
            # header and browser history — arriving from yandex.ru is much less suspicious
            # than a direct headless request.
            #
            # Enable per platform via platform_config:
            #   {"yandex_warmup": true, "yandex_search_query": "Агуша яблоко 90г ozon"}
            #
            # If yandex_search_query is omitted, the URL domain is used as the search hint.
            _yandex_referer: Optional[str] = None
            if self._platform_config.get("yandex_warmup"):
                _search_q = self._platform_config.get(
                    "yandex_search_query",
                    f"{self._platform_name} {_root_url(url) or ''}".strip(),
                )
                _yandex_referer = f"https://yandex.ru/search/?text={quote_plus(_search_q)}"
                try:
                    await page.goto(
                        "https://yandex.ru",
                        wait_until="domcontentloaded",
                        timeout=_LOAD_TIMEOUT_MS,
                    )
                    await asyncio.sleep(1.2)
                    intercepted.clear()
                    logger.debug(
                        "PlaywrightScraper: Yandex warm-up complete for %s (referer=%s)",
                        self._platform_name,
                        _yandex_referer,
                    )
                except Exception as exc:
                    logger.warning(
                        "PlaywrightScraper: Yandex warm-up failed for %s: %s — continuing",
                        self._platform_name,
                        exc,
                    )
                    _yandex_referer = None  # fall back to direct navigation

            # Navigate to actual product page
            try:
                wait_mode = "domcontentloaded" if fresh_context else "networkidle"
                goto_kwargs: dict = {"wait_until": wait_mode, "timeout": _LOAD_TIMEOUT_MS}
                if _yandex_referer:
                    goto_kwargs["referer"] = _yandex_referer
                await page.goto(url, **goto_kwargs)
                # Give SPA hydration scripts a moment to populate product widgets.
                await asyncio.sleep(1.8 if fresh_context else 1.2)
                await self._ensure_page_materialized(page, url)
            except Exception as exc:
                await self._save_debug_screenshot(page, url)
                raise ScraperError(
                    "API_UNAVAILABLE",
                    f"PlaywrightScraper: page load failed for {self._platform_name}: {exc}",
                ) from exc

            # Anti-bot heuristic: look for CAPTCHA / access denied indicators
            assessment = await self._assess_page(page)
            if assessment.is_blocked:
                await self._save_debug_screenshot(page, url)
                raise ScraperError(
                    "ANTIBOT_BLOCK",
                    f"PlaywrightScraper: anti-bot page detected at {url}",
                    details={
                        "platform": self._platform_name,
                        "reason": assessment.reason,
                        "confidence": assessment.confidence,
                        "attempt_kind": attempt_kind,
                        "proxy_enabled": bool(proxy),
                    },
                )

            # 1. Try network interception
            result = await self._parse_intercepted(intercepted, data_type)
            if result is not None:
                logger.debug(
                    "PlaywrightScraper: extracted %s from intercepted XHR for %s",
                    data_type.value,
                    url,
                )
                return result

            # 2. Fall back to DOM / CSS selectors
            result = await self._parse_dom(page, data_type)
            if result is not None:
                logger.debug(
                    "PlaywrightScraper: extracted %s from DOM for %s",
                    data_type.value,
                    url,
                )
                return result

            # Nothing worked
            page_text = await _page_text(page)
            page_html = await _page_html(page)
            parse_reason = classify_parse_failure(body=page_text, html=page_html)
            await self._save_debug_screenshot(page, url)
            raise ScraperError(
                "PARSE_ERROR",
                f"PlaywrightScraper: could not extract {data_type.value} from {url}",
                details={
                    "platform": self._platform_name,
                    "reason": parse_reason,
                    "attempt_kind": attempt_kind,
                    "proxy_enabled": bool(proxy),
                },
            )

    # ── Backward-compat stubs (nm_id interface) ────────────────────────────
    # L2 requires a URL, not an nm_id.  These stubs prevent silent misuse from
    # code paths that call collect_content/price/stock/reviews directly.

    async def collect_content(self, nm_id: str) -> ContentData:
        raise ScraperError(
            "API_UNAVAILABLE",
            "L2 PlaywrightScraper requires a URL, not nm_id — use ScraperRouter",
        )

    async def collect_price(self, nm_id: str) -> PriceData:
        raise ScraperError(
            "API_UNAVAILABLE",
            "L2 PlaywrightScraper requires a URL, not nm_id — use ScraperRouter",
        )

    async def collect_stock(self, nm_id: str) -> StockData:
        raise ScraperError(
            "API_UNAVAILABLE",
            "L2 PlaywrightScraper requires a URL, not nm_id — use ScraperRouter",
        )

    async def collect_reviews(self, nm_id: str, take: int = 50) -> list[ReviewData]:
        raise ScraperError(
            "API_UNAVAILABLE",
            "L2 PlaywrightScraper requires a URL, not nm_id — use ScraperRouter",
        )

    # ── Network interception parsing ───────────────────────────────────────

    async def _parse_intercepted(
        self,
        responses: list[dict],
        data_type: DataType,
    ) -> Optional[ScrapedData]:
        """
        Attempt to extract typed data from intercepted JSON responses.

        Tries each intercepted response body in order; returns the first
        successful extraction or None if nothing matched.
        """
        for resp in responses:
            body = resp.get("body")
            if not body:
                continue

            try:
                if data_type == DataType.PRICE:
                    result = _try_extract_price(body)
                    if result:
                        return result
                elif data_type == DataType.CONTENT:
                    result = _try_extract_content(body)
                    if result:
                        return result
                elif data_type == DataType.STOCK:
                    result = _try_extract_stock(body)
                    if result:
                        return result
                # REVIEWS via XHR interception not implemented (page-based only)
            except Exception as exc:
                logger.debug("_parse_intercepted: extraction error: %s", exc)
                continue

        return None

    # ── DOM / CSS selector parsing ─────────────────────────────────────────

    async def _parse_dom(
        self,
        page,
        data_type: DataType,
    ) -> Optional[ScrapedData]:
        """
        Extract data using CSS selectors from platform config.

        Returns None (not raises) if selectors are absent or data not found.
        """
        try:
            # Many marketplaces keep canonical product data in JSON-LD / inline
            # script blobs; try that first before brittle CSS selectors.
            json_result = await self._parse_embedded_json(page, data_type)
            if json_result is not None:
                return json_result

            if data_type == DataType.CONTENT:
                return await self._dom_content(page)
            if data_type == DataType.PRICE:
                return await self._dom_price(page)
            if data_type == DataType.STOCK:
                return await self._dom_stock(page)
        except Exception as exc:
            logger.debug("_parse_dom: error for %s: %s", data_type.value, exc)
        return None

    async def _dom_content(self, page) -> Optional[ContentData]:
        title_sel = self._selectors.get("title")
        desc_sel = self._selectors.get("description")
        comp_sel = self._selectors.get("composition")
        img_sel = self._selectors.get("image")

        title = await _text(page, title_sel)
        if not title:
            title = await _attr(page, "meta[property='og:title']", "content")
        if not title:
            title = await _text(page, "h1")
        if not title:
            raw_title = await page.title()
            title = _clean_page_title(raw_title)
        if not title:
            return None

        description = await _text(page, desc_sel) or ""
        if not description:
            description = await _attr(page, "meta[name='description']", "content") or ""
            if not description:
                description = await _attr(page, "meta[property='og:description']", "content") or ""

        composition = await _text(page, comp_sel)
        if not composition:
            page_text = await _page_text(page)
            composition = _extract_composition_from_text(page_text)

        image_url = await _attr(page, img_sel, "src")
        if not image_url:
            image_url = await _attr(page, "meta[property='og:image']", "content")
        if not image_url:
            image_url = await _attr(page, "meta[name='twitter:image']", "content")

        return ContentData(
            title=sanitize(title, 500),
            description=sanitize(description, 5000),
            composition=sanitize(composition, 2000) if composition else None,
            image_url=image_url,
        )

    async def _dom_price(self, page) -> Optional[PriceData]:
        price_sel = self._selectors.get("price")
        orig_sel = self._selectors.get("original_price")
        promo_sel = self._selectors.get("promo_label")

        price_text = await _text(page, price_sel)
        if not price_text:
            # Generic fallbacks for marketplaces where selectors drift often.
            price_text = await _text(page, "[itemprop='price']")
        if not price_text:
            for selector in _fallback_price_selectors(self._platform_name):
                price_text = await _text(page, selector)
                if price_text:
                    break
        if not price_text:
            price_text = await _attr(page, "meta[itemprop='price']", "content")
        if not price_text:
            price_text = await _attr(page, "meta[property='product:price:amount']", "content")
        if not price_text:
            body_text = await _page_text(page)
            price_text = _extract_price_like_text(body_text)
        if not price_text:
            page_html = await _page_html(page)
            price_text = _extract_price_from_html(page_html)
        if not price_text:
            return None

        price = _parse_decimal(price_text)
        if price is None:
            return None

        orig_text = await _text(page, orig_sel)
        if not orig_text:
            orig_text = await _attr(page, "meta[property='product:original_price:amount']", "content")
        original_price = _parse_decimal(orig_text) if orig_text else price
        promo_label = sanitize(await _text(page, promo_sel), 100) if promo_sel else None

        discount_pct = Decimal("0")
        if original_price and original_price > price:
            discount_pct = ((original_price - price) / original_price * 100).quantize(
                Decimal("0.01")
            )

        return PriceData(
            price=price,
            original_price=original_price or price,
            discount_pct=discount_pct,
            promo_label=promo_label or None,
        )

    async def _dom_stock(self, page) -> Optional[StockData]:
        in_stock_sel = self._selectors.get("in_stock")
        qty_sel = self._selectors.get("stock_qty")

        in_stock_text = await _text(page, in_stock_sel) if in_stock_sel else None
        qty_text = await _text(page, qty_sel) if qty_sel else None

        page_text = (await _page_text(page)).lower()
        if "нет в наличии" in page_text or "раскупили" in page_text or "out of stock" in page_text:
            return StockData(in_stock=False, total_qty=0)
        if qty_text is None:
            m = re.search(r"(\d{1,4})\s*шт", page_text)
            if m:
                qty_text = m.group(1)

        # Heuristic: presence of the in-stock selector element = in stock
        in_stock = (in_stock_text is not None) or ("в наличии" in page_text) or ("available" in page_text)
        qty = int(_parse_decimal(qty_text) or 0) if qty_text else (1 if in_stock else 0)

        return StockData(in_stock=in_stock, total_qty=qty)

    async def _parse_embedded_json(
        self,
        page,
        data_type: DataType,
    ) -> Optional[ScrapedData]:
        """
        Parse JSON-LD and common inline JSON blobs from script tags.
        """
        scripts = await page.eval_on_selector_all(
            "script",
            "els => els.map(e => e.textContent || '').filter(Boolean).slice(0, 120)",
        )

        for raw in scripts:
            text = (raw or "").strip()
            if not text:
                continue

            candidates: list[object] = []
            parsed = _try_parse_json_blob(text)
            if parsed is not None:
                candidates.append(parsed)

            m = re.search(r"__NEXT_DATA__\\s*=\\s*(\\{.*?\\})\\s*;", text, flags=re.DOTALL)
            if m:
                parsed_next = _try_parse_json_blob(m.group(1))
                if parsed_next is not None:
                    candidates.append(parsed_next)

            for body in candidates:
                if data_type == DataType.PRICE:
                    result = _try_extract_price(body)
                elif data_type == DataType.CONTENT:
                    result = _try_extract_content(body)
                elif data_type == DataType.STOCK:
                    result = _try_extract_stock(body)
                else:
                    result = None
                if result is not None:
                    return result
        return None

    # ── Anti-bot detection ─────────────────────────────────────────────────

    async def _assess_page(self, page) -> AntiBotAssessment:
        try:
            title = await page.title()
        except Exception:
            title = ""
        try:
            url = page.url
        except Exception:
            url = ""
        body = await _page_text(page)
        html = await _page_html(page)
        return classify_page_state(
            platform_name=self._platform_name,
            url=url,
            title=title,
            body=body,
            html=html,
        )

    async def _ensure_page_materialized(self, page, url: str) -> None:
        """
        Best-effort fallback for pages that initially render blank in headless mode.
        """
        body = (await _page_text(page)).strip()
        if len(body) >= 24:
            return
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=_LOAD_TIMEOUT_MS)
            await asyncio.sleep(1.5)
        except Exception:
            return

    # ── Debug screenshot ───────────────────────────────────────────────────

    async def _save_debug_screenshot(self, page, url: str) -> None:
        """
        Save a full-page screenshot to MinIO under:
            debug/{platform_name}/{YYYY-MM-DD}/{uuid}.png

        Failures are logged as warnings and silently suppressed — screenshot
        upload must never mask the original scraper error.
        """
        try:
            from app.core.minio_client import MinioClient

            screenshot: bytes = await page.screenshot(full_page=True)
            key = f"debug/{self._platform_name}/{date.today()}/{uuid4()}.png"

            client = MinioClient()
            # Ensure debug bucket exists (best-effort)
            try:
                import boto3, io, os
                s3 = boto3.client(
                    "s3",
                    endpoint_url=f"http://{os.environ['MINIO_ENDPOINT']}",
                    aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
                    aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
                )
                try:
                    s3.head_bucket(Bucket=_DEBUG_BUCKET)
                except Exception:
                    s3.create_bucket(Bucket=_DEBUG_BUCKET)
                s3.put_object(
                    Bucket=_DEBUG_BUCKET,
                    Key=key,
                    Body=io.BytesIO(screenshot),
                    ContentType="image/png",
                    ContentLength=len(screenshot),
                )
                logger.info(
                    "PlaywrightScraper: debug screenshot → s3://%s/%s (url=%s attempt=%s)",
                    _DEBUG_BUCKET,
                    key,
                    url,
                    self._attempt_kind,
                )
            except Exception as s3_exc:
                logger.warning(
                    "PlaywrightScraper: S3 upload failed for screenshot: %s", s3_exc
                )
        except Exception as exc:
            logger.warning("PlaywrightScraper: screenshot failed: %s", exc)

    # ── Proxy helper ───────────────────────────────────────────────────────

    def _build_proxy(self) -> Optional[dict]:
        """
        Build a Playwright proxy dict from environment if available.
        Returns None when no proxy is configured (direct connection).
        """
        import os
        proxy_url = os.environ.get("SCRAPER_PROXY_URL")
        if not proxy_url:
            return None
        proxy: dict = {"server": proxy_url}
        user = os.environ.get("SCRAPER_PROXY_USER")
        password = os.environ.get("SCRAPER_PROXY_PASS")
        if user:
            proxy["username"] = user
        if password:
            proxy["password"] = password
        return proxy


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def _try_extract_price(body: object) -> Optional[PriceData]:
    """
    Heuristic JSON price extraction.

    Looks for common key names used by Russian marketplaces in their JSON APIs.
    Returns None when no recognisable price structure is found.
    """
    if not isinstance(body, dict):
        # Some APIs return a list at top level
        if isinstance(body, list) and body:
            for item in body:
                result = _try_extract_price(item)
                if result:
                    return result
        return None

    # Common key names across WB / Ozon / Lenta / Самокат
    price_keys = ("salePriceU", "sale_price", "price", "finalPrice", "currentPrice")
    orig_keys = ("priceU", "original_price", "oldPrice", "basePrice", "originalPrice")
    promo_keys = ("promoText", "promo_label", "badge", "label")

    raw_price = _find_first(body, price_keys)
    if raw_price is None:
        # Recurse into nested dicts (e.g. {"data": {"price": 999}})
        for v in body.values():
            if isinstance(v, (dict, list)):
                result = _try_extract_price(v)
                if result:
                    return result
        return None

    price = _to_decimal(raw_price)
    if price is None:
        return None

    raw_orig = _find_first(body, orig_keys)
    original_price = _to_decimal(raw_orig) if raw_orig is not None else price
    promo_label = str(_find_first(body, promo_keys) or "")[:100] or None

    discount_pct = Decimal("0")
    if original_price and original_price > price:
        discount_pct = ((original_price - price) / original_price * 100).quantize(
            Decimal("0.01")
        )

    return PriceData(
        price=price,
        original_price=original_price or price,
        discount_pct=discount_pct,
        promo_label=promo_label,
    )


def _try_extract_content(body: object) -> Optional[ContentData]:
    """Heuristic JSON content extraction."""
    if not isinstance(body, dict):
        if isinstance(body, list) and body:
            for item in body:
                result = _try_extract_content(item)
                if result:
                    return result
        return None

    title_keys = ("name", "title", "productName", "nm_name")
    desc_keys = ("description", "desc", "shortDescription", "fullDescription")
    comp_keys = ("composition", "consist", "ingredients", "sostav")
    img_keys = ("image", "photo", "img", "mainPhoto", "imageUrl")

    title_raw = _find_first(body, title_keys)
    if title_raw is None:
        for v in body.values():
            if isinstance(v, (dict, list)):
                result = _try_extract_content(v)
                if result:
                    return result
        return None

    title = sanitize(str(title_raw), 500)
    if not title:
        return None

    description = sanitize(str(_find_first(body, desc_keys) or ""), 5000)
    composition_raw = _find_first(body, comp_keys)
    composition = sanitize(str(composition_raw), 2000) if composition_raw else None
    image_url = str(_find_first(body, img_keys) or "") or None

    return ContentData(
        title=title,
        description=description,
        composition=composition,
        image_url=image_url,
    )


def _try_extract_stock(body: object) -> Optional[StockData]:
    """Heuristic JSON stock extraction."""
    if not isinstance(body, dict):
        if isinstance(body, list) and body:
            for item in body:
                result = _try_extract_stock(item)
                if result:
                    return result
        return None

    stock_keys = ("qty", "quantity", "stock", "totalQty", "remains", "остатки")
    in_stock_keys = ("inStock", "in_stock", "available", "isAvailable")

    qty_raw = _find_first(body, stock_keys)
    in_stock_raw = _find_first(body, in_stock_keys)

    if qty_raw is None and in_stock_raw is None:
        for v in body.values():
            if isinstance(v, (dict, list)):
                result = _try_extract_stock(v)
                if result:
                    return result
        return None

    total_qty = int(_to_decimal(qty_raw) or 0) if qty_raw is not None else 0
    if in_stock_raw is not None:
        in_stock = bool(in_stock_raw)
    else:
        in_stock = total_qty > 0

    return StockData(in_stock=in_stock, total_qty=total_qty)


# ---------------------------------------------------------------------------
# Low-level DOM helpers
# ---------------------------------------------------------------------------

async def _text(page, selector: Optional[str]) -> Optional[str]:
    """Return text_content for the first matching element, or None."""
    if not selector:
        return None
    try:
        return await page.text_content(selector, timeout=_SELECTOR_TIMEOUT_MS)
    except Exception:
        return None


async def _attr(page, selector: Optional[str], attribute: str) -> Optional[str]:
    """Return an attribute value for the first matching element, or None."""
    if not selector:
        return None
    try:
        el = await page.query_selector(selector)
        if el:
            return await el.get_attribute(attribute)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------

def _parse_decimal(text: Optional[str]) -> Optional[Decimal]:
    """Parse a price string like '1 299,00 ₽' → Decimal('1299.00')."""
    if not text:
        return None
    cleaned = (
        text.replace("\u00a0", "")  # non-breaking space
        .replace(" ", "")
        .replace("₽", "")
        .replace("руб", "")
        .replace(",", ".")
        .strip()
    )
    # Keep only digits and a single decimal point
    import re
    m = re.search(r"\d+(?:\.\d+)?", cleaned)
    if not m:
        return None
    try:
        return Decimal(m.group())
    except InvalidOperation:
        return None


def _to_decimal(value: object) -> Optional[Decimal]:
    """Convert a JSON numeric value (int/float/str/kopecks) to Decimal roubles."""
    if value is None:
        return None
    try:
        d = Decimal(str(value))
        # WB stores prices in kopecks (divide by 100 if suspiciously large)
        if d > Decimal("100000"):
            d = (d / 100).quantize(Decimal("0.01"))
        return d
    except InvalidOperation:
        return None


def _find_first(d: dict, keys: tuple) -> object:
    """Return the value of the first key found in d, or None."""
    for k in keys:
        if k in d:
            return d[k]
    return None


def _try_parse_json_blob(text: str) -> Optional[object]:
    text = text.strip()
    if not text:
        return None
    if not (text.startswith("{") or text.startswith("[")):
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _clean_page_title(title: str) -> Optional[str]:
    if not title:
        return None
    cleaned = re.split(r"\s+[|\-]\s+", title, maxsplit=1)[0].strip()
    return cleaned or None


async def _page_text(page) -> str:
    try:
        return (await page.inner_text("body", timeout=_SELECTOR_TIMEOUT_MS)) or ""
    except Exception:
        return ""


async def _page_html(page) -> str:
    try:
        return await page.content()
    except Exception:
        return ""


def _extract_price_like_text(text: str) -> Optional[str]:
    if not text:
        return None
    # Example matches: "1 299 ₽", "999,90 руб", "1299.00 ₽"
    m = re.search(r"(\d[\d\s]{0,9}(?:[.,]\d{1,2})?)\s*(?:₽|руб)", text, flags=re.IGNORECASE)
    if not m:
        return None
    return m.group(1)


def _extract_price_from_html(html: str) -> Optional[str]:
    if not html:
        return None
    patterns = (
        r'"(?:price|finalPrice|currentPrice|sale_price|salePriceU|discountPrice|regularPrice)"\s*:\s*(?:\{[^{}]{0,160}?"value"\s*:\s*)?"?(?P<v>\d+(?:[.,]\d{1,2})?)',
        r'"amount"\s*:\s*"?(?P<v>\d+(?:[.,]\d{1,2})?)',
        r'"offers"\s*:\s*\{[^{}]{0,240}?"price"\s*:\s*"?(?P<v>\d+(?:[.,]\d{1,2})?)',
        r'data-(?:price|product-price|current-price)\s*=\s*"(?P<v>\d+(?:[.,]\d{1,2})?)"',
    )
    for pattern in patterns:
        m = re.search(pattern, html, flags=re.IGNORECASE)
        if m:
            return m.group("v")
    return None


def _extract_composition_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    m = re.search(
        r"(?:состав|ingredients)\s*[:\-]\s*(.{10,600})",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return None
    value = re.split(r"\n{2,}|Отзывы|Характеристики|Описание", m.group(1), maxsplit=1)[0]
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def _fallback_price_selectors(platform_name: str) -> tuple[str, ...]:
    name = (platform_name or "").lower()
    if "wildberries" in name:
        return (
            ".price-block__final-price",
            "[class*='final-price']",
            "[data-link*='price']",
        )
    if "ozon" in name:
        return (
            "[data-widget='webPrice'] span",
            "[data-widget*='price'] span",
            "[class*='price']",
        )
    if "самокат" in name or "samocat" in name:
        return (
            "[data-testid*='price']",
            "[class*='Price']",
            "[class*='price']",
        )
    if "лента" in name or "lenta" in name:
        return (
            ".price-main__value",
            ".price__value",
            "[class*='price']",
        )
    return ()


def _root_url(url: str) -> Optional[str]:
    try:
        p = urlparse(url)
        if not p.scheme or not p.netloc:
            return None
        return f"{p.scheme}://{p.netloc}/"
    except Exception:
        return None
