# Snippet: Sliding Window Rate Limiter (Redis)
# Category: Snippet | Language: Python (asyncio + Redis)
# Maturity: 🔴 Alpha | Extracted: 2026-03-27 from CAT project
#
# When to Use:
#   API endpoints where you need per-user/per-IP rate limiting distributed
#   across multiple API instances (Redis-backed = works with horizontal scaling).
#
# When NOT to Use:
#   - Single-instance apps (in-memory dict is simpler)
#   - Fixed window is acceptable (use Redis INCR + TTL instead — simpler)
#   - Token bucket needed (different semantics: burst allowance)
#
# Prerequisites: redis>=4.0 (asyncio support), Redis server
# Dependencies: redis[asyncio]

import time
import redis.asyncio as redis


async def is_rate_limited(
    cache: redis.Redis,
    key: str,
    limit: int,
    window_seconds: int,
) -> bool:
    """
    Sliding window rate limiter using Redis sorted sets.

    Stores request timestamps in a sorted set. On each request:
    1. Remove timestamps older than window
    2. Count remaining timestamps
    3. If count >= limit → rate limited
    4. Otherwise → add current timestamp, set TTL

    Args:
        cache:          Redis async client
        key:            Unique key per subject (e.g. f"rate:{user_id}:{endpoint}")
        limit:          Max requests allowed per window
        window_seconds: Window duration in seconds

    Returns:
        True if the caller is rate limited (request should be rejected).
        False if the request is allowed.
    """
    now = time.time()
    window_start = now - window_seconds

    pipe = cache.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)   # remove expired entries
    pipe.zcard(key)                                # count remaining
    pipe.zadd(key, {str(now): now})               # add current request
    pipe.expire(key, window_seconds + 1)          # clean up after window
    results = await pipe.execute()

    count_before_add = results[1]
    return count_before_add >= limit


# --- FastAPI middleware usage ---
#
# from fastapi import Request, HTTPException
# import redis.asyncio as aioredis
#
# redis_client = aioredis.from_url("redis://localhost:6379")
#
# @app.middleware("http")
# async def rate_limit_middleware(request: Request, call_next):
#     client_ip = request.client.host
#     endpoint = request.url.path
#
#     # Tighter limits for auth endpoints
#     if endpoint.startswith("/api/v1/auth"):
#         limit, window = 10, 60    # 10 req/min per IP
#     elif endpoint.endswith("/export"):
#         org_id = getattr(request.state, "org_id", client_ip)
#         client_ip = str(org_id)   # limit per org, not per IP
#         limit, window = 5, 60     # 5 req/min per org
#     else:
#         limit, window = 100, 60   # 100 req/min per IP
#
#     key = f"rate:{client_ip}:{endpoint}"
#     if await is_rate_limited(redis_client, key, limit, window):
#         raise HTTPException(status_code=429, detail="Too many requests")
#
#     return await call_next(request)
