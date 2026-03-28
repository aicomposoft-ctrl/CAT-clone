"""
Proxy rotation for scraper HTTP requests.

Design:
  - ProxyRotator is a module-level singleton per Celery worker process.
  - Populated ONCE at worker startup via Celery worker_process_init signal.
  - Thread-safe round-robin rotation.
  - get_proxy_rotator() initialises lazily if not already initialised.

Usage in celery_app.py:
    from celery.signals import worker_process_init
    @worker_process_init.connect
    def init_worker(**kwargs):
        get_proxy_rotator()   # warm up proxy list at worker startup
"""

from __future__ import annotations

import logging
import os
import re
import threading
from typing import Optional

# Allowlist format: http(s)://host[:port] — rejects plaintext credentials or
# bare IP:port strings that could be misused if the proxy list is compromised.
_PROXY_URL_RE = re.compile(r"^https?://[A-Za-z0-9.\-]+(:\d{1,5})?(/)?$")

logger = logging.getLogger(__name__)

_proxy_rotator: Optional["ProxyRotator"] = None
_init_lock = threading.Lock()


class ProxyRotator:
    """Thread-safe round-robin proxy rotator."""

    def __init__(self, proxy_list: list[str]) -> None:
        self._proxies = proxy_list
        self._idx = 0
        self._lock = threading.Lock()

    def next(self) -> Optional[str]:
        if not self._proxies:
            return None
        with self._lock:
            proxy = self._proxies[self._idx % len(self._proxies)]
            self._idx += 1
        return proxy

    def __len__(self) -> int:
        return len(self._proxies)

    @classmethod
    def from_env(cls) -> "ProxyRotator":
        """
        Fetch proxy list from PROXY_LIST_URL with 10s timeout.

        Returns empty rotator (no proxies) if env var not set.
        Raises on HTTP error — caller should handle at worker startup.
        """
        import requests  # sync — called at worker init, not in async context

        url = os.environ.get("PROXY_LIST_URL")
        if not url:
            logger.info("PROXY_LIST_URL not set — running without proxies")
            return cls([])

        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        raw = [p.strip() for p in resp.text.strip().splitlines() if p.strip()]
        proxies = [p for p in raw if _PROXY_URL_RE.match(p)]
        rejected = len(raw) - len(proxies)
        if rejected:
            logger.warning("Proxy list: rejected %d malformed entries (failed format check)", rejected)
        logger.info("Loaded %d proxies from %s", len(proxies), url)
        return cls(proxies)


def get_proxy_rotator() -> ProxyRotator:
    """
    Return the process-level ProxyRotator singleton.
    Initialises from env on first call (lazy, with lock for thread safety).
    """
    global _proxy_rotator
    if _proxy_rotator is None:
        with _init_lock:
            if _proxy_rotator is None:
                _proxy_rotator = ProxyRotator.from_env()
    return _proxy_rotator
