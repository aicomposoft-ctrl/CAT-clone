"""
Scraper registry.

get_l1_scraper(platform_name) returns an instantiated L1 scraper for the
given platform. Raises ScraperError("NOT_FOUND") if no L1 scraper exists.

L0 scrapers (seller API) are instantiated directly by ScraperRouter using the
L0_REGISTRY mapping (api_token_type → class).
"""

from __future__ import annotations

from app.core.base_scraper import ScraperError


def get_l1_scraper(platform_name: str):
    """
    Return an instantiated L1 (Playwright/httpx-based) scraper for the given
    platform name (matches Platform.name in DB, case-sensitive).

    Raises:
        ScraperError("NOT_FOUND") if no L1 scraper is registered for the platform.
    """
    from app.core.proxy import get_proxy_rotator

    _L1_MAP = {
        "Wildberries": _get_wildberries,
        "Ozon": _get_ozon,
        "Lenta": _get_lenta,
        "Лента": _get_lenta,       # DB seed uses Cyrillic — both aliases supported
        "Самокат": _get_samocat,
        "Samocat": _get_samocat,   # Latin alias for backward compat
    }

    factory = _L1_MAP.get(platform_name)
    if factory is None:
        raise ScraperError(
            "NOT_FOUND",
            f"No L1 scraper registered for platform: {platform_name!r}",
        )
    return factory(get_proxy_rotator())


def _get_wildberries(proxy_rotator):
    from app.scrapers.wildberries import WildberriesScraper
    return WildberriesScraper(proxy_rotator)


def _get_ozon(proxy_rotator):
    from app.scrapers.ozon import OzonScraper
    return OzonScraper(proxy_rotator)


def _get_lenta(proxy_rotator):
    from app.scrapers.lenta import LentaScraper
    return LentaScraper(proxy_rotator)


def _get_samocat(proxy_rotator):
    from app.scrapers.samocat import SamokatScraper
    return SamokatScraper(proxy_rotator)
