"""
BrowserPool — fixed-size Playwright browser pool for the collector-playwright service.

MUST only be used in the solo-pool Celery worker (collector-playwright).
Do NOT import or use in forking workers — Playwright is not fork-safe.

Usage:
    pool = BrowserPool(size=2)
    async with pool.acquire() as page:
        await page.goto(url)
    pool.close()  # called on worker shutdown

Celery signal wiring at module level:
    init_browser_pool  → worker_init  (creates the singleton pool)
    close_browser_pool → worker_shutdown (gracefully closes all browsers)
    get_browser_pool() → returns the singleton; raises RuntimeError if not initialised
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

logger = logging.getLogger(__name__)


class BrowserPool:
    """
    Manages a fixed-size pool of Playwright browser instances.

    Each acquire() creates a fresh BrowserContext (isolated cookies/storage) and
    returns a single Page from that context.  The context is closed when the
    async-with block exits — ensuring complete isolation between requests.

    Args:
        size: Maximum number of concurrent browser instances.
    """

    def __init__(self, size: int = 2) -> None:
        self._size = size
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._playwright = None
        self._browsers: list = []  # list of playwright Browser objects
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def _start(self) -> None:
        """Async initialisation — launch Playwright and `size` browser instances."""
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                "playwright package is not installed — "
                "BrowserPool is only available in the collector-playwright service."
            ) from exc

        self._semaphore = asyncio.Semaphore(self._size)
        self._playwright = await async_playwright().start()
        for _ in range(self._size):
            browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            self._browsers.append(browser)
        logger.info("BrowserPool started: %d browser(s)", self._size)

    async def _stop(self) -> None:
        """Async shutdown — close all browsers then stop Playwright."""
        for browser in self._browsers:
            try:
                await browser.close()
            except Exception as exc:
                logger.warning("BrowserPool: error closing browser: %s", exc)
        self._browsers.clear()

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as exc:
                logger.warning("BrowserPool: error stopping playwright: %s", exc)
            self._playwright = None

        logger.info("BrowserPool stopped")

    def close(self) -> None:
        """Synchronous shutdown — safe to call from worker_shutdown signal handler."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Schedule cleanup; caller should not need the result
                asyncio.ensure_future(self._stop())
            else:
                loop.run_until_complete(self._stop())
        except Exception as exc:
            logger.warning("BrowserPool.close(): %s", exc)

    # ── Acquire ────────────────────────────────────────────────────────────

    @asynccontextmanager
    async def acquire(
        self,
        proxy: Optional[dict] = None,
    ) -> AsyncIterator:
        """
        Acquire a browser page from the pool.

        Creates a new BrowserContext (for full isolation) on the least-loaded
        browser, then yields a Page.  The context is closed on exit.

        Args:
            proxy: Optional Playwright proxy dict, e.g.
                   {"server": "http://host:port", "username": "u", "password": "p"}

        Yields:
            playwright Page object.
        """
        if self._semaphore is None:
            raise RuntimeError("BrowserPool not started — call await pool._start() first")

        async with self._semaphore:
            # Pick the browser with the fewest open contexts (simple load balancing)
            browser = min(self._browsers, key=lambda b: len(b.contexts))

            # Crash recovery: if the browser is disconnected, relaunch it
            if not browser.is_connected():
                logger.warning("BrowserPool: browser disconnected — relaunching")
                browser = await self._relaunch(browser)

            context_kwargs: dict = {
                "viewport": {"width": 1280, "height": 800},
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                "locale": "ru-RU",
                "extra_http_headers": {"Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8"},
            }
            if proxy:
                context_kwargs["proxy"] = proxy

            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()
            try:
                yield page
            finally:
                try:
                    await context.close()
                except Exception as exc:
                    logger.warning("BrowserPool: error closing context: %s", exc)

    async def _relaunch(self, old_browser) -> object:
        """Replace a crashed browser in self._browsers and return the new one."""
        idx = self._browsers.index(old_browser)
        try:
            await old_browser.close()
        except Exception:
            pass  # already disconnected
        new_browser = await self._playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._browsers[idx] = new_browser
        logger.info("BrowserPool: relaunched browser at index %d", idx)
        return new_browser


# ---------------------------------------------------------------------------
# Celery signal wiring — singleton per worker process
# ---------------------------------------------------------------------------

_pool: Optional[BrowserPool] = None


def get_browser_pool() -> BrowserPool:
    """
    Return the process-global BrowserPool.

    Raises:
        RuntimeError: if called outside a collector-playwright Celery worker.
    """
    if _pool is None:
        raise RuntimeError(
            "BrowserPool not initialized — "
            "is this running in the collector-playwright Celery worker?"
        )
    return _pool


def _init_pool_sync(size: int = 2) -> None:
    """Create and start the BrowserPool in a new event loop (worker_init context)."""
    global _pool
    _pool = BrowserPool(size=size)
    # Start in a fresh event loop — worker_init runs before any tasks
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_pool._start())
    except Exception as exc:
        logger.error("BrowserPool: failed to start: %s", exc)
        _pool = None
        raise


try:
    from celery.signals import worker_init, worker_shutdown

    @worker_init.connect
    def init_browser_pool(**kwargs) -> None:
        """Celery worker_init: start the BrowserPool singleton."""
        size = int(__import__("os").environ.get("BROWSER_POOL_SIZE", "2"))
        logger.info("BrowserPool: initialising with size=%d", size)
        _init_pool_sync(size)

    @worker_shutdown.connect
    def close_browser_pool(**kwargs) -> None:
        """Celery worker_shutdown: gracefully close all browsers."""
        if _pool is not None:
            logger.info("BrowserPool: shutting down")
            _pool.close()

except ImportError:
    # Celery not installed — signals not wired (unit-test environment)
    logger.debug("BrowserPool: celery not available, signals not registered")
