"""
Celery application for CAT collector service.

Broker: Redis (REDIS_URL env var)
Worker pool: prefork ONLY — gevent/eventlet are incompatible with asyncio.run().

worker_process_init signal pre-loads the proxy rotator once per worker process
to avoid blocking HTTP calls inside task bodies.
"""

from __future__ import annotations

import os

from celery import Celery
from celery.signals import worker_process_init

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

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
