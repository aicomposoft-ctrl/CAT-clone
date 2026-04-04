# PRD — Multi-Client Support (Agency Model)

> **Feature:** multi-client-support | **Phase:** SPARC Planning | **Date:** 2026-04-04

---

## 1. Overview

CAT's current model is one-to-one: one Organization = one brand/company. Digital agencies that manage monitoring for 5–20 brand clients need to work across all their clients from a single CAT account — without logging in/out, without duplicating users, and with clean data separation between clients.

**Solution:** Introduce a `Client` entity as a named sub-scope within an Organization. Brands are assigned to clients. All downstream data (SKUs, content scores, stock, prices, reviews, alerts, reports) inherits client scope through the brand relationship. Agency users select an active client context from a header dropdown; all views, exports, and alerts filter accordingly.

---

## 2. Problem Statement

| Problem | Impact |
|---------|--------|
| Agency manages 10 brands — each in a separate CAT org | 10× login overhead, no cross-client view |
| No way to generate a per-client Excel report from one account | Manual work per client |
| Users must be added to each org separately | Access management nightmare |
| No client-level branding/contact info for agency reports | Reports look unprofessional |

---

## 3. Goals

- **G1:** Agency creates and manages multiple clients under one CAT organization
- **G2:** All data (SKUs, scores, alerts, reports) is isolated per client within the org
- **G3:** Users can switch client context instantly without re-authentication
- **G4:** Per-client reports and alerts (Excel, email) are clearly branded by client
- **G5:** Backward compatible — existing single-brand orgs work unchanged (client_id = NULL)

---

## 4. Non-Goals

- White-label / reseller model (client gets their own login) — Phase 2
- Cross-client analytics (compare KPIs across clients) — Phase 2
- Client-specific user permissions (user X can only see client A) — Phase 2
- Billing per client — out of scope

---

## 5. Target Users

| Persona | Context | Need |
|---------|---------|------|
| **Agency manager** | Manages 10 FMCG clients | Switch between clients, run per-client reports |
| **Agency analyst** | Day-to-day monitoring | See only the client they're working on today |
| **Agency admin** | Sets up new client onboarding | Create client, assign brands, invite users |

---

## 6. Feature Scope (MVP)

### Client Management (admin only)
- `POST /api/v1/clients` — create client (name, slug, contact_email, logo_url optional)
- `GET /api/v1/clients` — list all org's clients
- `GET /api/v1/clients/{id}` — get client detail
- `PATCH /api/v1/clients/{id}` — update client info
- `DELETE /api/v1/clients/{id}` — deactivate (soft delete)

### Brand-Client Assignment
- `PATCH /api/v1/brands/{id}` — add `client_id` to existing brand endpoint
- On brand creation — optionally specify `client_id`

### Client Context in JWT
- `POST /api/v1/auth/switch-client` — issue new access token with `client_id` claim
- All existing endpoints respect `client_id` claim: filter brands/SKUs by client when set

### Frontend
- Client selector dropdown in top navigation (persisted in user session)
- "All clients" mode — shows all data with client label column
- Per-client color badge on brand/SKU lists

---

## 7. Data Model Change

**Minimal schema impact:** Only `clients` (new table) and `brands.client_id` (new FK column).

All other domain tables (skus, content_scores, stock, prices, reviews, alerts, reports) chain through brands — no schema changes needed in those tables.

```
Organization
└── Client (new)    ← org_id FK
    └── Brand       ← client_id FK (nullable)
        └── SKU
            └── SKUPlatform
                └── ContentScore / Stock / Price / Review / Alert
```

---

## 8. Success Metrics

| Metric | Target |
|--------|--------|
| Client switch time | < 200ms (new JWT issued) |
| No data leak between clients | Zero cross-client queries |
| Backward compat — existing orgs work | All existing tests pass unchanged |
| Client creation to first SKU visible | < 5 min (UX flow) |

---

## 9. Security Requirements

- `client_id` in JWT is validated server-side: must belong to `current_user.org_id`
- All queries with active client context filter `brands.client_id = client_id`
- A user cannot set `client_id` to a client belonging to a different org
- `client_id = NULL` in JWT = "all clients" mode (org-level view)
- Soft delete: deactivated clients' data is hidden but not destroyed
