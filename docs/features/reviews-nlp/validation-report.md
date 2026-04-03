# Validation Report — Reviews NLP

**Feature:** Reviews NLP Sentiment Analysis
**Validation date:** 2026-04-03
**Method:** 5 parallel requirements-validator agents (INVEST + SMART + BDD + Feasibility + Security)
**Status after fixes:** ✅ PASS — all gates cleared

---

## Summary

| Agent | Focus | Initial Score | Fixed Score | Gate |
|-------|-------|---------------|-------------|------|
| 1 | US-1/US-2 story completeness | 78/100 | 78/100 | ✅ PASS |
| 2 | BDD scenario coverage | **58/100** | **82/100** | ✅ PASS after fix |
| 3 | US-3/US-4 AC clarity | 78/100 | 82/100 | ✅ PASS |
| 4 | Technical feasibility | 82/100 | 82/100 | ✅ PASS |
| 5 | Security / multi-tenant | 72/100 | 72/100 | ✅ PASS |

**Overall:** Ready for implementation. No BLOCKED items.

---

## Agent 1: US-1 & US-2 Story Completeness (78/100 ✅)

**US-1 (Sentiment Summary):** 78/100 — PASS
- All 6 INVEST criteria satisfied
- SMART: 4.5/5 — minor gap in time-bound (p95 in NFRs, not in AC)
- Field name harmonised: `last_review_date` (PRD said "most-recent review date" — minor)

**US-2 (Paginated History):** 72/100 — PASS
- All 6 INVEST criteria satisfied
- AC4 expanded to explicitly name all invalid parameter cases (sentiment enum, limit, offset, date)

**Fixes applied:**
- AC3 for /history now explicitly covers date range validation errors
- Zero-result edge case made explicit in /history AC

---

## Agent 2: BDD Scenario Coverage (58/100 → 82/100 ✅)

**Initial gaps:** 10 missing scenarios (401 auth, invalid enum, empty results, date boundaries,
rate limiting 429, idempotency, model failure retry, whitespace text, limit boundaries).

**Scenarios added to Specification.md Section 6:**
1. Unauthenticated request rejected (all 3 endpoints) — 401
2. Invalid sentiment enum → 422
3. Zero reviews → HTTP 200 empty response
4. date_from = date_to (single day) is valid
5. Exactly 366-day range is valid
6. Rate limit exceeded → 429 with Retry-After
7. score_pending_reviews idempotency (all scored already)
8. Model unavailable → Celery retry × 3
9. Whitespace-only review_text is skipped
10. limit boundary validation (0 → 422, 501 → 422, 500 → 200)

**Total BDD scenarios after fix:** 17 (was 7)

---

## Agent 3: US-3 & US-4 Acceptance Criteria Clarity (78/100 → 82/100 ✅)

**US-3 (Stats):** 78/100 — PASS
- "as fractions" clarified to `decimals in [0.0, 1.0]` in Specification
- Nullability contract made explicit: `review_count` always present, `sentiment_share` nullable,
  `avg_rating` nullable on zero reviews, `weekly_trend` always an array (may be empty)

**US-4 (Celery Scorer):** 82/100 — PASS
- Retry parameters made concrete: base 60s, multiplier 2× (60/120/240s), max 3 retries
- Whitespace-only text added to skip conditions (PRD + Specification)
- Return value structure documented in AC: `{"scored": N, "skipped": M}`

---

## Agent 4: Technical Feasibility (82/100 ✅)

**All SQL patterns feasible on PostgreSQL 16:**
- `COUNT(*) FILTER (WHERE ...)` — PG 9.4+ ✅
- CTE + `json_agg(row_to_json())` — PG 9.3+ ✅
- `SELECT ... FOR UPDATE SKIP LOCKED` — PG 9.5+ ✅

**Migration safety:** ALTER TABLE ADD COLUMN (nullable) — instant on PG 16, no table lock ✅

**Model choice:** rubert-base-cased-sentiment — adequate for Russian text ✅
- Language assumption documented in Specification.md Section 3
- Multi-language fallback documented (xlm-roberta-base)

**Numeric(4,3) for sentiment_score:** Supports 0.000–9.999 — sufficient for [0.0, 1.0] ✅
(Agent 4 suggested Numeric(3,3) but that would only support 0.000–0.999 — incorrect for score=1.0)

**validate_date_range duplication:** Accepted as-is (3-line function, avoids cross-domain coupling).
Documents as technical debt in Refinement.md. Candidate for `app.core.utils` in Sprint 8 refactor.

---

## Agent 5: Security / Multi-Tenant (72/100 ✅)

**Multi-tenant isolation:** PASS ✅
- Two-gate pattern: router SKU ownership check + repository org_id JOIN
- JOIN chain: `reviews → sku_platforms → skus.org_id`
- Cross-tenant scenario: HTTP 404 (not 403 — avoids org existence leak)

**Rate limiting:** PASS ✅ — 60 req/min, Redis sliding window, graceful degradation

**F-string SQL:** ACCEPTED RISK ✅
- Same pattern used in prices domain (proven safe)
- Only literal SQL clauses interpolated — never user strings
- Sentiment validated as `Literal["positive","neutral","negative"]` before repository
- Documented in repository docstring (same pattern as prices/repository.py)

**OWASP:** A01 ✅ A03 ✅ (partial / guarded) A04 ✅ A07 ✅

**RLS recommendation:** Deferred — application-level org_id filtering is mandatory and the
prices domain (identical pattern) is already in production without RLS policy on reviews.
Tracked as future security hardening item.

---

## Pre-Implementation Checklist

- [x] All 4 user stories score ≥ 70/100
- [x] BDD scenarios cover all 3 endpoints (happy + error + edge)
- [x] Cross-tenant isolation test scenario present
- [x] Rate limiting concretely specified (60 req/min)
- [x] Celery retry parameters concrete (60/120/240s, max 3)
- [x] Language assumption documented
- [x] Migration safety confirmed (nullable ALTER TABLE)
- [x] Throughput budget documented (1,000 reviews/min, 10s per 1k batch)
