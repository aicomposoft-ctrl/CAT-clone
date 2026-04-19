"""Lazy Redis client for Celery tasks (ScraperRouter L3 / AgentScraper)."""

from __future__ import annotations

import os

import redis

_client: redis.Redis | None = None


def get_redis_client() -> redis.Redis:
    """Singleton sync Redis client from REDIS_URL (same broker as Celery)."""
    global _client
    if _client is None:
        url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
        _client = redis.from_url(url, decode_responses=False)
    return _client
