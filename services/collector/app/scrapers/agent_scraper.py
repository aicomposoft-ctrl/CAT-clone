"""
AgentScraper — L3 scraper: Playwright accessibility tree + Claude API extraction.

Flow:
  1. Open page with Playwright (uses BrowserPool).
  2. page.locator("body").aria_snapshot() → ARIA text.
     NOTE: page.accessibility.snapshot() is Node.js only — Python uses aria_snapshot().
  3. Send to Claude API (claude-haiku-4-5-20251001) with system prompt.
     System prompt contains extraction instructions (injection protection).
     User message wraps the ARIA text in <accessibility_tree>...</accessibility_tree>.
  4. Validate response JSON with Pydantic (not dataclasses).
  5. Cache result in Redis for 1 hour.

Rate limiting:
  Redis counter key = l3_rate:{org_id}:{date}, max 100/day per org.
  Exceeding the limit raises ScraperError("RATE_LIMITED", "L3 daily limit exceeded").

Cache:
  Key = agent_result:{platform_id}:{url_hash}:{data_type}
  TTL = 3600 seconds.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional
from uuid import UUID

import anthropic
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

# Maximum ARIA text length sent to Claude (characters)
_ARIA_MAX_CHARS = 8_000
# Claude model for L3 extraction
_CLAUDE_MODEL = "claude-haiku-4-5-20251001"
# Maximum tokens in Claude response
_MAX_TOKENS = 512
# Redis cache TTL (seconds)
_CACHE_TTL = 3600
# Per-org daily L3 request limit (configurable via env)
_DAILY_LIMIT = int(os.getenv("AGENT_DAILY_LIMIT", "100"))
# Playwright page-load timeout (ms)
_LOAD_TIMEOUT_MS = 30_000

# ---------------------------------------------------------------------------
# System prompts — immutable extraction instructions (injection protection)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPTS: dict[DataType, str] = {
    DataType.CONTENT: (
        "Extract product information from the accessibility tree.\n"
        'Return ONLY a JSON object: {"title": "...", "description": "...", '
        '"composition": "...", "image_url": "..."}\n'
        "Use null for missing fields. No explanation."
    ),
    DataType.PRICE: (
        "Extract price information from the accessibility tree.\n"
        "Return ONLY a JSON object with these exact fields:\n"
        '  "price": current selling price as a plain number in rubles (REQUIRED, no currency symbols)\n'
        '  "original_price": full price before any discount as a plain number (equal to price if no discount)\n'
        '  "discount_pct": discount percentage as a plain number, 0 if no discount\n'
        '  "promo_label": promo/sale label string, or null if absent\n'
        "Example format only (do NOT copy these values): "
        '{"price": 0.00, "original_price": 0.00, "discount_pct": 0, "promo_label": null}\n'
        "Use the actual prices from the page. No explanation."
    ),
    DataType.STOCK: (
        "Determine product availability from the accessibility tree.\n"
        'Return ONLY a JSON object: {"in_stock": true, "total_qty": 0}\n'
        "Use total_qty only if explicit quantity shown, otherwise 0. No explanation."
    ),
}

# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class _ContentResponse(BaseModel):
    title: str = ""
    description: str = ""
    composition: Optional[str] = None
    image_url: Optional[str] = None


class _PriceResponse(BaseModel):
    price: Decimal
    original_price: Decimal
    discount_pct: Decimal = Decimal("0")
    promo_label: Optional[str] = None


class _StockResponse(BaseModel):
    in_stock: bool
    total_qty: int = 0


# ---------------------------------------------------------------------------
# AgentScraper
# ---------------------------------------------------------------------------


class AgentScraper:
    """
    L3 scraper: Playwright accessibility tree + Claude API extraction.

    Args:
        platform:      Platform ORM object (needs .id and .name attributes).
        org_id:        Organisation UUID — used for per-org rate limiting.
        redis_client:  Redis client for caching and rate limiting.
        browser_pool:  BrowserPool singleton from get_browser_pool().
    """

    platform = None  # set dynamically per-instance
    scraper_level: int = 3
    rate_limit: float = 0.2  # 1 request per 5 seconds

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
        self._claude = anthropic.AsyncAnthropic()
        self._attempt_kind: str = "l3"

    # ── Public API ─────────────────────────────────────────────────────────

    async def collect(self, url: str, data_type: DataType) -> ScrapedData:
        """
        Collect data for the given URL using Playwright + Claude API.

        Args:
            url:       Full product page URL.
            data_type: Which data to collect.

        Returns:
            ScrapedData matching data_type.

        Raises:
            ScraperError("RATE_LIMITED")            — daily L3 limit exceeded.
            ScraperError("API_UNAVAILABLE")         — page load failed.
            ScraperError("ANTIBOT_BLOCK")           — anti-bot page detected.
            ScraperError("AGENT_EXTRACTION_FAILED") — Claude response invalid.
        """
        # 1. Check cache first — cache hits must NOT consume daily L3 budget.
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
        cache_key = f"agent_result:{self._platform_id}:{url_hash}:{data_type.value}"
        cached = self._redis.get(cache_key)
        if cached is not None:
            # Log url_hash not the full URL — URLs can contain signed params or session tokens
            logger.debug(
                "AgentScraper: cache hit url_hash=%s data_type=%s", url_hash, data_type.value
            )
            return self._deserialize(cached, data_type)

        # 2. Load page and capture ARIA snapshot.
        # If anti-bot blocks before Claude call, we should not burn L3 quota.
        aria_text = await self._get_aria_snapshot(url)

        # 3. Enforce per-org daily rate limit only when we are about to call Claude.
        self._check_rate_limit()

        # 4. Call Claude API
        raw_json = await self._call_claude(aria_text, data_type)

        # 5. Cache result
        self._redis.setex(cache_key, _CACHE_TTL, raw_json)

        # 6. Parse and return
        return self._parse_response(raw_json, data_type)

    # ── Backward-compat stubs (nm_id interface) ────────────────────────────

    async def collect_content(self, nm_id: str) -> ContentData:
        raise ScraperError(
            "API_UNAVAILABLE",
            "L3 AgentScraper requires a URL, not nm_id — use ScraperRouter",
        )

    async def collect_price(self, nm_id: str) -> PriceData:
        raise ScraperError(
            "API_UNAVAILABLE",
            "L3 AgentScraper requires a URL, not nm_id — use ScraperRouter",
        )

    async def collect_stock(self, nm_id: str) -> StockData:
        raise ScraperError(
            "API_UNAVAILABLE",
            "L3 AgentScraper requires a URL, not nm_id — use ScraperRouter",
        )

    async def collect_reviews(self, nm_id: str, take: int = 50) -> list[ReviewData]:
        raise ScraperError(
            "API_UNAVAILABLE",
            "L3 AgentScraper requires a URL, not nm_id — use ScraperRouter",
        )

    # ── Rate limiting ──────────────────────────────────────────────────────

    def _check_rate_limit(self) -> None:
        """
        Enforce per-org daily L3 request limit via Redis counter.

        Uses a pipeline to make INCR + EXPIRE atomic — if the process dies
        between two separate calls the key would have no TTL and leak forever.
        """
        today = date.today().isoformat()
        key = f"l3_rate:{self._org_id}:{today}"

        pipe = self._redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 86_400)  # always refresh TTL — harmless if already set
        count, _ = pipe.execute()

        if count > _DAILY_LIMIT:
            raise ScraperError(
                "RATE_LIMITED",
                f"L3 daily limit exceeded for org={self._org_id} (count={count})",
            )

    # ── ARIA snapshot ──────────────────────────────────────────────────────

    async def _get_aria_snapshot(self, url: str) -> str:
        """
        Load the page with Playwright and return its ARIA accessibility snapshot.

        Uses BrowserPool to acquire a page context. The ARIA snapshot is truncated
        to _ARIA_MAX_CHARS to keep Claude API costs predictable.

        URL is never logged — it may contain signed query parameters or session tokens.
        Error messages use the platform name and scraper level instead.
        """
        async with self._pool.acquire(
            proxy=self._build_proxy(),
            persistent_profile_key=f"l3:{self._platform_name}",
        ) as page:
            try:
                await page.goto(url, wait_until="networkidle", timeout=_LOAD_TIMEOUT_MS)
            except Exception as exc:
                raise ScraperError(
                    "API_UNAVAILABLE",
                    f"AgentScraper (L3/{self._platform_name}): page load failed: {exc}",
                    details={
                        "platform": self._platform_name,
                        "reason": "empty_response",
                        "attempt_kind": self._attempt_kind,
                    },
                ) from exc

            # Anti-bot heuristic
            assessment = await self._assess_page(page)
            if assessment.is_blocked:
                raise ScraperError(
                    "ANTIBOT_BLOCK",
                    f"AgentScraper (L3/{self._platform_name}): anti-bot page detected",
                    details={
                        "platform": self._platform_name,
                        "reason": assessment.reason,
                        "confidence": assessment.confidence,
                        "attempt_kind": self._attempt_kind,
                        "proxy_enabled": bool(self._build_proxy()),
                    },
                )

            # Playwright Python compatibility:
            # - locator(...).aria_snapshot() is unavailable in older versions.
            # - use page.accessibility.snapshot() first, then graceful fallbacks.
            aria_text: str | None = None
            try:
                ax = await page.accessibility.snapshot(interesting_only=True)
                if ax is not None:
                    aria_text = json.dumps(ax, ensure_ascii=False)
            except Exception:
                aria_text = None

            if not aria_text:
                try:
                    body_text = await page.inner_text("body")
                    if body_text:
                        aria_text = body_text
                except Exception:
                    aria_text = None

            if not aria_text:
                try:
                    aria_text = await page.content()
                except Exception as exc:
                    raise ScraperError(
                        "API_UNAVAILABLE",
                        f"AgentScraper (L3/{self._platform_name}): page snapshot failed: {exc}",
                        details={
                            "platform": self._platform_name,
                            "reason": classify_parse_failure(body="", html=""),
                            "attempt_kind": self._attempt_kind,
                        },
                    ) from exc

        return aria_text[:_ARIA_MAX_CHARS]

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

    # ── Claude API call ────────────────────────────────────────────────────

    async def _call_claude(self, aria_text: str, data_type: DataType) -> str:
        """
        Send the ARIA snapshot to Claude API and return the raw JSON string.

        The system prompt is fixed at construction time — user-controlled content
        is confined to the <accessibility_tree> block in the user message, preventing
        prompt injection from page content from escaping the extraction context.
        """
        system_prompt = _SYSTEM_PROMPTS.get(data_type)
        if system_prompt is None:
            raise ScraperError(
                "AGENT_EXTRACTION_FAILED",
                f"AgentScraper: no system prompt for data_type={data_type.value}",
            )

        # Sanitize ARIA text: replace < > to prevent XML tag injection that could
        # break out of the <accessibility_tree> delimiter in the user message.
        # Fullwidth equivalents preserve readability for Claude.
        sanitized = aria_text.replace("<", "\uff1c").replace(">", "\uff1e")
        user_message = f"<accessibility_tree>\n{sanitized}\n</accessibility_tree>"

        try:
            response = await self._claude.messages.create(
                model=_CLAUDE_MODEL,
                max_tokens=_MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
        except anthropic.APIError as exc:
            raise ScraperError(
                "API_UNAVAILABLE",
                f"AgentScraper: Claude API error: {exc}",
            ) from exc

        raw = response.content[0].text.strip() if response.content else ""
        if not raw:
            raise ScraperError(
                "AGENT_EXTRACTION_FAILED",
                "AgentScraper: Claude returned an empty response",
            )

        # Log only data_type and length — never log response content (may contain scraped PII)
        logger.debug(
            "AgentScraper: Claude responded for data_type=%s len=%d",
            data_type.value,
            len(raw),
        )
        return raw

    # ── Response parsing ───────────────────────────────────────────────────

    def _parse_response(self, raw_json: str, data_type: DataType) -> ScrapedData:
        """
        Parse and validate Claude's raw JSON string into a typed ScrapedData object.

        Raises ScraperError("AGENT_EXTRACTION_FAILED") on JSON parse error or
        Pydantic validation error.
        """
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ScraperError(
                "AGENT_EXTRACTION_FAILED",
                f"AgentScraper: JSON parse error: {exc} — raw={raw_json[:200]}",
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
                # Guard against Claude echoing back the prompt's example values (0.00)
                # or any obviously sentinel price — these indicate the page price was
                # not found rather than an actual zero-priced product.
                if m.price <= Decimal("0"):
                    raise ScraperError(
                        "AGENT_EXTRACTION_FAILED",
                        f"AgentScraper: L3 returned zero/negative price — "
                        f"price={m.price} (page price not found or prompt echo)",
                    )
                # Compute discount_pct if not provided or zero but prices differ
                discount_pct = m.discount_pct
                if discount_pct == Decimal("0") and m.original_price > m.price:
                    discount_pct = (
                        (m.original_price - m.price) / m.original_price * 100
                    ).quantize(Decimal("0.01"))
                return PriceData(
                    price=m.price,
                    original_price=m.original_price,
                    discount_pct=discount_pct,
                    promo_label=m.promo_label,
                )

            if data_type == DataType.STOCK:
                m = _StockResponse.model_validate(data)
                return StockData(in_stock=m.in_stock, total_qty=m.total_qty)

        except (ValidationError, InvalidOperation) as exc:
            raise ScraperError(
                "AGENT_EXTRACTION_FAILED",
                f"AgentScraper: Pydantic validation error for {data_type.value}: {exc}",
            ) from exc

        raise ScraperError(
            "AGENT_EXTRACTION_FAILED",
            f"AgentScraper: unsupported data_type={data_type.value}",
        )

    def _deserialize(self, raw: bytes | str, data_type: DataType) -> ScrapedData:
        """Deserialize a cached raw JSON string back into ScrapedData."""
        if isinstance(raw, bytes):
            raw = raw.decode()
        return self._parse_response(raw, data_type)
