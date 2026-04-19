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

# Shared launch args used by both initial launch and crash-recovery relaunch.
# Keeping them in one place prevents the relaunch path from silently omitting
# stealth flags (e.g. --disable-blink-features=AutomationControlled).
_CHROMIUM_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
]


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
        self._shared_contexts: dict[str, object] = {}

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def _start(self) -> None:
        """Async initialisation — launch Playwright/patchright and `size` browser instances."""
        try:
            from patchright.async_api import async_playwright
            logger.info("BrowserPool: using patchright (Runtime.enable CDP leak patched)")
        except ImportError:
            try:
                from playwright.async_api import async_playwright
                logger.warning(
                    "BrowserPool: patchright not installed — falling back to playwright. "
                    "CDP automation leak NOT patched. "
                    "Install with: pip install patchright && patchright install chromium"
                )
            except ImportError as exc:
                raise RuntimeError(
                    "Neither patchright nor playwright is installed — "
                    "BrowserPool is only available in the collector-playwright service."
                ) from exc

        self._semaphore = asyncio.Semaphore(self._size)
        self._playwright = await async_playwright().start()
        for _ in range(self._size):
            browser = await self._playwright.chromium.launch(
                headless=True,
                args=_CHROMIUM_LAUNCH_ARGS,
            )
            self._browsers.append(browser)
        logger.info("BrowserPool started: %d browser(s)", self._size)

    async def _stop(self) -> None:
        """Async shutdown — close all browsers then stop Playwright."""
        for key, context in list(self._shared_contexts.items()):
            try:
                await context.close()
            except Exception as exc:
                logger.warning("BrowserPool: error closing shared context %s: %s", key, exc)
        self._shared_contexts.clear()

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
        geolocation: Optional[dict] = None,
        permissions: Optional[list] = None,
        persistent_profile_key: Optional[str] = None,
        profile_variant: str = "default",
    ) -> AsyncIterator:
        """
        Acquire a browser page from the pool.

        Creates a new BrowserContext (for full isolation) on the least-loaded
        browser, then yields a Page.  The context is closed on exit.

        Args:
            proxy:        Optional Playwright proxy dict, e.g.
                          {"server": "http://host:port", "username": "u", "password": "p"}
            geolocation:  Optional geolocation override, e.g.
                          {"latitude": 55.7558, "longitude": 37.6173, "accuracy": 10}
                          Required for geo-gated platforms like Samokat.
            permissions:  List of browser permissions to grant, e.g. ["geolocation"].
                          Must be set together with geolocation for sites that request it.

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

            context_kwargs = self._context_kwargs(profile_variant)
            if proxy:
                context_kwargs["proxy"] = proxy
            if geolocation:
                context_kwargs["geolocation"] = geolocation
            if permissions:
                context_kwargs["permissions"] = permissions

            context = None
            shared_key = None
            if persistent_profile_key:
                shared_key = f"{persistent_profile_key}|{proxy}|{geolocation}|{permissions}"
                context = self._shared_contexts.get(shared_key)
                if context is None:
                    context = await browser.new_context(**context_kwargs)
                    self._shared_contexts[shared_key] = context
                    logger.info(
                        "BrowserPool: created shared context for %s variant=%s",
                        persistent_profile_key,
                        profile_variant,
                    )
            else:
                context = await browser.new_context(**context_kwargs)

            page = await context.new_page()
            # Stealth: remove webdriver property and navigator.plugins signature
            # that Ozon/WB anti-bot checks for headless detection.
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['ru-RU','ru','en-US','en']});
                window.chrome = {runtime: {}};
            """)
            try:
                yield page
            finally:
                try:
                    await page.close()
                except Exception as exc:
                    logger.warning("BrowserPool: error closing page: %s", exc)
                if shared_key is None:
                    try:
                        await context.close()
                    except Exception as exc:
                        logger.warning("BrowserPool: error closing context: %s", exc)

    def evict_shared_context(self, persistent_profile_key: str) -> None:
        if _pool_loop is None or not _pool_loop.is_running():
            return
        victims = [key for key in self._shared_contexts if key.startswith(f"{persistent_profile_key}|")]
        for key in victims:
            context = self._shared_contexts.pop(key, None)
            if context is None:
                continue
            future = asyncio.run_coroutine_threadsafe(context.close(), _pool_loop)
            try:
                future.result(timeout=10)
            except Exception as exc:
                logger.warning("BrowserPool: failed evicting shared context %s: %s", key, exc)

    def _context_kwargs(self, profile_variant: str) -> dict:
        if profile_variant == "fresh":
            return {
                "viewport": {"width": 1366, "height": 768},
                "user_agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/121.0.0.0 Safari/537.36"
                ),
                "locale": "ru-RU",
                "timezone_id": "Europe/Moscow",
                "extra_http_headers": {"Accept-Language": "ru-RU,ru;q=0.95,en-US;q=0.8"},
            }
        return {
            "viewport": {"width": 1280, "height": 800},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "locale": "ru-RU",
            "timezone_id": "Europe/Moscow",
            "extra_http_headers": {"Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8"},
        }

    async def _relaunch(self, old_browser) -> object:
        """Replace a crashed browser in self._browsers and return the new one."""
        idx = self._browsers.index(old_browser)
        try:
            await old_browser.close()
        except Exception:
            pass  # already disconnected
        new_browser = await self._playwright.chromium.launch(
            headless=True,
            args=_CHROMIUM_LAUNCH_ARGS,
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


_pool_loop: Optional[asyncio.AbstractEventLoop] = None


def _init_pool_sync(size: int = 2) -> None:
    """
    Create and start the BrowserPool in a dedicated background thread.

    Playwright browsers are bound to the event loop that created them.
    Running them in a background thread with a persistent loop avoids the
    "attached to different loop" error that occurs when asyncio.run() in
    Celery tasks creates a fresh loop per call.
    """
    import threading

    global _pool, _pool_loop

    started_event = threading.Event()
    error_holder: list = []

    def _thread_main():
        global _pool, _pool_loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _pool_loop = loop
        _pool = BrowserPool(size=size)
        try:
            loop.run_until_complete(_pool._start())
            started_event.set()
            loop.run_forever()  # keep loop alive for future use
        except Exception as exc:
            logger.error("BrowserPool: failed to start: %s", exc)
            _pool = None
            error_holder.append(exc)
            started_event.set()

    t = threading.Thread(target=_thread_main, daemon=True, name="browser-pool-loop")
    t.start()
    started_event.wait(timeout=60)  # wait up to 60s for browsers to launch
    if error_holder:
        raise error_holder[0]


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
