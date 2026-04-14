# Refinement — Multi-Client Support

> **Feature:** multi-client-support | **Phase:** SPARC Refinement | **Date:** 2026-04-04

---

## Edge Cases Matrix

| Scenario | Input | Expected | Handling |
|----------|-------|----------|----------|
| Switch to client in different org | client_id from org_b | 403 CLIENT_NOT_IN_ORG | DB lookup includes org_id filter |
| Switch to deactivated client | client_id where is_active=false | 403 CLIENT_NOT_IN_ORG | Same 403 (not 404) — prevents enumeration |
| JWT with deleted client_id | Client deleted after token issued | 401 INVALID_CLIENT_CONTEXT | Re-validation on every request |
| Brand assigned to deactivated client | client_id is_active=false | Brand hidden in client mode | Client filter excludes inactive |
| Unassigned brand in client context | brand.client_id = NULL | Brand not visible | Only client-assigned brands show |
| Org with 0 clients | Empty clients table | All-clients mode works normally | client_id=None path unchanged |
| Slug with uppercase | slug: "Nestle-RU" | 422 validation error | Regex: ^[a-z0-9-]+$ |
| Delete client with brands | brands.client_id = client_id | Client deactivated, brands.client_id stays | SET NULL not triggered — soft delete |
| Concurrent brand assignment | Two requests update brand.client_id | Last write wins | Optimistic, no conflict expected |
| Report with deactivated client JWT | token has client_id of inactive | 401 on next request | Re-validated per request |

---

## Testing Strategy

### Unit Tests

```python
# test_client_service.py
def test_create_client_validates_slug_format():
    # slug with uppercase → ValidationError
    with pytest.raises(ValidationError):
        ClientCreateRequest(name="X", slug="Nestle-RU")  # uppercase not allowed

def test_switch_client_issues_new_token_with_claim():
    # Verify the new token contains client_id
    token = create_access_token(user_id, org_id, role="admin", client_id=CLIENT_ID)
    payload = decode_token(token, expected_type="access")
    assert payload["client_id"] == str(CLIENT_ID)

def test_switch_to_null_removes_client_claim():
    token = create_access_token(user_id, org_id, role="admin", client_id=None)
    payload = decode_token(token, expected_type="access")
    assert "client_id" not in payload
```

### Integration Tests

```python
# test_client_repository.py
async def test_get_by_slug_and_org_cross_org_isolation(db_session):
    client_a = await create_test_client(db_session, org_id=ORG_A_ID, slug="nestle")
    # Same slug, different org — should not conflict
    found = await ClientRepository.get_by_slug_and_org(db_session, "nestle", ORG_B_ID)
    assert found is None

async def test_brand_client_filter_excludes_other_clients(db_session):
    # Create two clients, assign brands to each
    brand_a = await create_test_brand(db_session, org_id=ORG_A_ID, client_id=CLIENT_A_ID)
    brand_b = await create_test_brand(db_session, org_id=ORG_A_ID, client_id=CLIENT_B_ID)

    # Query with client_a context → only brand_a returned
    ctx = AuthContext(user=..., org_id=ORG_A_ID, client_id=CLIENT_A_ID)
    brands = await BrandRepository.list_by_org(db_session, ctx)
    assert brand_b.id not in [b.id for b in brands]

async def test_deactivated_client_excluded_from_switch(db_session):
    inactive = await create_test_client(db_session, is_active=False)
    found = await ClientRepository.get_active_by_id_and_org(
        db_session, inactive.id, inactive.org_id
    )
    assert found is None
```

### E2E Tests

```python
# test_multi_client_api.py
async def test_create_client_as_admin(client, admin_headers):
    resp = await client.post("/api/v1/clients/", json={
        "name": "Nestle RU", "slug": "nestle-ru"
    }, headers=admin_headers)
    assert resp.status_code == 201
    assert resp.json()["slug"] == "nestle-ru"

async def test_slug_conflict_returns_409(client, admin_headers, existing_client):
    resp = await client.post("/api/v1/clients/", json={
        "name": "Other", "slug": existing_client.slug
    }, headers=admin_headers)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "SLUG_CONFLICT"

async def test_switch_client_returns_new_token(client, auth_headers, org_client):
    resp = await client.post("/api/v1/auth/switch-client",
        json={"client_id": str(org_client.id)},
        headers=auth_headers
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()

async def test_switch_to_foreign_client_returns_403(client, auth_headers, foreign_client):
    resp = await client.post("/api/v1/auth/switch-client",
        json={"client_id": str(foreign_client.id)},
        headers=auth_headers
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "CLIENT_NOT_IN_ORG"

async def test_skus_filtered_by_client_context(client, client_a_headers, sku_client_b):
    # Authenticated with client_a token — sku_client_b must not appear
    resp = await client.get("/api/v1/skus", headers=client_a_headers)
    sku_ids = [s["id"] for s in resp.json()["items"]]
    assert str(sku_client_b.id) not in sku_ids

async def test_cross_client_isolation(client, client_a_headers, sku_client_b):
    # Critical: must be explicit test per testing.md multi-tenant rule
    resp = await client.get(f"/api/v1/skus/{sku_client_b.id}", headers=client_a_headers)
    assert resp.status_code == 404  # not 403 — prevents enumeration
```

---

## Security Hardening

### client_id claim validation
Every request with a JWT must re-validate `client_id` against the DB to catch:
- Deactivated clients (token issued before deactivation)
- Deleted clients (CASCADE may clean up)
- Organization change (unlikely but defensive)

Performance impact: one extra DB query per request when client_id is set.
Mitigation: cache active client IDs in Redis with 60s TTL (future optimization).

### Slug injection prevention
```python
slug: str = Field(pattern=r"^[a-z0-9-]+$", min_length=1, max_length=100)
# Prevents: "../admin", "client;DROP TABLE", etc.
```

---

## Performance

| Operation | Overhead | Notes |
|-----------|----------|-------|
| Client context validation | +1 DB query/request | Cache in Redis for 60s (deferred) |
| Brand list with client filter | +0 (added WHERE clause) | Uses idx_brands_client_id |
| SKU list via brand JOIN | +0 (JOIN already exists) | No new JOINs needed |
| Client list | O(1) per org | idx_clients_org_id covers it |
| Report generation | +1 JOIN for client name | Acceptable |

---

## Technical Debt

| Item | Priority | Notes |
|------|----------|-------|
| Redis cache for client_id validation | Medium | 1 DB query/request is acceptable for MVP |
| Per-client user permissions | Medium | Phase 2 — assign users to specific clients |
| Client logo upload to MinIO | Low | Placeholder URL field exists, upload TBD |
| Cross-client analytics | Low | Phase 2 feature |
