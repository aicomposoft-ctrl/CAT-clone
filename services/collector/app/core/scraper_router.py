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


def _register_l0_scrapers() -> None:
    """Populate L0_REGISTRY lazily to avoid import cycles at module load."""
    if L0_REGISTRY:
        return
    try:
        from app.scrapers.seller_api.wb_seller import WBSellerAPIScraper
        L0_REGISTRY["wb_seller"] = WBSellerAPIScraper
    except ImportError:
        logger.warning("WBSellerAPIScraper not available — l0 disabled for Wildberries")


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
        chain = self._build_chain(creds)

        last_error: Optional[ScraperError] = None

        for level in chain:
            scraper = self._instantiate(level, platform, creds)
            if scraper is None:
                logger.debug("ScraperRouter: level %s not available — skipping", level)
                continue

            try:
                result = self._invoke(scraper, sku_id, data_type)
                # Tag the result with the level that succeeded (informational)
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
                if exc.code == "TOKEN_INVALID":
                    logger.warning(
                        "ScraperRouter: TOKEN_INVALID for platform=%s org=%s — "
                        "falling back (future: send alert)",
                        platform.name,
                        org_id,
                    )
                if exc.code in _FALLBACK_CODES:
                    logger.info(
                        "ScraperRouter: level=%s failed with %s — trying next level",
                        level,
                        exc.code,
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

    def _build_chain(self, creds: Optional[OrgPlatformCredentials]) -> list[str]:
        """
        Return the fallback chain for this org/platform combination.

        Priority:
          1. Explicit override in creds.fallback_chain (stored as JSON list of strings)
          2. Default chain based on whether an API token is available
        """
        if creds and creds.fallback_chain:
            chain = creds.fallback_chain
            if isinstance(chain, list) and all(isinstance(x, str) for x in chain):
                return chain
            logger.warning(
                "ScraperRouter: invalid fallback_chain value %r — using default", chain
            )
        return self._default_chain(creds)

    def _default_chain(self, creds: Optional[OrgPlatformCredentials]) -> list[str]:
        if creds and creds.api_token_encrypted:
            return ["l0", "l2"]
        return ["l1", "l2"]

    def _instantiate(
        self,
        level: str,
        platform: Platform,
        creds: Optional[OrgPlatformCredentials],
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

        # l2 (browser automation) and l3 (CAPTCHA solver) — Sprint B/C
        logger.debug("ScraperRouter: level %s not yet implemented", level)
        return None

    def _invoke(
        self, scraper: BaseScraper, sku_id: str, data_type: DataType
    ) -> ScrapedData:
        """
        Call the scraper's collect() method.

        L0 scrapers implement synchronous collect().
        L1 scrapers are async — wrap with asyncio.run() for the sync Celery context.
        """
        # L0 (WBSellerAPIScraper and future L0s) — synchronous
        if scraper.scraper_level == 0:
            return scraper.collect(sku_id, data_type)

        # L1+ scrapers — async; run in a new event loop from the sync Celery worker
        return asyncio.run(self._invoke_async(scraper, sku_id, data_type))

    @staticmethod
    async def _invoke_async(
        scraper: BaseScraper, sku_id: str, data_type: DataType
    ) -> ScrapedData:
        """Dispatch to the appropriate async collect_* method for L1 scrapers."""
        if data_type == DataType.CONTENT:
            return await scraper.collect_content(sku_id)
        if data_type == DataType.PRICE:
            return await scraper.collect_price(sku_id)
        if data_type == DataType.STOCK:
            return await scraper.collect_stock(sku_id)
        if data_type == DataType.REVIEWS:
            return await scraper.collect_reviews(sku_id)
        raise ScraperError("PARSE_ERROR", f"Unknown DataType: {data_type}")
