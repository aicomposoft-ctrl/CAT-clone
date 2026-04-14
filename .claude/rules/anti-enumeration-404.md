# Anti-Enumeration: Return 404 Not 403 for Cross-Tenant Resources

**Category:** Rule
**Maturity:** 🔴 Alpha
**Type:** Security Constraint
**Scope:** Universal (any multi-tenant web API)
**Source:** CAT (api_keys/service.py), 2026-04-05

---

## Rule

**Return HTTP 404 (Not Found), not HTTP 403 (Forbidden), when a resource exists
but belongs to a different tenant/organization.**

```python
# WRONG — reveals that the resource exists (403 = "it exists, but not yours")
if resource.org_id != current_user.org_id:
    raise HTTPException(status_code=403, detail="FORBIDDEN")

# CORRECT — treats wrong-org same as not-found (no information leakage)
resource = await repo.get_by_id_and_org(db, resource_id, org_id=current_user.org_id)
if resource is None:
    raise HTTPException(status_code=404, detail="NOT_FOUND")
```

## Why

A 403 response to `GET /api/resources/{id}` tells the attacker:
- The ID is valid
- The resource exists
- They just don't have permission

An attacker can enumerate valid IDs across tenants by cycling UUIDs and watching
for 403 vs. 404 responses. With 404 for both "not found" and "wrong tenant",
sequential/random ID scanning yields no useful information.

## How to Apply

1. **Repository layer:** Include `org_id` in the lookup query
   ```python
   # Filter by BOTH id AND org_id in the same query
   result = await db.execute(
       select(Resource)
       .where(Resource.id == resource_id)
       .where(Resource.org_id == org_id)   # tenant filter
   )
   resource = result.scalar_one_or_none()  # returns None for wrong-org AND not-found
   ```

2. **Service layer:** Raise KeyError or a domain exception (not HTTPException)
   ```python
   if resource is None:
       raise KeyError("RESOURCE_NOT_FOUND")  # let router map to 404
   ```

3. **Router layer:** Catch and return 404
   ```python
   except KeyError:
       raise HTTPException(status_code=404, detail="NOT_FOUND")
   ```

## Applies To

- All `GET /resources/{id}` endpoints in multi-tenant APIs
- All `PUT`, `PATCH`, `DELETE` operations on owned resources
- API key revocation, permission checks, subscription lookups
- Any endpoint where a user supplies a resource ID that could belong to another tenant

## Exceptions (when 403 IS correct)

- Listing endpoints: returning empty list (not 403) is correct — no ID exposure
- Rate limit exceeded: 429, not 404
- Insufficient role (admin-only endpoint): 403 is correct — the user knows they're authenticated
- Publicly enumerable resources (public product catalog, etc.) — 403 is appropriate

## Expiry

Permanent rule. This is a standard OWASP IDOR (Insecure Direct Object Reference) mitigation.
