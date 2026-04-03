# Validation Report — Price Monitoring

**Date:** 2026-04-03
**Phase:** 2 — Requirements Validation (5 parallel agents)
**Methodology:** INVEST + SMART criteria, BDD coverage, technical feasibility, security

---

## Summary

| Agent | Scope | Score | Status |
|-------|-------|-------|--------|
| 1 | US-1 (Price history) | 89/100 | ✅ PASS |
| 2 | US-2 (Latest prices) | 89/100 | ✅ PASS |
| 3 | US-3 (Stats) + US-4 (Anomalies) | 82/100 | ✅ PASS |
| 4 | BDD scenario coverage | 78/100 | ✅ PASS |
| 5 | Technical feasibility | 92/100 | ✅ FEASIBLE |
| Cross-cutting | Security & multi-tenant isolation | 78/100 | ✅ PASS |

**Minimum required:** 70/100 per story. All stories pass. **Zero BLOCKED items.**

---

## User Story Assessments

### US-1: View price history for a SKU — 89/100

**INVEST: 88/100**

| Criterion | Score | Notes |
|-----------|-------|-------|
| Independent | 13/15 | Separable; minor dependency on Platform/SKU entities |
| Negotiable | 12/15 | `limit` default negotiable; date validation rules fixed |
| Valuable | 18/20 | Clear value: managers track price changes over time |
| Estimable | 14/15 | Clear API contract; p95 requires load-test infrastructure |
| Small | 13/15 | 6 scenarios; cross-platform JOIN increases scope slightly |
| Testable | 18/20 | HTTP codes specified; p95 < 200ms requires perf test setup |

**SMART: 84/100** | **Security bonus: +5** (cross-tenant 404, JWT required specified)

**Issues (non-blocking):**
- MINOR: `platform_id` not shown in response schema example despite being mentioned in scenario
- MINOR: "Viewer can read" scenario — role differentiation relative to manager not explained (both 200, which is correct but worth noting)
- MINOR: No explicit sprint delivery deadline (only "Sprint 6")

---

### US-2: Compare latest prices across platforms — 89/100

**INVEST: 90/100** | **SMART: 86/100** | **Security bonus: +5**

**Issues (non-blocking):**
- MINOR: No p95 latency NFR specified for /latest (US-1 has < 200ms; US-2 omitted)
- MINOR: Tie-breaking for "cheapest" when two platforms have identical price not specified
- MINOR: "Most recent snapshot" — same-day vs exact timestamp comparison not clarified (exact timestamp is correct, documented in Pseudocode)

---

### US-3: Price statistics over a period — 82/100

**INVEST: 94/100** | **SMART: 100/100** | **Security bonus: +5**

**Issues (non-blocking):**
- MINOR: NFR specifies "PERCENTILE_CONT(0.5)" — implementation detail better suited for Architecture/Pseudocode. Spec should say "statistical median" only.
- MINOR: No explicit "so that" clause in story description (value implied clearly from context)

---

### US-4: Detect price anomalies — 82/100

**INVEST: 94/100** | **SMART: 100/100** | **Security bonus: +5**

**Issues (non-blocking):**
- MINOR: NFR specifies "LAG window function" — implementation detail better in Architecture/Pseudocode
- MINOR: Intraday anomalies (multiple snapshots same day) behavior not specified — documented in Refinement.md as edge case

---

## BDD Coverage — 78/100 ✅ PASS

| Category | Coverage | Status |
|----------|----------|--------|
| Happy path (1-2 per endpoint) | 8/8 scenarios | ✅ |
| Error handling (2-3 per endpoint) | 12/12 scenarios | ✅ |
| Edge cases (1-2 per endpoint) | 6/8 scenarios | ⚠️ |
| Security (cross-tenant) | 4/4 endpoints | ✅ |

**Missing scenarios (add during Phase 3 tests):**
1. `401 Unauthenticated` — no Authorization header → reject all endpoints
2. `401 Expired/malformed JWT` — tampered token → reject
3. `429 Rate limiting` — 61+ requests in 60s → 429 Too Many Requests
4. `History limit param` — request with limit=1000, assert exactly 1000 rows returned
5. `Timezone boundary` — snapshot at 23:59 UTC counted in correct date bucket

---

## Technical Feasibility — 92/100 ✅ FEASIBLE

All 8 design decisions assessed as FEASIBLE. No blockers.

| Decision | Status | Notes |
|----------|--------|-------|
| `DISTINCT ON (platform_id)` | ✅ FEASIBLE | PostgreSQL 16 idiomatic |
| `PERCENTILE_CONT(0.5)` | ✅ FEASIBLE | PostgreSQL 16 native aggregate |
| `LAG()` window function | ✅ FEASIBLE | PostgreSQL 16, fully optimized |
| CTE + `ROW_NUMBER()` for first/last | ✅ FEASIBLE | Single round-trip, correct semantics |
| Max 2 SQL queries per endpoint | ✅ FEASIBLE | SKU check + data query |
| `extend_existing=True` on ORM | ✅ FEASIBLE | Standard pattern for shared tables |
| 366-day date range cap | ✅ FEASIBLE | Simple, effective unbounded-scan guard |
| p95 latency targets | ✅ FEASIBLE | With optional migration 0009 (idx on sku_platforms.sku_id) |

**Recommendation:** Apply migration 0009 immediately after feature launch to guarantee p95 for stats/anomalies under production load.

---

## Security & Multi-Tenant Isolation — 78/100 ✅ PASS

| Category | Score | Status |
|----------|-------|--------|
| Isolation correctness | 28/30 | ✅ JOIN chain correct |
| Input validation | 26/30 | ⚠️ threshold bounds missing in schema |
| Auth/authz coverage | 20/20 | ✅ JWT on all 4 endpoints |
| Rate limiting | 0/10 | ⚠️ Spec says 60 req/min — not in design yet |
| No secrets/data exposure | 8/10 | ✅ Minor: collected_at leaks scraper schedule |

---

## Issues Found — Action Items for Phase 3

| # | Severity | Issue | Resolution |
|---|----------|-------|------------|
| 1 | **CRITICAL** | Rate limiting (60 req/min per user) specified in NFR but not in design | Add Redis sliding-window rate limiter on all 4 routes in `router.py` |
| 2 | **MAJOR** | `threshold` param has no bounds in Pydantic schema | Add `Field(..., ge=0.0, le=100.0)` to `threshold` in schemas |
| 3 | **MAJOR** | `_validate_sku_access()` must be called in all 4 endpoints — must not be skipped | Verify in code review + integration test |
| 4 | MINOR | US-2 missing p95 NFR for /latest endpoint | Add to Specification: p95 < 200ms |
| 5 | MINOR | `platform_id` not shown in history response schema example | Add `platform_id` to example JSON |
| 6 | MINOR | Add 401/429 test scenarios | Add 3 scenarios to `test_prices_api.py` |

---

## Verdict

**All user stories PASS validation.** Minimum score 70/100 met across all dimensions. Zero BLOCKED items.

**Phase 3 pre-conditions:**
1. ✅ SPARC docs internally consistent and complete
2. ✅ All 4 endpoints have clear API contracts
3. ✅ Tenant isolation design verified correct
4. ⚠️ Rate limiting must be implemented (CRITICAL — item #1 above)
5. ⚠️ Threshold bounds validation must be in schema (MAJOR — item #2)

Feature is **ready for Phase 3 implementation** with items #1 and #2 addressed during implementation.
