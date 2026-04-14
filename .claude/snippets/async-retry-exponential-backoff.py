# Snippet: Async Retry with Exponential Backoff
# Category: Snippet | Language: Python (asyncio)
# Maturity: 🔴 Alpha | Extracted: 2026-03-27 from CAT project
#
# When to Use:
#   Any async operation that can fail transiently:
#   HTTP requests, external APIs, rate-limited scrapers, DB connection attempts.
#
# When NOT to Use:
#   - Non-idempotent operations (POST that creates records — retrying may duplicate)
#   - Operations with no retry budget (strict latency SLOs)
#   - Permanent errors (404, 401, schema validation) — retrying won't help
#
# Prerequisites: Python 3.11+, asyncio
# Dependencies: None (stdlib only)

import asyncio
import logging
from functools import wraps
from typing import Callable, TypeVar, ParamSpec

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


def async_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    exceptions: tuple = (Exception,),
    backoff_factor: float = 2.0,
):
    """
    Decorator for async functions: retry on failure with exponential backoff.

    Args:
        max_retries:    Maximum number of retry attempts (default: 3)
        base_delay:     Initial delay in seconds (default: 1.0)
        exceptions:     Exception types to catch and retry (default: all)
        backoff_factor: Multiplier per attempt (default: 2.0 → 1s, 2s, 4s)

    Delays: attempt 0 → base_delay * factor^0, attempt 1 → base_delay * factor^1, ...
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    last_exception = exc
                    if attempt == max_retries:
                        logger.error(
                            "%s failed after %d attempts: %s",
                            func.__name__, max_retries + 1, exc,
                        )
                        raise
                    delay = base_delay * (backoff_factor ** attempt)
                    logger.warning(
                        "%s attempt %d/%d failed: %s. Retrying in %.1fs",
                        func.__name__, attempt + 1, max_retries, exc, delay,
                    )
                    await asyncio.sleep(delay)
            raise last_exception  # unreachable, satisfies type checker
        return wrapper
    return decorator


# --- Usage ---
#
# import httpx
#
# @async_retry(max_retries=3, base_delay=1.0, exceptions=(httpx.HTTPError,))
# async def fetch_product_page(url: str) -> str:
#     async with httpx.AsyncClient() as client:
#         resp = await client.get(url, timeout=10)
#         resp.raise_for_status()
#         return resp.text
#
#
# --- Celery variant (synchronous, uses self.retry) ---
#
# @celery_app.task(bind=True, max_retries=3)
# def process_task(self, item_id: str):
#     try:
#         do_work(item_id)
#     except TransientError as exc:
#         raise self.retry(exc=exc, countdown=2 ** self.request.retries)
