"""
OpenAIAgentScraper — L3 scraper: Playwright accessibility tree + OpenAI extraction.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from urllib.parse import urlparse
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional
from uuid import UUID

from openai import APIError, AsyncOpenAI
from pydantic import BaseModel, ValidationError

from app.core.anti_bot import classify_page_state, classify_parse_failure
from app.core.base_scraper import (
    ContentData,
    DataType,
    PriceData,
    ReviewData,
    ScrapedData,
    ScraperError,
    StockData,
)
from app.core.browser_pool import BrowserPool

logger = logging.getLogger(__name__)

_ARIA_MAX_CHARS = 8_000
_OPENAI_MODEL = os.getenv("OPENAI_L3_MODEL", "gpt-4o-mini")
_MAX_TOKENS = int(os.getenv("OPENAI_L3_MAX_TOKENS", "512"))
_CACHE_TTL = 3600
_DAILY_LIMIT = int(os.getenv("AGENT_DAILY_LIMIT", "100"))
_LOAD_TIMEOUT_MS = 30_000

_SYSTEM_PROMPTS: dict[DataType, str] = {
    DataType.CONTENT: (
        "Extract product information from the accessibility tree.\n"
        'Return ONLY JSON: {"title":"...","description":"...","composition":"...","image_url":"..."}\n'
        "Use null for missing fields."
    ),
    DataType.PRICE: (
        "Extract price information from the accessibility tree.\n"
        'Return ONLY JSON: {"price":999.99,"original_price":1199.99,"discount_pct":16.7,"promo_label":"..."}\n'
        "Prices as numbers in rubles. Do not return null for price/original_price: "
        "infer from nearby price-like text when needed."
    ),
    DataType.STOCK: (
        "Determine product availability from the accessibility tree.\n"
        'Return ONLY JSON: {"in_stock":true,"total_qty":0}\n'
        "Use total_qty only when explicit quantity is present."
    ),
}


class _ContentResponse(BaseModel):
    title: str = ""
    description: str = ""
    composition: Optional[str] = None
    image_url: Optional[str] = None


class _PriceResponse(BaseModel):
    price: Optional[Decimal] = None
    original_price: Optional[Decimal] = None
    discount_pct: Optional[Decimal] = Decimal("0")
    promo_label: Optional[str] = None


class _StockResponse(BaseModel):
    in_stock: bool
    total_qty: int = 0


class OpenAIAgentScraper:
    scraper_level: int = 3
    rate_limit: float = 0.2

    def __init__(
        self,
        platform,
        org_id: UUID,
        redis_client,
        browser_pool: BrowserPool,
    ) -> None:
        self._platform = platform
        self._platform_name: str = getattr(platform, "name", str(platform))
        self._platform_id: str = str(getattr(platform, "id", platform))
        self._org_id = org_id
        self._redis = redis_client
        self._pool = browser_pool
        self._openai = AsyncOpenAI()
        self._attempt_kind: str = "l3"

    async def collect(self, url: str, data_type: DataType) -> ScrapedData:
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
        cache_key = f"agent_result:openai:{self._platform_id}:{url_hash}:{data_type.value}"
        cached = self._redis.get(cache_key)
        if cached is not None:
            try:
                return self._deserialize(cached, data_type)
            except ScraperError:
                # Drop stale/invalid cache payloads (e.g. prior null-valued JSON)
                # and continue with a fresh L3 extraction.
                self._redis.delete(cache_key)

        aria_text = await self._get_aria_snapshot(url)
        self._check_rate_limit()
        raw_json = await self._call_openai(aria_text, data_type)
        self._redis.setex(cache_key, _CACHE_TTL, raw_json)
        return self._parse_response(raw_json, data_type, fallback_text=aria_text)

    async def collect_content(self, nm_id: str) -> ContentData:
        raise ScraperError("API_UNAVAILABLE", "L3 OpenAIAgentScraper requires URL")

    async def collect_price(self, nm_id: str) -> PriceData:
        raise ScraperError("API_UNAVAILABLE", "L3 OpenAIAgentScraper requires URL")

    async def collect_stock(self, nm_id: str) -> StockData:
        raise ScraperError("API_UNAVAILABLE", "L3 OpenAIAgentScraper requires URL")

    async def collect_reviews(self, nm_id: str, take: int = 50) -> list[ReviewData]:
        raise ScraperError("API_UNAVAILABLE", "L3 OpenAIAgentScraper requires URL")

    def _check_rate_limit(self) -> None:
        today = date.today().isoformat()
        key = f"l3_rate:{self._org_id}:{today}"
        pipe = self._redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 86_400)
        count, _ = pipe.execute()
        if count > _DAILY_LIMIT:
            raise ScraperError(
                "RATE_LIMITED",
                f"L3 daily limit exceeded for org={self._org_id} (count={count})",
            )

    async def _get_aria_snapshot(self, url: str) -> str:
        async with self._pool.acquire(
            proxy=self._build_proxy(),
            persistent_profile_key=f"l3:{self._platform_name}",
        ) as page:
            root = _root_url(url)
            if root:
                try:
                    await page.goto(root, wait_until="domcontentloaded", timeout=_LOAD_TIMEOUT_MS)
                    await page.wait_for_timeout(1200)
                except Exception:
                    # Best-effort warmup: continue with product URL.
                    pass
            try:
                await page.goto(url, wait_until="networkidle", timeout=_LOAD_TIMEOUT_MS)
                await page.wait_for_timeout(1200)
            except Exception as exc:
                raise ScraperError(
                    "API_UNAVAILABLE",
                    f"OpenAIAgentScraper (L3/{self._platform_name}): page load failed: {exc}",
                    details={
                        "platform": self._platform_name,
                        "reason": "empty_response",
                        "attempt_kind": self._attempt_kind,
                    },
                ) from exc

            await self._ensure_page_materialized(page, url)
            assessment = await self._assess_page(page)
            if assessment.is_blocked:
                raise ScraperError(
                    "ANTIBOT_BLOCK",
                    f"OpenAIAgentScraper (L3/{self._platform_name}): anti-bot page detected",
                    details={
                        "platform": self._platform_name,
                        "reason": assessment.reason,
                        "confidence": assessment.confidence,
                        "attempt_kind": self._attempt_kind,
                        "proxy_enabled": bool(self._build_proxy()),
                    },
                )

            aria_text: str | None = None
            try:
                ax = await page.accessibility.snapshot(interesting_only=True)
                if ax is not None:
                    aria_text = json.dumps(ax, ensure_ascii=False)
            except Exception:
                aria_text = None
            if not aria_text:
                try:
                    aria_text = await page.inner_text("body")
                except Exception:
                    aria_text = None
            if not aria_text:
                try:
                    aria_text = await page.content()
                except Exception as exc:
                    raise ScraperError(
                        "API_UNAVAILABLE",
                        f"OpenAIAgentScraper (L3/{self._platform_name}): page snapshot failed: {exc}",
                        details={
                            "platform": self._platform_name,
                            "reason": classify_parse_failure(body="", html=""),
                            "attempt_kind": self._attempt_kind,
                        },
                    ) from exc
        return (aria_text or "")[:_ARIA_MAX_CHARS]

    async def _ensure_page_materialized(self, page, url: str) -> None:
        """
        Best-effort fallback for pages that render sparse/blank on first load.
        """
        try:
            body = (await page.inner_text("body")).strip()
        except Exception:
            body = ""
        if len(body) >= 24:
            return
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=_LOAD_TIMEOUT_MS)
            await page.wait_for_timeout(1800)
        except Exception:
            return

    async def _assess_page(self, page):
        try:
            title = await page.title()
        except Exception:
            title = ""
        try:
            url = page.url
        except Exception:
            url = ""
        try:
            body = await page.inner_text("body")
        except Exception:
            body = ""
        try:
            html = await page.content()
        except Exception:
            html = ""
        return classify_page_state(
            platform_name=self._platform_name,
            url=url,
            title=title,
            body=body,
            html=html,
        )

    def _build_proxy(self) -> Optional[dict]:
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

    async def _call_openai(self, aria_text: str, data_type: DataType) -> str:
        system_prompt = _SYSTEM_PROMPTS.get(data_type)
        if system_prompt is None:
            raise ScraperError(
                "AGENT_EXTRACTION_FAILED",
                f"OpenAIAgentScraper: no system prompt for data_type={data_type.value}",
            )
        sanitized = aria_text.replace("<", "\uff1c").replace(">", "\uff1e")
        user_message = f"<accessibility_tree>\n{sanitized}\n</accessibility_tree>"
        try:
            resp = await self._openai.chat.completions.create(
                model=_OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
        except APIError as exc:
            raise ScraperError(
                "API_UNAVAILABLE",
                f"OpenAIAgentScraper: OpenAI API error: {exc}",
            ) from exc

        raw = (resp.choices[0].message.content or "").strip() if resp.choices else ""
        if not raw:
            raise ScraperError(
                "AGENT_EXTRACTION_FAILED",
                "OpenAIAgentScraper: OpenAI returned an empty response",
            )
        return raw

    def _parse_response(
        self,
        raw_json: str,
        data_type: DataType,
        *,
        fallback_text: str = "",
    ) -> ScrapedData:
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ScraperError(
                "AGENT_EXTRACTION_FAILED",
                f"OpenAIAgentScraper: JSON parse error: {exc}",
            ) from exc

        try:
            if data_type == DataType.CONTENT:
                m = _ContentResponse.model_validate(data)
                return ContentData(
                    title=m.title,
                    description=m.description,
                    composition=m.composition,
                    image_url=m.image_url,
                )
            if data_type == DataType.PRICE:
                m = _PriceResponse.model_validate(data)
                price = m.price
                original_price = m.original_price
                if price is None:
                    inferred = _extract_price_like_text(fallback_text)
                    price = inferred
                if original_price is None:
                    original_price = price
                if price is None or original_price is None:
                    raise ScraperError(
                        "PARSE_ERROR",
                        "OpenAIAgentScraper: missing price values after L3 extraction",
                    )
                discount_pct = m.discount_pct or Decimal("0")
                if discount_pct == Decimal("0") and original_price > price:
                    discount_pct = (
                        (original_price - price) / original_price * 100
                    ).quantize(Decimal("0.01"))
                return PriceData(
                    price=price,
                    original_price=original_price,
                    discount_pct=discount_pct,
                    promo_label=m.promo_label,
                )
            if data_type == DataType.STOCK:
                m = _StockResponse.model_validate(data)
                return StockData(in_stock=m.in_stock, total_qty=m.total_qty)
        except (ValidationError, InvalidOperation) as exc:
            raise ScraperError(
                "PARSE_ERROR",
                f"OpenAIAgentScraper: validation error for {data_type.value}: {exc}",
            ) from exc

        raise ScraperError(
            "AGENT_EXTRACTION_FAILED",
            f"OpenAIAgentScraper: unsupported data_type={data_type.value}",
        )

    def _deserialize(self, raw: bytes | str, data_type: DataType) -> ScrapedData:
        if isinstance(raw, bytes):
            raw = raw.decode()
        return self._parse_response(raw, data_type)


def _root_url(url: str) -> Optional[str]:
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return None
        return f"{parsed.scheme}://{parsed.netloc}/"
    except Exception:
        return None


def _extract_price_like_text(text: str) -> Optional[Decimal]:
    if not text:
        return None
    import re

    # Match examples: "199.99", "199,99", "1 299 ₽", "1299 руб"
    m = re.search(r"(\d[\d\s]{0,9}(?:[.,]\d{1,2})?)\s*(?:₽|руб|\b)", text, flags=re.IGNORECASE)
    if not m:
        return None
    raw = m.group(1).replace(" ", "").replace(",", ".")
    try:
        return Decimal(raw)
    except Exception:
        return None

