# Refinement — API Public Endpoints

> **Feature:** api-public-endpoints | **Phase:** SPARC Refinement | **Date:** 2026-04-04

---

## Edge Cases Matrix

| Scenario | Input | Expected | Handling |
|----------|-------|----------|----------|
| Key used exactly at expiry second | expires_at = now() | 401 API_KEY_EXPIRED | `<=` comparison in service |
| Concurrent 60th and 61st request | Two requests at same ms | One gets 429, one gets 200 | Redis pipeline is atomic per ZADD |
| Key deleted from DB while cached | Hash deleted mid-request | 401 INVALID_API_KEY | No Redis key caching — always DB lookup |
| last_used_at update fails | DB unavailable at update | Request succeeds anyway | Fire-and-forget, never blocks response |
| Org deleted, API key still valid | Organization cascade delete | 401 INVALID_API_KEY | FK ON DELETE CASCADE removes key |
| Very old key with NULL expires_at | expires_at=None | Valid forever | None check before comparison |
| Key prefix collision (8 chars) | Two keys with same prefix | Both work | Lookup is on key_hash (unique), prefix is display only |
| Malformed UUID in brand_id filter | brand_id=not-a-uuid | 422 Unprocessable Entity | Pydantic UUID validation |
| page_size=0 or negative | page_size=-1 | 422 | Pydantic ge=1 validator |
| page_size=10001 | page_size=10001 | 422 | Pydantic le=500 validator |
| from_date > to_date | Invalid range | 422 with detail | Manual validator in schema |
| SKU with no content score yet | content_total=null | Included with null scores | LEFT JOIN in query |
| All SKUs have no scores | Empty score join | All nulls returned, not filtered | LEFT JOIN not INNER JOIN |

---

## Testing Strategy

### Unit Tests (`services/api/tests/unit/`)

```python
# test_api_key_service.py

def test_generate_api_key_format():
    full_key, prefix, hash_ = generate_api_key("live")
    assert full_key.startswith("cat_live_")
    assert len(prefix) == 8
    assert len(hash_) == 64  # SHA-256 hex

def test_generate_api_key_uniqueness():
    keys = {generate_api_key("live")[0] for _ in range(100)}
    assert len(keys) == 100

def test_generate_api_key_hash_is_deterministic():
    full_key, _, hash1 = generate_api_key("live")
    hash2 = hashlib.sha256(full_key.encode()).hexdigest()
    assert hash1 == hash2
```

### Integration Tests (`services/api/tests/integration/`)

```python
# test_api_key_repository.py

async def test_get_by_hash_returns_matching_key(db_session):
    key = await create_test_api_key(db_session, org_id=ORG_A_ID)
    found = await APIKeyRepository.get_by_hash(db_session, key.key_hash)
    assert found.id == key.id

async def test_get_by_hash_cross_org_isolation(db_session):
    # Key belongs to org_a
    key_a = await create_test_api_key(db_session, org_id=ORG_A_ID)
    # Lookup by hash works, but org_id is from the key itself
    found = await APIKeyRepository.get_by_hash(db_session, key_a.key_hash)
    assert found.org_id == ORG_A_ID  # tenant isolation via key itself

async def test_revoked_key_blocks_auth(db_session, redis_client):
    key = await create_test_api_key(db_session, revoked=True)
    with pytest.raises(HTTPException) as exc:
        await get_org_by_api_key_with_key(key.full_key, db_session, redis_client)
    assert exc.value.status_code == 401
    assert exc.value.detail == "API_KEY_REVOKED"

async def test_expired_key_blocks_auth(db_session, redis_client):
    expires = datetime.now(UTC) - timedelta(hours=1)
    key = await create_test_api_key(db_session, expires_at=expires)
    with pytest.raises(HTTPException) as exc:
        await get_org_by_api_key_with_key(key.full_key, db_session, redis_client)
    assert exc.value.status_code == 401
    assert exc.value.detail == "API_KEY_EXPIRED"
```

### E2E Tests (`services/api/tests/e2e/`)

```python
# test_public_api.py

async def test_create_api_key_as_admin(async_client, admin_headers):
    resp = await async_client.post(
        "/api/v1/api-keys",
        json={"name": "Test Key"},
        headers=admin_headers
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["key"].startswith("cat_live_")
    assert "key_prefix" in data
    assert "key" in data  # full key present only at creation

async def test_create_api_key_as_viewer_fails(async_client, viewer_headers):
    resp = await async_client.post(
        "/api/v1/api-keys",
        json={"name": "Test Key"},
        headers=viewer_headers
    )
    assert resp.status_code == 403

async def test_public_skus_with_valid_key(async_client, api_key_for_org_a):
    resp = await async_client.get(
        "/api/v1/public/skus",
        headers={"X-API-Key": api_key_for_org_a}
    )
    assert resp.status_code == 200
    assert "items" in resp.json()

async def test_public_skus_cross_org_isolation(async_client, api_key_for_org_a, sku_org_b):
    resp = await async_client.get(
        "/api/v1/public/skus",
        headers={"X-API-Key": api_key_for_org_a}
    )
    sku_ids = [item["sku_id"] for item in resp.json()["items"]]
    assert str(sku_org_b.id) not in sku_ids

async def test_rate_limiting_enforced(async_client, api_key_for_org_a):
    for _ in range(60):
        resp = await async_client.get(
            "/api/v1/public/skus",
            headers={"X-API-Key": api_key_for_org_a}
        )
        assert resp.status_code == 200
    # 61st request
    resp = await async_client.get(
        "/api/v1/public/skus",
        headers={"X-API-Key": api_key_for_org_a}
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers

async def test_missing_api_key_header(async_client):
    resp = await async_client.get("/api/v1/public/skus")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "MISSING_API_KEY"

async def test_revoked_key_returns_401(async_client, admin_headers, async_client_db):
    # Create key
    create_resp = await async_client.post(
        "/api/v1/api-keys", json={"name": "k"}, headers=admin_headers
    )
    key_id = create_resp.json()["id"]
    full_key = create_resp.json()["key"]

    # Revoke it
    await async_client.delete(f"/api/v1/api-keys/{key_id}", headers=admin_headers)

    # Use it
    resp = await async_client.get(
        "/api/v1/public/skus",
        headers={"X-API-Key": full_key}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "API_KEY_REVOKED"
```

---

## Security Hardening

### Key masking in logs
```python
# In logging middleware / API key dependency
masked = raw_key[:9] + raw_key[9:17] + "****"
# e.g. "cat_live_xK9mN2ab****"
logger.info("API key auth: %s from %s", masked, request.client.host)
```

### Prevent timing attacks on key comparison
```python
# Use hashlib (constant-time comparison not needed since we compare hashes, 
# not raw keys — but hash lookup must handle "not found" without leaking timing)
# Always compute hash before DB lookup — never short-circuit on format alone
```

### Key log in audit table (future)
```python
# api_key_audit_log: key_id, action(created/revoked/used), ip, user_agent, timestamp
# Not in MVP but stub the model
```

---

## Performance Optimizations

| Optimization | Rationale |
|-------------|-----------|
| Index on `api_keys.key_hash` | O(1) lookup per request instead of full scan |
| Redis rate check before DB hit | Prevents DB load from burst traffic |
| `last_used_at` update is fire-and-forget | Removes DB write from critical path |
| Public endpoints reuse existing repos | No duplicated queries, leverages existing query optimization |
| `page_size` max = 500 | Prevents accidentally pulling full dataset in one request |

---

## Technical Debt

| Item | Priority | Notes |
|------|----------|-------|
| API key scopes (read:skus, read:prices) | Medium | MVP gives full read access |
| Per-endpoint rate limits | Medium | Global 60/min is adequate for MVP |
| Key rotation (generate new without deleting old) | Low | Users can create new + delete old manually |
| Audit log table for key usage | Medium | Compliance teams will eventually need this |
