# Solution Strategy — Multi-Client Support

> **Feature:** multi-client-support | **Phase:** SPARC Solution | **Date:** 2026-04-04

---

## Problem Statement (SCQA)

- **Situation:** CAT is a multi-tenant SaaS where one Organization = one brand/company. Digital agencies monitoring 10+ FMCG brands must create a separate CAT account per brand.
- **Complication:** Agencies are the primary growth channel for this type of SaaS. Forcing them to manage 10 logins, 10 user lists, and 10 billing accounts creates friction that drives churn — especially when competitors offer a unified agency dashboard.
- **Question:** How do we let agencies manage multiple brand clients from one account without compromising data isolation or making the data model unmanageably complex?
- **Answer:** Introduce `Client` as a lightweight sub-scope within an Organization. Brands are assigned to clients. JWT carries an optional `client_id` claim for context switching. All existing queries add one optional `WHERE brands.client_id = :client_id` guard. No other tables change.

---

## First Principles Analysis

1. **Data belongs to orgs, context belongs to sessions.** The DB doesn't need to know which client a user is "looking at" — the JWT token carries that session state. The DB only needs `client_id` on brands to enable filtering.

2. **All domain data traces back to brands.** SKUs belong to brands. Everything else (scores, prices, reviews, alerts) belongs to SKUPlatforms which belong to SKUs. So `brands.client_id` is the single choke point for all scoping.

3. **Backward compatibility is non-negotiable.** Existing single-brand orgs must work without changes. `client_id = NULL` must mean "unscoped / all-clients" throughout the codebase.

4. **Slug is the human-readable key.** UUIDs are for machines. Agencies refer to clients by name. A unique slug per org enables URL-safe routing and report filenames.

---

## Key Design Decisions

| Decision | Options | Chosen | Reason |
|----------|---------|--------|--------|
| Client as sub-tenant | Full sub-org, Brand tag, JWT scope | Brand FK + JWT claim | Minimal schema change, full isolation via join |
| Context storage | JWT claim, Redis session, DB flag | JWT claim | Stateless, no extra infra, cryptographically signed |
| Cross-client view | Separate "all" endpoint, no-filter mode | client_id=None = all mode | Single code path, existing tests pass |
| Client deactivation | Hard delete, soft delete, archive | Soft delete (is_active=false) | Preserves historical data and audit trail |
| Slug scope | Global unique, org-unique | Org-unique | Agencies may use same client names |

---

## TRIZ Contradictions Resolved

| Contradiction | Principle | Resolution |
|---------------|-----------|------------|
| Data isolation vs. minimal schema change | #1 Segmentation | Isolate at brand level — single FK, all downstream data inherits |
| Context switch speed vs. security | #10 Preliminary Action | JWT carries context (fast) + server validates on switch (secure) |
| Backward compat vs. new behavior | #15 Dynamics | NULL client_id = existing behavior; non-NULL = new behavior |

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Developer forgets client filter in new query | Medium | High | Linter rule + code review checklist item |
| Token with stale client_id after deactivation | Low | Medium | Re-validate client_id on every request |
| Slug collision causing 409 confusion | Low | Low | Clear error message + frontend uniqueness check |
| Report generation missing client filter | Medium | Medium | Report service reads client_id from AuthContext, not from request |
