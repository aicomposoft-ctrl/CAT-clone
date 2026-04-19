from __future__ import annotations

from app.core.base_scraper import ScraperError


_HARD_ANTIBOT_REASONS = frozenset({"challenge_page", "empty_response", "geo_or_auth_block"})
_RETRYABLE_CODES = frozenset({"RATE_LIMITED", "API_UNAVAILABLE"})


def should_retry_scrape_error(exc: ScraperError) -> bool:
    if exc.code in _RETRYABLE_CODES:
        return True
    if exc.code == "ALL_LEVELS_FAILED":
        reason = getattr(exc, "details", {}).get("reason")
        return reason not in _HARD_ANTIBOT_REASONS
    if exc.code == "ANTIBOT_BLOCK":
        reason = getattr(exc, "details", {}).get("reason")
        return reason not in _HARD_ANTIBOT_REASONS
    return exc.code == "PARSE_ERROR"
