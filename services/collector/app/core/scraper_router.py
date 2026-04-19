"""
ScraperRouter — adaptive scraper fallback pipeline.

Resolves the best available scraper for a (platform, org) pair and falls
back through the configured chain when a scraper fails with a retriable error.

Fallback chain:
  Default with API token  → ["l0", "l2"]   (L2 = browser; Sprint B/C)
  Default without token   → ["l1", "l2"]

  Per-org override stored in OrgPlatformCredentials.fallback_chain.

Retriable error codes (trigger fallback to next level):
  TOKEN_INVALID, API_UNAVAILABLE, RATE_LIMITED, ANTIBOT_BLOCK

Non-retriable codes (re-raised immediately):
  NOT_FOUND, PARSE_ERROR, and any unexpected exception

Multi-tenant isolation:
  OrgPlatformCredentials is ALWAYS loaded filtered by (platform_id, org_id).
  Never query credentials without an org_id filter.

Sync requirement:
  All public methods are synchronous — called from Celery tasks.
  L1 scrapers (async) are wrapped with asyncio.run() internally.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.base_scraper import BaseScraper, DataType, ScrapedData, ScraperError
from app.models import OrgPlatformCredentials, Platform

logger = logging.getLogger(__name__)

# Error codes that trigger fallback to the next scraper level
_FALLBACK_CODES = frozenset({
    "TOKEN_INVALID",
    "API_UNAVAILABLE",
    "RATE_LIMITED",
    "ANTIBOT_BLOCK",
})

# Registry mapping api_token_type → L0 scraper class constructor (takes token: str)
L0_REGISTRY: dict[str, type] = {}

# URL templates for L2 (PlaywrightScraper needs a full page URL, not just sku_id).
# {sku_id} is replaced with the external platform ID at runtime.
_L2_URL_TEMPLATES: dict[str, str] = {
    "Wildberries": "https://www.wildberries.ru/catalog/{sku_id}/detail.aspx",
    "Ozon":        "https://www.ozon.ru/product/{sku_id}/",
    "Лента":       "https://lenta.com/product/{sku_id}/",
    "Lenta":       "https://lenta.com/product/{sku_id}/",
    "Самокат":     "https://samokat.ru/product/{sku_id}",
    "Samocat":     "https://samokat.ru/product/{sku_id}",
}

# Allowlist of valid fallback chain level identifiers
_VALID_LEVELS = frozenset({"l0", "l1", "l2", "l3"})
_HARD_BLOCK_REASONS = frozenset({"challenge_page", "empty_response", "geo_or_auth_block"})
_PLATFORM_ANTIBOT_POLICY: dict[str, dict[str, object]] = {
    "Wildberries": {"hard_block_reasons": {"challenge_page", "empty_response"}, "allow_l2_second_chance": True},
    "Ozon": {"hard_block_reasons": {"challenge_page", "empty_response"}, "allow_l2_second_chance": True},
    "Самокат": {"hard_block_reasons": {"challenge_page"}, "allow_l2_second_chance": True},
    "Samocat": {"hard_block_reasons": {"challenge_page"}, "allow_l2_second_chance": True},
    "Лента": {"hard_block_reasons": {"challenge_page", "geo_or_auth_block"}, "allow_l2_second_chance": True},
    "Lenta": {"hard_block_reasons": {"challenge_page", "geo_or_auth_block"}, "allow_l2_second_chance": True},
}


def _is_truthy_env(name: str) -> bool:
    value = (os.getenv(name) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _apply_runtime_chain_policy(chain: list[str]) -> list[str]:
    """
    Apply runtime policy switches (env-based) to the fallback chain.
    """
    out = list(chain)
    if _is_truthy_env("SCRAPER_DISABLE_L3"):
        out = [lvl for lvl in out if lvl != "l3"]
    return out


def _l3_provider() -> str:
    return (os.getenv("L3_PROVIDER") or "anthropic").strip().lower()


def _register_l0_scrapers() -> None:
    """Populate L0_REGISTRY lazily to avoid import cycles at module load."""
    if L0_REGISTRY:
        return
    try:
        from app.scrapers.seller_api.wb_seller import WBSellerAPIScraper
        L0_REGISTRY["wb_seller"] = WBSellerAPIScraper
    except ImportError:
        logger.warning("WBSellerAPIScraper not available — l0 disabled for Wildberries")
    try:
        from app.scrapers.seller_api.ozon_seller import OzonSellerAPIScraper
        L0_REGISTRY["ozon_seller"] = OzonSellerAPIScraper
    except ImportError:
        logger.warning("OzonSellerAPIScraper not available — l0 disabled for Ozon")


class ScraperRouter:
    """
    Routes scraping requests through a fallback chain of scraper levels.

    Args:
        db:           Sync SQLAlchemy Session (from tasks/_db.py).
        redis_client: Optional Redis client (reserved for future caching).
    """

    def __init__(self, db: Session, redis_client=None) -> None:
        self._db = db
        self._redis = redis_client
        _register_l0_scrapers()

    # ── Public API ─────────────────────────────────────────────────────────

    def collect(
        self,
        platform_id: UUID,
        sku_id: str,
        data_type: DataType,
        org_id: UUID,
        page_url: str | None = None,
    ) -> ScrapedData:
        """
        Collect data for a SKU, falling back through the scraper chain.

        Args:
            platform_id: UUID of the platform row.
            sku_id:      External platform ID (e.g. WB nm_id).
            data_type:   Which data to collect (CONTENT, PRICE, STOCK, REVIEWS).
            org_id:      Organisation UUID — used to load per-org credentials.
                         MUST be provided; never use a fallback here.

        Returns:
            ScrapedData — ContentData | PriceData | StockData | list[ReviewData]

        Raises:
            ScraperError("ALL_LEVELS_FAILED") if every level in the chain failed.
        """
        platform = self._load_platform(platform_id)
        creds = self._load_creds(platform_id, org_id)
        chain = self._build_chain(creds, platform)

        last_error: Optional[ScraperError] = None

        for level in chain:
            scraper = self._instantiate(level, platform, creds, org_id)
            if scraper is None:
                logger.debug("ScraperRouter: level %s not available — skipping", level)
                continue

            try:
                result = self._invoke(scraper, sku_id, data_type, platform.name, page_url)
                # Return result alongside the scraper_level as a tuple so tasks
                # can persist provenance to the DB without mutating result objects.
                # Callers unpack: data, scraper_level = router.collect(...)
                result.scraper_level = scraper.scraper_level  # type: ignore[union-attr]
                logger.info(
                    "ScraperRouter: collected %s for sku=%s via %s (level=%s)",
                    data_type.value,
                    sku_id,
                    platform.name,
                    level,
                )
                return result

            except ScraperError as exc:
                last_error = exc
                # L1 PARSE_ERROR: scraper couldn't handle the sku_id format (e.g. slug
                # instead of numeric product_id). L2/L3 use URL templates, not the raw
                # sku_id, so they may still work.
                if level == "l1" and exc.code == "PARSE_ERROR":
                    logger.info(
                        "ScraperRouter: level=l1 PARSE_ERROR for %s sku=%s — "
                        "L1 cannot handle sku_id format, trying L2",
                        platform.name,
                        sku_id,
                    )
                    continue
                if level == "l2" and exc.code in {"ANTIBOT_BLOCK", "PARSE_ERROR"}:
                    second_chance = self._maybe_retry_l2_adaptive(
                        scraper, exc, sku_id, data_type, platform.name, page_url
                    )
                    if second_chance is not None:
                        second_chance.scraper_level = scraper.scraper_level  # type: ignore[union-attr]
                        return second_chance
                    if exc.code == "PARSE_ERROR":
                        # L2 may fail on volatile front-end selectors while L3 can
                        # still extract from ARIA snapshot. Allow fallback to L3.
                        logger.info(
                            "ScraperRouter: level=l2 parse error for %s sku=%s — trying next level",
                            platform.name,
                            sku_id,
                        )
                        continue
                if exc.code == "TOKEN_INVALID":
                    logger.warning(
                        "ScraperRouter: TOKEN_INVALID for platform=%s org=%s — "
                        "falling back (future: send alert)",
                        platform.name,
                        org_id,
                    )
                if exc.code in _FALLBACK_CODES:
                    details = getattr(exc, "details", {})
                    logger.info(
                        "ScraperRouter: level=%s failed with %s reason=%s confidence=%s attempt=%s proxy=%s — trying next level",
                        level,
                        exc.code,
                        details.get("reason", "unknown"),
                        details.get("confidence", "n/a"),
                        details.get("attempt_kind", "n/a"),
                        details.get("proxy_enabled", "n/a"),
                    )
                    continue
                # Non-retriable — propagate immediately
                raise

            except Exception as exc:
                # Unexpected errors (e.g. programming mistakes) — propagate
                logger.exception(
                    "ScraperRouter: unexpected error at level=%s for sku=%s: %s",
                    level,
                    sku_id,
                    exc,
                )
                raise

        raise ScraperError(
            "ALL_LEVELS_FAILED",
            f"All scraper levels exhausted for platform={platform.name} "
            f"sku={sku_id} data_type={data_type.value}. "
            f"Last error: {last_error}",
            details=getattr(last_error, "details", {}),
        )

    # ── Private helpers ────────────────────────────────────────────────────

    def _load_platform(self, platform_id: UUID) -> Platform:
        """Load platform metadata (global — no org_id filter needed for metadata)."""
        platform = self._db.get(Platform, platform_id)
        if platform is None:
            raise ScraperError("NOT_FOUND", f"Platform {platform_id} not found")
        return platform

    def _load_creds(
        self, platform_id: UUID, org_id: UUID
    ) -> Optional[OrgPlatformCredentials]:
        """
        Load org-specific credentials for the platform.

        ALWAYS filters by BOTH platform_id AND org_id — multi-tenant isolation.
        Returns None if no credentials row exists (org hasn't configured the platform).
        """
        stmt = (
            select(OrgPlatformCredentials)
            .where(OrgPlatformCredentials.platform_id == platform_id)
            .where(OrgPlatformCredentials.org_id == org_id)  # MANDATORY tenant filter
        )
        result = self._db.execute(stmt).scalar_one_or_none()
        return result

    def _build_chain(
        self,
        creds: Optional[OrgPlatformCredentials],
        platform: "Platform",
    ) -> list[str]:
        """
        Return the fallback chain for this org/platform combination.

        Priority:
          1. Explicit per-org override in creds.fallback_chain
          2. Platform-level default derived from platform.scraper_mode
        """
        if creds and creds.fallback_chain:
            chain = creds.fallback_chain
            if (
                isinstance(chain, list)
                and all(isinstance(x, str) for x in chain)
                and all(x in _VALID_LEVELS for x in chain)
            ):
                return _apply_runtime_chain_policy(chain)
            logger.warning(
                "ScraperRouter: invalid or unknown level in fallback_chain %r — using default",
                chain,
            )
        return _apply_runtime_chain_policy(self._default_chain(creds, platform))

    def _default_chain(
        self,
        creds: Optional[OrgPlatformCredentials],
        platform: Optional["Platform"] = None,
    ) -> list[str]:
        """
        Map platform.scraper_mode to a fallback chain.

        Supported modes:
          'auto'       → all levels; L0 first if token present
          'playwright' → ["l2", "l3"]  (skip httpx — known to fail on this platform)
          'browser'    → same as 'playwright' (legacy alias from migration 0014)
          'agent'      → ["l3"]  (Claude extraction only)
          'api'        → ["l0", "l1"] / ["l1"] — no browser, API only
          'scrape'     → ["l1"]  (httpx only, no seller API)
          'token'      → ["l0"] if token present, else fall through to auto
          unknown      → treated as 'auto'
        """
        mode = (getattr(platform, "scraper_mode", None) or "auto").lower()
        has_token = bool(creds and creds.api_token_encrypted)

        if mode in ("playwright", "browser"):
            return ["l2", "l3"]
        if mode == "agent":
            return ["l3"]
        if mode == "scrape":
            return ["l1"]
        if mode == "api":
            return ["l0", "l1"] if has_token else ["l1"]
        if mode == "token":
            # token-only: require API token; fall through to auto if missing
            return ["l0"] if has_token else ["l1", "l2", "l3"]
        # 'auto' or any unrecognised value: try all levels, L3 as last resort
        return ["l0", "l1", "l2", "l3"] if has_token else ["l1", "l2", "l3"]

    def _instantiate(
        self,
        level: str,
        platform: Platform,
        creds: Optional[OrgPlatformCredentials],
        org_id: Optional[UUID] = None,
    ) -> Optional[BaseScraper]:
        """
        Instantiate the scraper for a given level.

        Returns None if the level is not yet implemented or prerequisites are missing.
        """
        if level == "l0":
            if not creds or not creds.api_token_encrypted:
                logger.debug(
                    "ScraperRouter: l0 requested but no token for platform=%s",
                    platform.name,
                )
                return None
            token_type = creds.api_token_type
            scraper_cls = L0_REGISTRY.get(token_type)
            if scraper_cls is None:
                logger.warning(
                    "ScraperRouter: no L0 scraper registered for api_token_type=%r",
                    token_type,
                )
                return None
            from app.core.crypto import decrypt_token
            token = decrypt_token(creds.api_token_encrypted)
            return scraper_cls(token)

        if level == "l1":
            from app.scrapers import get_l1_scraper
            try:
                return get_l1_scraper(platform.name)
            except ScraperError:
                logger.warning(
                    "ScraperRouter: no L1 scraper for platform=%s — skipping",
                    platform.name,
                )
                return None

        if level == "l2":
            from app.scrapers.playwright_scraper import PlaywrightScraper
            from app.core.browser_pool import get_browser_pool
            selectors = creds.selectors if creds and hasattr(creds, "selectors") else {}
            platform_config = getattr(platform, "platform_config", None) or {}
            try:
                pool = get_browser_pool()
            except RuntimeError:
                logger.warning(
                    "ScraperRouter: BrowserPool not available — l2 disabled "
                    "(not running in collector-playwright worker?)"
                )
                return None
            return PlaywrightScraper(platform, selectors or {}, pool, platform_config)

        if level == "l3":
            from app.core.browser_pool import get_browser_pool
            if self._redis is None:
                logger.warning("ScraperRouter: no Redis client — l3 disabled")
                return None
            try:
                pool = get_browser_pool()
            except RuntimeError:
                logger.warning(
                    "ScraperRouter: BrowserPool not available — l3 disabled"
                )
                return None
            provider = _l3_provider()
            if provider == "openai":
                from app.scrapers.openai_agent_scraper import OpenAIAgentScraper

                return OpenAIAgentScraper(platform, org_id, self._redis, pool)

            from app.scrapers.agent_scraper import AgentScraper

            return AgentScraper(platform, org_id, self._redis, pool)

        logger.debug("ScraperRouter: level %s not yet implemented", level)
        return None

    def _invoke(
        self,
        scraper: BaseScraper,
        sku_id: str,
        data_type: DataType,
        platform_name: str = "",
        page_url: str | None = None,
    ) -> ScrapedData:
        """
        Call the scraper's collect() method.

        L0 scrapers implement synchronous collect().
        L1 scrapers are async — wrap with asyncio.run() for the sync Celery context.
        """
        # L0 (WBSellerAPIScraper and future L0s) — synchronous
        if scraper.scraper_level == 0:
            return scraper.collect(sku_id, data_type)

        # L2/L3: Playwright browsers are bound to the BrowserPool's background loop.
        # Use run_coroutine_threadsafe to schedule on that loop instead of creating
        # a new one (which would cause "attached to different loop" asyncio errors).
        if getattr(scraper, "scraper_level", 1) in (2, 3):
            from app.core.browser_pool import _pool_loop
            if _pool_loop is not None and _pool_loop.is_running():
                fut = asyncio.run_coroutine_threadsafe(
                    self._invoke_async(scraper, sku_id, data_type, platform_name, page_url),
                    _pool_loop,
                )
                return fut.result(timeout=120)
            # Pool loop not available — fall through to asyncio.run (will likely fail gracefully)
            logger.warning("ScraperRouter: BrowserPool loop not available for L2/L3")

        # L1 (and L2/L3 fallback): run in a fresh event loop
        return asyncio.run(self._invoke_async(scraper, sku_id, data_type, platform_name, page_url))

    def _maybe_retry_l2_adaptive(
        self,
        scraper,
        exc: ScraperError,
        sku_id: str,
        data_type: DataType,
        platform_name: str,
        page_url: str | None,
    ):
        policy = _PLATFORM_ANTIBOT_POLICY.get(platform_name, {})
        if not policy.get("allow_l2_second_chance", False):
            return None
        reason = getattr(exc, "details", {}).get("reason")
        if exc.code == "PARSE_ERROR" and reason != "soft_parse_failure":
            return None
        if reason and self._is_hard_block(platform_name, reason):
            try:
                from app.core.browser_pool import get_browser_pool

                get_browser_pool().evict_shared_context(f"l2:{platform_name}")
            except Exception:
                pass
        if not hasattr(scraper, "collect_with_strategy"):
            return None
        logger.info(
            "ScraperRouter: level=l2 adaptive retry platform=%s reason=%s attempt=fresh_profile",
            platform_name,
            reason or "unknown",
        )
        try:
            return self._invoke_l2_second_chance(
                scraper, sku_id, data_type, platform_name, page_url
            )
        except ScraperError as second_exc:
            logger.info(
                "ScraperRouter: level=l2 second chance failed with %s for %s sku=%s",
                second_exc.code,
                platform_name,
                sku_id,
            )
            return None

    def _is_hard_block(self, platform_name: str, reason: str) -> bool:
        policy = _PLATFORM_ANTIBOT_POLICY.get(platform_name, {})
        hard_reasons = set(policy.get("hard_block_reasons", _HARD_BLOCK_REASONS))
        return reason in hard_reasons

    def _invoke_l2_second_chance(
        self,
        scraper,
        sku_id: str,
        data_type: DataType,
        platform_name: str,
        page_url: str | None,
    ):
        from app.core.browser_pool import _pool_loop

        if page_url:
            url = page_url
        else:
            tmpl = _L2_URL_TEMPLATES.get(platform_name)
            url = tmpl.format(sku_id=sku_id) if tmpl else sku_id
        coro = scraper.collect_with_strategy(
            url,
            data_type,
            fresh_context=True,
            attempt_kind="fresh_profile",
        )
        if _pool_loop is not None and _pool_loop.is_running():
            return asyncio.run_coroutine_threadsafe(coro, _pool_loop).result(timeout=120)
        return asyncio.run(coro)

    @staticmethod
    async def _invoke_async(
        scraper,
        sku_id: str,
        data_type: DataType,
        platform_name: str = "",
        page_url: str | None = None,
    ) -> ScrapedData:
        """
        Dispatch to the appropriate async collect method.

        L1 scrapers: calls collect_content/price/stock/reviews(sku_id).
        L2/L3 scrapers (PlaywrightScraper/AgentScraper): calls collect(url, data_type)
            where url is built from _L2_URL_TEMPLATES using sku_id.
        """
        # L2 and L3: unified collect(url, data_type) interface
        if getattr(scraper, "scraper_level", 1) in (2, 3):
            if page_url:
                url = page_url
            else:
                tmpl = _L2_URL_TEMPLATES.get(platform_name)
                if tmpl:
                    url = tmpl.format(sku_id=sku_id)
                else:
                    # Fallback: treat sku_id as full URL (legacy behaviour)
                    url = sku_id
                    logger.warning(
                        "ScraperRouter: no URL template for platform=%r — "
                        "passing sku_id as URL for L2 (may fail)",
                        platform_name,
                    )
            return await scraper.collect(url, data_type)

        # L1: legacy per-type methods
        if data_type == DataType.CONTENT:
            return await scraper.collect_content(sku_id)
        if data_type == DataType.PRICE:
            return await scraper.collect_price(sku_id)
        if data_type == DataType.STOCK:
            return await scraper.collect_stock(sku_id)
        if data_type == DataType.REVIEWS:
            return await scraper.collect_reviews(sku_id)
        raise ScraperError("PARSE_ERROR", f"Unknown DataType: {data_type}")
