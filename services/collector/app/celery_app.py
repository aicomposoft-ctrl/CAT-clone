"""
Celery application for CAT collector service.

Broker: Redis (REDIS_URL env var)
Worker pool: prefork ONLY — gevent/eventlet are incompatible with asyncio.run().

worker_process_init signal pre-loads the proxy rotator once per worker process
to avoid blocking HTTP calls inside task bodies.
"""

from __future__ import annotations

import logging
import os
import sys

from celery import Celery
from celery.signals import worker_process_init

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

# Fail fast if secrets required for L0 scraping are missing.
# PLATFORM_SECRET_KEYS is only mandatory when encrypted tokens exist in DB,
# but we validate early so misconfiguration is caught at startup, not mid-task.
_REQUIRED_SECRETS = ["POSTGRES_URL", "REDIS_URL"]
_OPTIONAL_SECRETS_WITH_FEATURES = {
    "PLATFORM_SECRET_KEYS": "L0 Seller API token encryption",
    "ANTHROPIC_API_KEY": "L3 AgentScraper Claude API",
}


def _validate_secrets() -> None:
    missing = [k for k in _REQUIRED_SECRETS if not os.environ.get(k)]
    if missing:
        logger.critical("Collector startup: missing required secrets: %s", missing)
        sys.exit(1)
    for key, feature in _OPTIONAL_SECRETS_WITH_FEATURES.items():
        if not os.environ.get(key):
            logger.warning(
                "Collector startup: %s not set — %s will be unavailable", key, feature
            )


_validate_secrets()

# When PLAYWRIGHT_WORKER=1 the BrowserPool signals must be registered before
# any tasks run.  Importing browser_pool here wires worker_init / worker_shutdown
# at module load time — safe in solo pool, must NOT run in forking prefork workers.
if os.environ.get("PLAYWRIGHT_WORKER") == "1":
    from app.core import browser_pool  # noqa: F401 — side-effect import (signal wiring)

celery_app = Celery(
    "cat_collector",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "app.tasks.wb_content_task",
        "app.tasks.wb_price_task",
        "app.tasks.wb_stock_task",
        "app.tasks.wb_reviews_task",
        "app.tasks.wb_orchestrator",
        "app.tasks.ozon_content_task",
        "app.tasks.ozon_price_task",
        "app.tasks.ozon_stock_task",
        "app.tasks.ozon_reviews_task",
        "app.tasks.ozon_orchestrator",
        "app.tasks.samocat_content_task",
        "app.tasks.samocat_price_task",
        "app.tasks.samocat_stock_task",
        "app.tasks.samocat_reviews_task",
        "app.tasks.samocat_orchestrator",
        "app.tasks.lenta_content_task",
        "app.tasks.lenta_price_task",
        "app.tasks.lenta_stock_task",
        "app.tasks.lenta_reviews_task",
        "app.tasks.lenta_orchestrator",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    # Route Ozon tasks to the playwright queue — Ozon L1 (httpx) is blocked by
    # anti-bot (403), so these must run in collector-playwright (BrowserPool
    # available for L2 fallback).  All other tasks use the default queue.
    task_routes={
        "ozon.*": {"queue": "playwright"},
    },
)


@worker_process_init.connect
def init_worker_process(**kwargs) -> None:
    """
    Pre-load proxy list once per worker process at startup.
    Avoids blocking HTTP call inside every task body.
    """
    from app.core.proxy import get_proxy_rotator
    rotator = get_proxy_rotator()
    import logging
    logging.getLogger(__name__).info(
        "Worker process initialised with %d proxies", len(rotator)
    )
