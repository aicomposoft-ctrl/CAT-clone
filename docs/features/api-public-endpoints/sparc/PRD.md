# PRD — API Public Endpoints (External Integration API)

> **Feature:** api-public-endpoints | **Phase:** SPARC Planning | **Date:** 2026-04-04

---

## 1. Overview

CAT currently serves data exclusively through its web dashboard. FMCG brands and agencies that use CAT need programmatic access to integrate monitoring data into their own BI tools (Tableau, Power BI), ERP systems, and internal dashboards — without going through the UI.

**Solution:** A versioned External Integration API authenticated via long-lived API keys (`X-API-Key` header), exposing read-only views of all core CAT domains. API keys are org-scoped, named, and managed by admins through a dedicated management API.

---

## 2. Problem Statement

| Problem | Impact |
|---------|--------|
| No programmatic access to CAT data | BI integrations require manual CSV exports |
| JWT tokens expire in 15 min — unusable for automation | Bots and pipelines cannot authenticate |
| No audit trail for machine-to-machine access | Compliance teams cannot distinguish human vs. automated reads |
| No rate-scoped access control for integrations | One bad client can degrade service for all users |

---

## 3. Goals

- **G1:** Enable programmatic read access to CAT data for external integrations
- **G2:** Provide org-scoped API keys with name/expiry/revocation management
- **G3:** Rate-limit public API independently from web dashboard traffic
- **G4:** Maintain full multi-tenant isolation — no cross-org data leakage

---

## 4. Non-Goals

- Write operations via public API (create SKU, upload reference, etc.) — Phase 2
- OAuth2 / OpenID Connect flows — not required for B2B integrations
- Webhook push API — separate feature
- Public (unauthenticated) endpoints — all endpoints require a valid API key

---

## 5. Target Users

| Persona | Context | Need |
|---------|---------|------|
| **Brand BI analyst** | Connects Power BI to data sources | Pull content scores + stock into dashboards |
| **Agency developer** | Builds client reporting pipelines | Automate nightly data pulls via cron |
| **Brand admin** | Manages team access | Create/revoke API keys for each integration |

---

## 6. Feature Scope (MVP)

### API Key Management (admin/manager only)
- `POST /api/v1/api-keys` — create a named key with optional expiry
- `GET /api/v1/api-keys` — list all org's keys (with prefix, never full key)
- `DELETE /api/v1/api-keys/{id}` — revoke a key immediately

### Public Read Endpoints (API key auth)
- `GET /api/v1/public/skus` — paginated list of org's SKUs with latest content scores
- `GET /api/v1/public/skus/{sku_id}/content-score` — detailed content score breakdown
- `GET /api/v1/public/stock` — stock distribution matrix (platform × SKU)
- `GET /api/v1/public/prices` — latest price snapshots per platform
- `GET /api/v1/public/reviews/summary` — sentiment summary per brand/platform
- `GET /api/v1/public/alerts` — triggered alerts (last 30 days)

---

## 7. Success Metrics

| Metric | Target |
|--------|--------|
| p99 response time on public endpoints | < 300ms |
| API key validation overhead | < 5ms (Redis cache hit) |
| Zero cross-org data leakage incidents | 0 |
| API key creation to first successful request | < 2 min |

---

## 8. Security Requirements

- API key stored only as SHA-256 hash in DB; shown to user exactly once on creation
- Key prefix (first 8 chars) stored for display and fast lookup
- Rate limit: 60 requests/minute per key via Redis sliding window
- All public endpoints filter by `org_id` derived from API key — no `org_id` query parameter accepted from client
- `last_used_at` updated on every successful authentication (async, non-blocking)
- Key expiry enforced at authentication time; expired = 401
- Revoked keys return 401 immediately (no grace period)

---

## 9. Out of Scope

- Webhook registration and delivery
- Write API (POST/PUT/DELETE on business entities)
- Per-endpoint rate limits (global per-key limit only in MVP)
- IP allowlisting
- Key scopes/permissions (all keys get viewer-level read access)
