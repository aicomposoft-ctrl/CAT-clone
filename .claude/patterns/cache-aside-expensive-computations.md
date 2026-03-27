# Pattern: Cache-Aside for Expensive Computations (Redis)

## Maturity: 🔴 Alpha
## Used in: CAT (Commerce Analytics Tool) — ML embedding caching
## Extracted: 2026-03-27
## Last updated: 2026-03-27
## Version: v1.0

## When to Use

When computations are:
- Deterministic (same input → same output)
- Expensive (>100ms: ML inference, external API calls, complex aggregations)
- Repeated with the same inputs (embeddings for same content, report generation)

Examples: ML model embeddings, compiled reports, external API geocoding, rendered templates.

## When NOT to Use

- Non-deterministic results (real-time prices, live inventory)
- Single-use computations unlikely to repeat
- Results that MUST be fresh on every request (auth tokens, security checks)
- When cache invalidation is complex and error-prone

## Prerequisites

- Redis (or any key-value cache with TTL support)
- Serializable computation inputs (to form a cache key)
- Serializable outputs (to store in cache)

## Implementation

```python
import hashlib
import json
import redis.asyncio as redis
from typing import Callable, Any

async def cache_aside(
    cache: redis.Redis,
    key: str,
    compute_fn: Callable[[], Any],
    ttl_seconds: int = 86400,  # 24 hours
    serializer=json,
) -> Any:
    """
    Cache-aside pattern: check cache → compute if missing → store → return.

    Args:
        cache: Redis client instance
        key: Cache key (must be unique per input combination)
        compute_fn: Async callable that produces the value if cache miss
        ttl_seconds: Cache expiry in seconds (default: 24h)
        serializer: Module with .dumps() and .loads() (default: json)
    """
    cached = await cache.get(key)
    if cached:
        return serializer.loads(cached)

    value = await compute_fn()
    await cache.setex(key, ttl_seconds, serializer.dumps(value))
    return value


# --- Usage: ML embedding caching ---
def make_embedding_key(org_id: str, content_hash: str, model: str) -> str:
    return f"embed:{org_id}:{content_hash}:{model}"

async def get_embedding(
    text: str,
    org_id: str,
    model_name: str,
    cache: redis.Redis,
    model,
) -> list[float]:
    content_hash = hashlib.md5(text.encode()).hexdigest()
    key = make_embedding_key(org_id, content_hash, model_name)

    return await cache_aside(
        cache=cache,
        key=key,
        compute_fn=lambda: model.encode(text).tolist(),
        ttl_seconds=86400,  # embeddings stable for 24h
    )
```

### Cache Key Design Conventions

```python
# Pattern: {namespace}:{tenant_id}:{content_hash}:{variant}
# Examples:
"embed:{org_id}:{sha256_of_text}:{model_name}"
"report:{org_id}:{date}:{report_type}"
"geocode:{sha256_of_address}:v1"
```

## Variants

### Variant A: NumPy arrays (binary serialization)

```python
import numpy as np
import pickle

async def cache_aside_numpy(cache, key, compute_fn, ttl=86400):
    cached = await cache.get(key)
    if cached:
        return np.frombuffer(cached, dtype=np.float32)
    value = await compute_fn()
    await cache.setex(key, ttl, value.astype(np.float32).tobytes())
    return value
```

### Variant B: Invalidation on update

```python
# Pattern: invalidate all keys for a tenant when source data changes
async def invalidate_org_embeddings(cache: redis.Redis, org_id: str):
    pattern = f"embed:{org_id}:*"
    async for key in cache.scan_iter(pattern):
        await cache.delete(key)
```

### Variant C: Stampede protection (locking)

```python
import asyncio

_locks: dict[str, asyncio.Lock] = {}

async def cache_aside_safe(cache, key, compute_fn, ttl=86400):
    """Prevents thundering herd: only one coroutine computes per key."""
    if key not in _locks:
        _locks[key] = asyncio.Lock()
    async with _locks[key]:
        cached = await cache.get(key)
        if cached:
            return json.loads(cached)
        value = await compute_fn()
        await cache.setex(key, ttl, json.dumps(value))
        return value
```

## Gotchas

- **TTL too short → cache thrashing**: Expensive computations run constantly. Set TTL based on how often the underlying data changes.
- **TTL too long → stale data**: If source content changes, cached embeddings become incorrect. Trigger invalidation on content update events.
- **Cache key collisions**: Always namespace by tenant (org_id) to prevent cross-tenant cache sharing.
- **Missing null caching**: If compute_fn returns None/empty, you may want to cache that too (negative caching) to avoid repeated expensive misses.

## Related Artifacts

- `snippets/startup-secrets-validation.py` — Redis URL must be validated at startup
- `patterns/multi-tenant-saas-isolation.md` — always namespace cache keys by org_id

## Changelog
- v1.0: Initial extraction from CAT project embedding cache (2026-03-27)
