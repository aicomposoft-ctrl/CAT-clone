# Architecture — Multi-Client Support

> **Feature:** multi-client-support | **Phase:** SPARC Architecture | **Date:** 2026-04-04

---

## 1. Component Overview

```
services/api/app/
├── clients/                    # NEW — client management domain
│   ├── __init__.py
│   ├── models.py               # Client ORM model
│   ├── schemas.py              # Request/Response schemas
│   ├── repository.py           # DB queries (always org_id scoped)
│   ├── service.py              # Business logic
│   └── router.py               # CRUD /api/v1/clients
├── auth/
│   ├── router.py               # UPDATED — add POST /switch-client
│   └── service.py              # UPDATED — add switch_client_context()
├── catalog/
│   └── models.py               # UPDATED — Brand gets client_id FK
└── core/
    └── deps.py                 # UPDATED — get_current_user returns client_id from token
```

---

## 2. Database Schema

### Table: `clients` (NEW)

```sql
CREATE TABLE clients (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name         VARCHAR(255) NOT NULL,
    slug         VARCHAR(100) NOT NULL,
    contact_email VARCHAR(255),
    logo_url     VARCHAR(500),
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_clients_org_slug ON clients(org_id, slug) WHERE is_active = TRUE;
CREATE INDEX idx_clients_org_id ON clients(org_id);
```

### Column: `brands.client_id` (NEW — nullable)

```sql
ALTER TABLE brands ADD COLUMN client_id UUID REFERENCES clients(id) ON DELETE SET NULL;
CREATE INDEX idx_brands_client_id ON brands(client_id);
```

**Backward compatibility:** `client_id = NULL` means "unassigned / org-level brand". Existing orgs are unaffected.

---

## 3. JWT Extension

The existing JWT access token gets an optional `client_id` claim:

```json
{
  "sub": "<user_id>",
  "org_id": "<org_id>",
  "role": "manager",
  "client_id": "<client_id>",   ← NEW (optional, omitted = all-clients mode)
  "type": "access",
  "exp": 1712160000
}
```

`get_current_user` dependency extracts `client_id` from the token and attaches it to the `User` object (or a new `AuthContext` dataclass). All downstream queries use it for scoping.

---

## 4. Client Context Scoping

### Without client context (client_id = None)
All queries use only `org_id` filter — existing behavior unchanged.

### With client context (client_id = <uuid>)
Queries filter brands by `client_id`, which cascades to all downstream data:

```python
# SKU query with client context
SELECT skus.*
FROM skus
JOIN brands b ON b.id = skus.brand_id
WHERE skus.org_id = :org_id
  AND b.client_id = :client_id   ← added when context is set
  AND skus.is_active = TRUE
```

No changes needed to sku_platforms, content_scores, stock, prices, reviews, alert_events — they all join through skus → brands.

---

## 5. Switch Client Flow

```
POST /api/v1/auth/switch-client { client_id: "<uuid>" | null }
        │
        ├─ Validate current JWT (existing get_current_user)
        ├─ If client_id not null:
        │     ├─ SELECT client WHERE id = client_id AND org_id = user.org_id AND is_active
        │     └─ 403 if not found
        ├─ Issue new access token with client_id claim
        │     (same exp as original, or fresh 15min window)
        └─ Return { access_token, token_type: "bearer" }
```

**No new DB tables** — context lives in JWT. No server-side session required.

---

## 6. Client-Scoped Report Filenames

When `client_id` is present in JWT, report service:
- Prepends `{client.slug}_` to filename: `nestle-ru_content_2026-04-04.xlsx`
- Adds client name to Excel header row (row 1)
- Filters SKU query through `brands.client_id = client_id`

---

## 7. Impact on Existing Domains

| Domain | Change Required | Notes |
|--------|----------------|-------|
| `auth` | Minor — add switch-client endpoint | Existing login/refresh unchanged |
| `catalog/brands` | Minor — add client_id to model + PATCH | Backward compatible (nullable) |
| `catalog/skus` | Minor — add client JOIN filter in repo | Only when client_id in token |
| `content` | Minor — client filter via brand JOIN | |
| `stock` | Minor — client filter via brand JOIN | |
| `prices` | Minor — client filter via brand JOIN | |
| `reviews` | Minor — client filter via brand JOIN | |
| `alerts` | Minor — client filter via brand JOIN | |
| `reports` | Minor — filename + header + filter | |
| `dashboard` | Minor — client filter on all summary queries | |

---

## 8. Frontend Changes

### Client Selector (TopNav)
```
[ Agency XYZ ▼ ] → [ All Clients | Nestle RU ✓ | P&G | Unilever ]
```
- Calls `POST /api/v1/auth/switch-client` on selection
- Stores new token in localStorage
- Reloads current page data (React Query invalidation)

### Client Management Page (new route: `/settings/clients`)
- Table: name, slug, brands_count, contact_email, status
- Actions: create, edit, deactivate
- Brand assignment: select brands → assign to client

---

## 9. Security Boundaries

```
JWT claim client_id
        │
        ▼
get_current_user dependency
        │
        ├─ Validates client_id belongs to user.org_id (on every request)
        ├─ Validates client is_active (cached in token, re-checked on switch)
        └─ Returns AuthContext { user, org_id, client_id }
                │
                ▼
        All repo queries:
        WHERE org_id = :org_id
          AND (brands.client_id = :client_id OR :client_id IS NULL)
```

Key guarantee: `client_id` in JWT is cryptographically signed — cannot be forged. Server re-validates client belongs to org on every switch. Between switches, the signed token is authoritative.
