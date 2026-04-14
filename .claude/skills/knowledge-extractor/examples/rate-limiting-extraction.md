# Example: Rate Limiting Pattern Extraction

End-to-end example of extracting a rate limiting middleware from a project
into a reusable toolkit artifact.

---

## Source: auth-service project

### Original Code

```rust
// auth-service/src/middleware/rate_limit.rs
use crate::config::AuthConfig;
use crate::models::User;

pub struct RateLimiter {
    max_requests: u32,
    window_secs: u64,
    store: HashMap<UserId, Vec<Timestamp>>,
}

pub fn rate_limit(config: &AuthConfig) -> RateLimiter {
    RateLimiter::new(config.max_requests, config.window_secs)
}

impl RateLimiter {
    pub fn check(&mut self, user: &User) -> Result<(), RateLimitError> {
        let now = Utc::now();
        let window_start = now - Duration::seconds(self.window_secs as i64);

        let requests = self.store
            .entry(user.id)
            .or_default();

        // Remove expired entries
        requests.retain(|ts| *ts > window_start);

        if requests.len() >= self.max_requests as usize {
            return Err(RateLimitError::TooManyRequests {
                user_id: user.id,
                limit: self.max_requests,
                retry_after: self.window_secs,
            });
        }

        requests.push(now);
        Ok(())
    }
}
```

### TOOLKIT_HARVEST.md Marker (during work)

```markdown
## Patterns
- [ ] Rate limiting middleware — получился универсальнее чем обычно, см. src/middleware/rate_limit.rs
```

---

## Phase 1: Agent Review

**extractor-patterns** found:
```
- Name: Rate Limiting Middleware
- File: src/middleware/rate_limit.rs:1-35
- Description: Sliding window rate limiter with per-user tracking
- Reusability: HIGH
- Why reusable: Core algorithm is generic, only config is project-specific
```

## Phase 2: Classify

```
Category: Pattern (architectural approach, multiple implementations possible)
Secondary: Snippet (core algorithm is <50 lines)
Confidence: HIGH
Note: Needs decontextualization — currently tied to AuthConfig and User model
```

## Phase 3: Decontextualize

### Step 1: Remove project specifics

| Before | After |
|--------|-------|
| `AuthConfig` | `RateLimitConfig` trait |
| `User` / `UserId` | `SubjectId: String` |
| `crate::config` import | Standalone |
| `crate::models` import | Standalone |

### Step 2: Document usage

See final artifact below.

### Step 3: Version & provenance

```
Maturity: 🔴 Alpha
Used in: auth-service
Extracted: 2026-03-01
Version: v1.0
```

### Quality gate:

| Check | Status |
|-------|--------|
| No project-specific names | ✅ |
| No hardcoded paths | ✅ |
| "When to use" present | ✅ |
| "When NOT to use" present | ✅ |
| Prerequisites documented | ✅ |
| At least 1 variant | ✅ (Redis) |
| Code compiles standalone | ✅ |
| Maturity assigned | ✅ |

## Phase 4: Integrate

### Final Artifact: `patterns/rate-limiting.md`

```markdown
# Pattern: Rate Limiting

## Maturity: 🔴 Alpha
## Used in: auth-service
## Extracted: 2026-03-01
## Last updated: 2026-03-01
## Version: v1.0

## When to Use

- Any HTTP API exposed to external clients
- Services with expensive operations that need throttling
- Multi-tenant systems with per-tenant quotas
- APIs that call rate-limited external services

## When NOT to Use

- Internal service-to-service calls (use circuit breaker instead)
- Read-only cache endpoints (overhead not worth it)
- WebSocket connections (use connection-level limits instead)

## Prerequisites

- A way to identify the request subject (user ID, API key, IP)
- Storage for request counts (in-memory or distributed)
- Configurable limits (per-subject or global)

## Implementation

### Core Algorithm: Sliding Window

```rust
pub trait RateLimitConfig {
    fn max_requests(&self) -> u32;
    fn window_duration(&self) -> Duration;
}

pub struct SlidingWindowLimiter<K: Hash + Eq> {
    config: Box<dyn RateLimitConfig>,
    windows: HashMap<K, Vec<Instant>>,
}

impl<K: Hash + Eq> SlidingWindowLimiter<K> {
    pub fn check(&mut self, subject: &K) -> Result<(), RateLimitError> {
        let now = Instant::now();
        let window_start = now - self.config.window_duration();

        let requests = self.windows.entry(subject.clone()).or_default();
        requests.retain(|ts| *ts > window_start);

        if requests.len() >= self.config.max_requests() as usize {
            return Err(RateLimitError::Exceeded {
                limit: self.config.max_requests(),
                retry_after: self.config.window_duration(),
            });
        }

        requests.push(now);
        Ok(())
    }
}
```

## Variants

### Variant A: In-Memory (single instance)

Use the implementation above. Good for:
- Single-server deployments
- Development environments
- Low-traffic services

Trade-off: Resets on restart, doesn't share across instances.

### Variant B: Redis-backed (distributed)

```python
import redis
import time

class RedisRateLimiter:
    def __init__(self, redis_client, max_requests, window_seconds):
        self.redis = redis_client
        self.max_requests = max_requests
        self.window = window_seconds

    def check(self, subject_id: str) -> bool:
        key = f"ratelimit:{subject_id}"
        now = time.time()
        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(key, 0, now - self.window)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, self.window)
        _, _, count, _ = pipe.execute()
        return count <= self.max_requests
```

Good for: distributed systems, multi-instance deployments.

### Variant C: Token Bucket

Better for bursty traffic patterns. Allows short bursts while
maintaining average rate.

## Gotchas

- In-memory variant resets on restart — clients may see sudden burst of allowed requests
- Redis variant needs MULTI/EXEC for atomicity
- Don't forget to set TTL on Redis keys to prevent memory leak
- Consider returning `Retry-After` header with the rate limit response

## Related Artifacts

- Circuit Breaker pattern — complementary, for downstream protection
- Rule: "Sequential API calls for rate-limited services" — client-side rate limiting

## Changelog
- v1.0: Initial extraction from auth-service project
```

---

## Harvest Report Entry

```
| 1 | Rate Limiting | Pattern | 🔴 Alpha | v1.0 | patterns/rate-limiting.md |
```

## Key Takeaways

1. Original code: 35 lines, tightly coupled to AuthConfig + User
2. Extracted artifact: 100+ lines of docs, 3 variants, standalone
3. The PRINCIPLE (sliding window rate limiting) is universal
4. The IMPLEMENTATION needed generics/traits to decontextualize
5. Adding Redis variant immediately increased value
