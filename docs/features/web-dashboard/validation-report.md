# Validation Report — Web Dashboard
> Phase 2 | 5 parallel agents | Date: 2026-04-04

---

## Summary

| Agent | Score | Gate (≥70) | Status |
|-------|-------|-----------|--------|
| 1. User story completeness (INVEST/SMART) | 77.8/100 | PASS | ✅ |
| 2. BDD scenario coverage | 42/100 | FAIL | ❌ |
| 3. Acceptance criteria clarity | 63.1/100 | FAIL | ❌ |
| 4. Technical feasibility | 62/100 | FAIL | ❌ |
| 5. Security/multi-tenant | 62/100 | FAIL | ❌ |

**BLOCKED items (score < 50):** None
**Overall:** Revision required before implementation

---

## Critical Issues (Must Fix)

### Backend Missing Endpoints (Feasibility Agent)
1. **CRITICAL** — `content/` domain entirely absent from API. No ContentScore model, router, or repository. Blocks: Content page, Dashboard KPIs, Red Zone widget.
2. **CRITICAL** — `GET /api/v1/dashboard/summary` does not exist. Blocks: Dashboard Overview page.
3. **MAJOR** — `PATCH /api/v1/alerts/{id}/acknowledge` missing. `is_sent` ≠ `is_acknowledged`.
4. **MAJOR** — `GET /api/v1/reviews/sentiment` (org-wide, no sku_id) missing. Existing endpoint requires `sku_id`.
5. **MINOR** — Export endpoints use `GET` not `POST` — Pseudocode spec wrong, backend correct.

### BDD Gaps (Coverage Agent — 42/100)
6. **CRITICAL** — Zero error path scenarios across 9/10 stories (no wrong password, no API errors, no export failures).
7. **CRITICAL** — Multi-tenant isolation not behaviorally tested in any scenario.
8. **MAJOR** — RBAC scenarios entirely absent (viewer cannot create SKU, cannot acknowledge alerts, cannot export).
9. **MAJOR** — ~14/29 scenarios missing `Given` context clause.
10. **MAJOR** — Empty state scenarios absent (new org, 0 results after filter, no alerts).

### Acceptance Criteria (Clarity Agent — 63.1/100)
11. **CRITICAL** — Price anomaly threshold undefined in US-05 (what is the threshold value?).
12. **MAJOR** — Loading/empty/error UI states absent from all stories.
13. **MAJOR** — Token storage contradiction: NFR says "no localStorage", Architecture says `sessionStorage` — unresolved.
14. **MAJOR** — US-08 Export: filter-to-request-body mapping undefined, role guard absent.
15. **MAJOR** — US-03 Drill-down: diff rendering algorithm undefined, boundary navigation undefined.

### Security (Security Agent — 62/100)
16. **MAJOR** — `sessionStorage` for refresh token contradicts NFR (httpOnly cookie preferred). XSS risk.
17. **MAJOR** — `ProtectedRoute` role-check logic has no pseudocode — viewer RBAC guard unspecified.
18. **MAJOR** — XSS risk in scraped text rendering (review_text, diff output) not addressed.

---

## Iteration 1 Fixes Required

### Spec fixes (Specification.md)
- Add error path scenarios to all 10 stories
- Add multi-tenant isolation scenario (cross-org test)
- Add RBAC scenarios (viewer blocked from write actions)
- Add empty/loading/error state scenarios
- Define price anomaly threshold (MVP: 20% change in 24h)
- Fix missing `Given` clauses in 14 scenarios
- Resolve token storage contradiction → use sessionStorage explicitly, document XSS risk acceptance

### Architecture/Pseudocode fixes
- Add `ProtectedRoute` pseudocode with role check
- Add plain-text rendering requirement for scraped fields
- Fix export endpoint method: `GET` not `POST`
- Add `is_acknowledged` field to `AlertEvent` type (update backend schema)

### Backend prerequisites (Phase 3 must implement these first)
- Create `services/api/app/content/` domain
- Create `GET /api/v1/dashboard/summary` endpoint
- Add `PATCH /api/v1/alerts/{id}/acknowledge` to alerts router
- Add `GET /api/v1/reviews/sentiment` (org-wide aggregate)
