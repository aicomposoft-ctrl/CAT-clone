# Architecture — API Public Endpoints

> **Feature:** api-public-endpoints | **Phase:** SPARC Architecture | **Date:** 2026-04-04

---

## 1. Component Overview

```
services/api/app/
├── api_keys/               # NEW — API key management domain
│   ├── __init__.py
│   ├── models.py           # APIKey ORM model
│   ├── schemas.py          # Request/Response schemas
│   ├── repository.py       # DB queries (always org_id scoped)
│   ├── service.py          # Key generation, validation, revocation
│   └── router.py           # POST/GET/DELETE /api/v1/api-keys
├── public/                 # NEW — External integration endpoints
│   ├── __init__.py
│   ├── router.py           # GET /api/v1/public/* (registered in main.py)
│   └── schemas.py          # Public-facing response schemas (simplified)
└── core/
    └── deps.py             # UPDATED — add get_org_by_api_key dependency
```

---

## 2. Database Schema

### Table: `api_keys`

```sql
CREATE TABLE api_keys (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name        VARCHAR(255) NOT NULL,
    key_prefix  VARCHAR(16) NOT NULL,          -- first 8 chars of raw key (display only)
    key_hash    VARCHAR(64) NOT NULL UNIQUE,   -- SHA-256 hex digest of full key
    created_by  UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    expires_at  TIMESTAMP WITH TIME ZONE,      -- NULL = never expires
    last_used_at TIMESTAMP WITH TIME ZONE,     -- updated on each successful auth
    revoked     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_api_keys_org_id ON api_keys(org_id);
CREATE INDEX idx_api_keys_key_hash ON api_keys(key_hash);  -- fast lookup on auth
CREATE INDEX idx_api_keys_key_prefix ON api_keys(key_prefix);
```

---

## 3. Authentication Flow

```
Client Request (X-API-Key: cat_live_Abc123...)
        │
        ▼
┌───────────────────────────────────────────────────┐
│  get_org_by_api_key dependency (core/deps.py)     │
│                                                   │
│  1. Extract X-API-Key header → 401 if missing     │
│  2. Validate format: must start with "cat_live_"  │
│     or "cat_test_" → 401 INVALID_API_KEY          │
│  3. Extract prefix = key[:8]                      │
│  4. Check Redis cache: rate:{prefix} counter      │
│     → 429 if exceeded (before DB hit)             │
│  5. Compute SHA-256(key) → look up in api_keys    │
│     → 401 INVALID_API_KEY if not found            │
│  6. Check revoked=TRUE → 401 API_KEY_REVOKED      │
│  7. Check expires_at < now → 401 API_KEY_EXPIRED  │
│  8. Increment Redis rate counter (sliding window) │
│  9. Update last_used_at async (fire-and-forget)   │
│ 10. Return Organization object (with org_id)      │
└───────────────────────────────────────────────────┘
        │
        ▼
  Route Handler (has org: Organization)
  → All DB queries filter by org.id
```

---

## 4. Rate Limiting Design

**Algorithm:** Sliding window using Redis sorted sets (same pattern as existing rate limiter)

```
Key:   rate:apikey:{key_prefix}
Value: sorted set of timestamps (score = timestamp)
TTL:   60 seconds

On each request:
  1. ZREMRANGEBYSCORE key 0 (now - 60s)    # remove old entries
  2. count = ZCARD key                      # current request count
  3. if count >= 60: return 429
  4. ZADD key now now                       # add current timestamp
  5. EXPIRE key 60                          # reset TTL
```

**Response headers on 429:**
```
HTTP/1.1 429 Too Many Requests
Retry-After: 15
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1712160000
```

---

## 5. Public Endpoints Routing

```
/api/v1/public/                              ← registered in main.py
    GET  /skus                               ← paginated, filters: brand_id, from_date, to_date
    GET  /skus/{sku_id}/content-score        ← single SKU detailed score
    GET  /stock                              ← filters: sku_id, platform_id
    GET  /prices                             ← filters: sku_id, platform_id
    GET  /reviews/summary                    ← filters: brand_id, platform_id
    GET  /alerts                             ← filters: days (default 30), severity
```

All endpoints use `Depends(get_org_by_api_key)` — returns `Organization` (not `User`).
All DB queries scope to `org.id`.

---

## 6. API Key Management Routing

```
/api/v1/api-keys/                            ← registered in main.py
    POST   /                                 ← admin/manager only
    GET    /                                 ← admin/manager only
    DELETE /{key_id}                         ← admin/manager only
```

These endpoints use `Depends(require_role("admin", "manager"))` (existing JWT auth).

---

## 7. Key Generation Algorithm

```python
import secrets, hashlib

def generate_api_key(env: str = "live") -> tuple[str, str, str]:
    """
    Returns: (full_key, key_prefix, key_hash)
    
    full_key:   cat_live_<40 random url-safe chars>  — shown once to user
    key_prefix: first 8 chars after "cat_live_"      — stored for display
    key_hash:   SHA-256 hex of full_key              — stored in DB
    """
    raw = secrets.token_urlsafe(30)           # 40-char url-safe string
    full_key = f"cat_{env}_{raw}"
    key_prefix = raw[:8]
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    return full_key, key_prefix, key_hash
```

---

## 8. Data Flow: Public SKU Endpoint

```
GET /api/v1/public/skus?page=1&page_size=50&brand_id=<uuid>
     │
     ├─ get_org_by_api_key → Organization(id=org_id)
     │
     ├─ public_router.get_skus(org, page, page_size, brand_id)
     │
     └─ PublicService.list_skus_with_scores(db, org_id, ...)
         │
         ├─ JOIN skus + brands + content_scores (latest per sku)
         ├─ WHERE skus.org_id = org_id
         ├─ WHERE brand_id = brand_id (if filter provided)
         ├─ ORDER BY skus.created_at DESC
         └─ LIMIT page_size OFFSET (page-1)*page_size
```

Public endpoints reuse existing repositories from content, stock, prices, reviews, alerts domains. No new DB queries — only new routing layer with API key auth.

---

## 9. Integration with Existing Infrastructure

| Concern | Approach |
|---------|----------|
| Multi-tenant isolation | `org_id` derived from API key → never from client request |
| Logging | API key masked: `cat_live_Abc*****` in all log lines |
| Existing repos | Public router delegates to existing `ContentRepository`, `StockRepository`, etc. |
| Redis | Rate limiting uses same Redis instance as existing Celery broker |
| Alembic | One migration: add `api_keys` table |
| Nginx | No changes — traffic goes through existing `/api/v1/` route |

---

## 10. Security Boundaries

```
┌─────────────────────────────────────────────────────┐
│  PUBLIC API (api key zone)                          │
│  /api/v1/public/*   → read-only, org-scoped         │
│  /api/v1/api-keys/* → JWT+RBAC (admin/manager)      │
├─────────────────────────────────────────────────────┤
│  INTERNAL API (JWT zone)                            │
│  /api/v1/content/*, /api/v1/stock/*, etc.           │
│  → JWT access token, RBAC roles                     │
└─────────────────────────────────────────────────────┘
```

Key isolation guarantees:
- API key resolves to `org_id` only — no user context, no role elevation
- `last_used_at` update is fire-and-forget (non-blocking)
- Full key never logged, never returned after creation
