# Pseudocode — API Public Endpoints

> **Feature:** api-public-endpoints | **Phase:** SPARC Pseudocode | **Date:** 2026-04-04

---

## Data Structures

### APIKey (DB model)
```
type APIKey = {
    id:           UUID
    org_id:       UUID
    name:         str (max 255)
    key_prefix:   str (8 chars, for display)
    key_hash:     str (64 chars, SHA-256 hex)
    created_by:   UUID (user.id)
    expires_at:   datetime | None
    last_used_at: datetime | None
    revoked:      bool
    created_at:   datetime
}
```

### APIKeyCreateRequest (Pydantic)
```
type APIKeyCreateRequest = {
    name:       str (1..255)
    expires_at: datetime | None = None
}
```

### APIKeyCreateResponse (Pydantic)
```
type APIKeyCreateResponse = {
    id:         UUID
    name:       str
    key:        str          # full key — shown ONCE, never stored
    key_prefix: str
    expires_at: datetime | None
    created_at: datetime
}
```

### APIKeyListItem (Pydantic)
```
type APIKeyListItem = {
    id:           UUID
    name:         str
    key_prefix:   str
    expires_at:   datetime | None
    last_used_at: datetime | None
    revoked:      bool
    created_at:   datetime
}
```

### PublicSKUItem (Pydantic)
```
type PublicSKUItem = {
    sku_id:              UUID
    sku_name:            str
    external_id:         str | None
    brand_name:          str
    content_total:       float | None
    image_score:         float | None
    description_score:   float | None
    completeness_score:  float | None
    scored_at:           datetime | None
    platform_count:      int
}
```

---

## Core Algorithms

### Algorithm: API Key Generation

```
FUNCTION generate_api_key(env: "live" | "test" = "live") -> (full_key, prefix, hash):
    raw = secrets.token_urlsafe(30)        # 40-char url-safe random string
    full_key = f"cat_{env}_{raw}"          # e.g. "cat_live_xK9mN2..."
    prefix = raw[:8]                       # first 8 chars of raw portion
    key_hash = sha256(full_key.encode()).hexdigest()
    RETURN (full_key, prefix, key_hash)
```

---

### Algorithm: API Key Validation (dependency)

```
FUNCTION get_org_by_api_key(request: Request, db: AsyncSession, redis: Redis) -> Organization:

    # Step 1: extract header
    raw_key = request.headers.get("X-API-Key")
    IF raw_key is None:
        RAISE HTTP 401 "MISSING_API_KEY"

    # Step 2: validate format
    IF NOT (raw_key.startswith("cat_live_") OR raw_key.startswith("cat_test_")):
        RAISE HTTP 401 "INVALID_API_KEY"
    IF len(raw_key) < 48:
        RAISE HTTP 401 "INVALID_API_KEY"

    # Step 3: extract prefix (8 chars after "cat_live_" or "cat_test_")
    prefix = raw_key[9:17]   # chars 9..16 (after "cat_????_")

    # Step 4: rate limiting (before DB hit)
    rate_key = f"rate:apikey:{prefix}"
    now_ts = time.time()
    window_start = now_ts - 60

    pipe = redis.pipeline()
    pipe.zremrangebyscore(rate_key, 0, window_start)
    pipe.zcard(rate_key)
    pipe.zadd(rate_key, {str(now_ts): now_ts})
    pipe.expire(rate_key, 60)
    results = await pipe.execute()
    count = results[1]

    IF count >= 60:
        reset_at = int(window_start + 60)
        RAISE HTTP 429 "RATE_LIMIT_EXCEEDED"
            headers: {
                "Retry-After": str(reset_at - int(now_ts)),
                "X-RateLimit-Limit": "60",
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_at)
            }

    # Step 5: hash lookup
    key_hash = sha256(raw_key.encode()).hexdigest()
    api_key = await APIKeyRepository.get_by_hash(db, key_hash)

    IF api_key is None:
        RAISE HTTP 401 "INVALID_API_KEY"

    # Step 6: check revoked
    IF api_key.revoked:
        RAISE HTTP 401 "API_KEY_REVOKED"

    # Step 7: check expiry
    IF api_key.expires_at is not None AND api_key.expires_at < datetime.now(UTC):
        RAISE HTTP 401 "API_KEY_EXPIRED"

    # Step 8: update last_used_at (fire-and-forget, no await)
    asyncio.create_task(
        APIKeyRepository.update_last_used(db, api_key.id)
    )

    # Step 9: load and return org
    org = await OrgRepository.get_by_id(db, api_key.org_id)
    RETURN org
```

---

### Algorithm: Create API Key

```
FUNCTION create_api_key(
    request: APIKeyCreateRequest,
    current_user: User,          # from require_role("admin", "manager")
    db: AsyncSession
) -> APIKeyCreateResponse:

    full_key, prefix, key_hash = generate_api_key("live")

    api_key = APIKey(
        org_id     = current_user.org_id,
        name       = request.name,
        key_prefix = prefix,
        key_hash   = key_hash,
        created_by = current_user.id,
        expires_at = request.expires_at
    )

    await db.add(api_key)
    await db.commit()

    RETURN APIKeyCreateResponse(
        id         = api_key.id,
        name       = api_key.name,
        key        = full_key,      # ONLY TIME full key is returned
        key_prefix = prefix,
        expires_at = api_key.expires_at,
        created_at = api_key.created_at
    )
```

---

### Algorithm: Revoke API Key

```
FUNCTION revoke_api_key(key_id: UUID, current_user: User, db: AsyncSession) -> None:

    api_key = await APIKeyRepository.get_by_id_and_org(
        db, key_id, current_user.org_id
    )

    IF api_key is None:
        RAISE HTTP 404 "API_KEY_NOT_FOUND"
        # Note: same 404 for wrong-org keys — prevents enumeration

    api_key.revoked = True
    await db.commit()
    RETURN None  # 204
```

---

## API Contracts

### POST /api/v1/api-keys
```
Request:
    Headers: { Authorization: Bearer <jwt_access_token> }
    Body: { "name": "Power BI Integration", "expires_at": "2027-01-01T00:00:00Z" }

Response (201 Created):
    {
        "id": "uuid",
        "name": "Power BI Integration",
        "key": "cat_live_xK9mN2...",   ← only time this appears
        "key_prefix": "xK9mN2ab",
        "expires_at": "2027-01-01T00:00:00Z",
        "created_at": "2026-04-04T10:00:00Z"
    }

Response (403): { "detail": "INSUFFICIENT_PERMISSIONS" }
Response (422): validation errors
```

### GET /api/v1/api-keys
```
Request:
    Headers: { Authorization: Bearer <jwt_access_token> }

Response (200):
    {
        "items": [
            {
                "id": "uuid",
                "name": "Power BI Integration",
                "key_prefix": "xK9mN2ab",
                "expires_at": "2027-01-01T00:00:00Z",
                "last_used_at": "2026-04-03T08:15:00Z",
                "revoked": false,
                "created_at": "2026-04-01T10:00:00Z"
            }
        ],
        "total": 1
    }
```

### DELETE /api/v1/api-keys/{key_id}
```
Response (204): empty body
Response (404): { "detail": "API_KEY_NOT_FOUND" }
```

### GET /api/v1/public/skus
```
Request:
    Headers: { X-API-Key: cat_live_... }
    Query:   page=1, page_size=50, brand_id=<uuid>, from_date=ISO8601, to_date=ISO8601

Response (200):
    {
        "items": [
            {
                "sku_id": "uuid",
                "sku_name": "Product Name",
                "external_id": "WB-12345",
                "brand_name": "BrandX",
                "content_total": 82.5,
                "image_score": 91.0,
                "description_score": 78.0,
                "completeness_score": 79.0,
                "scored_at": "2026-04-03T22:00:00Z",
                "platform_count": 5
            }
        ],
        "total": 120,
        "page": 1,
        "page_size": 50
    }

Response (401): { "detail": "MISSING_API_KEY" | "INVALID_API_KEY" | "API_KEY_EXPIRED" | "API_KEY_REVOKED" }
Response (429): { "detail": "RATE_LIMIT_EXCEEDED" }
```

### GET /api/v1/public/alerts
```
Request:
    Headers: { X-API-Key: cat_live_... }
    Query:   days=30 (default), severity=critical|warning

Response (200):
    {
        "items": [
            {
                "alert_id": "uuid",
                "alert_type": "content_score_drop",
                "sku_id": "uuid",
                "sku_name": "Product Name",
                "platform_name": "Wildberries",
                "severity": "critical",
                "message": "Content score dropped below threshold",
                "triggered_at": "2026-04-03T14:22:00Z"
            }
        ],
        "total": 7
    }
```

---

## Error Handling Strategy

| Error | HTTP Status | Detail Code | When |
|-------|------------|-------------|------|
| Missing X-API-Key | 401 | MISSING_API_KEY | Header absent |
| Wrong format | 401 | INVALID_API_KEY | Not cat_live_/cat_test_ prefix |
| Not found in DB | 401 | INVALID_API_KEY | Hash lookup miss (same code — no enumeration) |
| Revoked | 401 | API_KEY_REVOKED | revoked=true |
| Expired | 401 | API_KEY_EXPIRED | expires_at < now |
| Rate limit | 429 | RATE_LIMIT_EXCEEDED | > 60 req/min |
| Key not found (management) | 404 | API_KEY_NOT_FOUND | Wrong org or missing |
| Insufficient role | 403 | INSUFFICIENT_PERMISSIONS | Viewer tries to create key |
