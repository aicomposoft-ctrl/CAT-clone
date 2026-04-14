# Solution Strategy — API Public Endpoints

> **Feature:** api-public-endpoints | **Phase:** SPARC Solution | **Date:** 2026-04-04

---

## Problem Statement (SCQA)

- **Situation:** CAT provides FMCG brands with daily monitoring data across 110+ platforms. Data is accessible only via a React web dashboard authenticated by short-lived JWT tokens.
- **Complication:** Brands and agencies need to integrate CAT data into BI tools (Power BI, Tableau), ERP systems, and automated pipelines that cannot handle 15-minute JWT expiry or browser-based auth flows.
- **Question:** How do we enable secure, programmatic, long-lived access to CAT data without weakening the existing multi-tenant security model?
- **Answer:** Introduce org-scoped, long-lived API keys with `X-API-Key` authentication. Keys are managed by admins via the existing JWT API, stored only as SHA-256 hashes, and grant read-only access scoped to the key's organization.

---

## First Principles Analysis

1. **Authentication is about identity, not transport.** JWT proves who a user is. API keys prove which org a machine belongs to. Different problem, different tool.
2. **Multi-tenancy must be enforced at the data layer, not the auth layer.** The API key resolves to `org_id` — all downstream queries still filter by `org_id` regardless.
3. **A key that's seen is a key that can leak.** Therefore: compute hash on creation, store hash, show raw key once, never log it.
4. **Rate limiting protects shared infrastructure.** One integration should not be able to starve another org's web users.

---

## Key Design Decisions

| Decision | Options Considered | Chosen | Reason |
|----------|--------------------|--------|--------|
| Auth mechanism | OAuth2, JWT long-lived, API keys | API keys | Simplest for B2B machine-to-machine; no browser flow needed |
| Key storage | Plaintext, encrypted, hashed | SHA-256 hash only | Breach of DB does not expose valid keys |
| Key format | UUID, random hex, prefixed | `cat_live_{token_urlsafe(30)}` | Prefix enables quick format validation and log masking |
| Rate limit storage | DB counter, Redis | Redis sliding window | Non-blocking, consistent with existing infra |
| Endpoint namespace | `/api/v1/` with key auth, `/public/` | `/api/v1/public/` | Clear separation; key vs JWT auth by URL prefix |
| Tenant resolution | `org_id` in request, from key | From key only | Client cannot spoof a different org_id |

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Key leaked via logs | Medium | High | Log masking mandatory in deps.py and middleware |
| Brute-force key guessing | Low | High | 40-char random token = 2^240 space; rate limit adds protection |
| Cross-org data leak | Low | Critical | org_id derived from key, never from client input |
| Redis unavailability blocks auth | Low | High | On Redis failure, fail open for rate check (or use Circuit Breaker) |
| last_used_at fire-and-forget loses updates | Medium | Low | Acceptable — metric is informational, not security-critical |

---

## TRIZ Contradictions Resolved

| Contradiction | TRIZ Principle | Resolution |
|---------------|----------------|------------|
| Security (short-lived tokens) vs. Usability (long-lived access) | #10 Preliminary Action | Pre-create API keys at admin time; separate auth flows for human vs. machine |
| Key must be shown to user vs. Key must not be stored | #15 Dynamics | Show once at creation, store only hash — two representations serve two purposes |
| Rate limiting must be fast vs. Rate limiting must be accurate | #35 Parameter Changes | Redis atomic pipeline — consistent and O(log N) |
