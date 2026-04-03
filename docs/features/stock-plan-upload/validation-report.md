# Validation Report — Distribution Plan Upload (Stock Plan)

**Date:** 2026-04-03
**Phase:** 2 — Requirements Validation (5 parallel agents)
**Methodology:** INVEST criteria + SMART metrics + BDD scenario review

---

## Summary

| Agent | User Story | INVEST Score | SMART Score | Status |
|-------|-----------|-------------|------------|--------|
| 1 | US-1: Upload CSV | 87/100 | 90/100 | ✅ Pass |
| 2 | US-2: List plans | 82/100 | 85/100 | ✅ Pass |
| 3 | US-3: Delete plan | 90/100 | 88/100 | ✅ Pass |
| 4 | Cross-cutting: Tenant isolation | 91/100 | — | ✅ Pass |
| 5 | Cross-cutting: Error handling | 85/100 | — | ✅ Pass |

**Minimum required:** 70/100. All stories pass. Zero BLOCKED items.

---

## User Story Assessments

### US-1: Upload distribution plan via CSV

**INVEST Analysis:**

| Criterion | Score | Notes |
|-----------|-------|-------|
| Independent | ✅ 15/15 | No dependency on other in-progress features |
| Negotiable | ✅ 12/15 | Encoding and partial-import behavior are negotiable; column list is not |
| Valuable | ✅ 18/20 | Without plan data, Distribution Dashboard shows only fact — no plan/fact comparison |
| Estimable | ✅ 15/15 | CSV parsing + UPSERT is well-understood; 5 SP estimate is accurate |
| Small | ✅ 14/15 | Single endpoint; fits in one sprint |
| Testable | ✅ 13/20 | 11 BDD scenarios defined; cp1251 encoding test needs fixture file |

**SMART Metrics:**

| Metric | Specific | Measurable | Assessment |
|--------|----------|-----------|------------|
| Upload latency < 3s for 1000 rows | ✅ | ✅ Measurable with benchmark test | Pass |
| Idempotency (same CSV = same state) | ✅ | ✅ Row count check | Pass |
| Partial import: valid rows saved | ✅ | ✅ Assert imported == valid_count | Pass |

**Validation Findings:**
- ✅ Row limit (10 000) is specified in both PRD and Specification
- ✅ File size limit (5 MB) is consistent across all docs
- ✅ UPSERT behavior documented in Pseudocode and Specification
- ⚠️ Resolved: Week 53 validation boundary documented in Refinement

---

### US-2: List distribution plans

**INVEST Analysis:**

| Criterion | Score | Notes |
|-----------|-------|-------|
| Independent | ✅ 15/15 | Reads existing data; no external dependencies |
| Negotiable | ✅ 13/15 | Filter set and page size are negotiable |
| Valuable | ✅ 16/20 | Required for Distribution Dashboard and Excel Stock export |
| Estimable | ✅ 15/15 | Standard paginated list endpoint |
| Small | ✅ 15/15 | Simple query with 3 optional filters |
| Testable | ✅ 8/20 | Cross-tenant isolation test is mandatory and specified; filter combinations need more scenarios |

**Validation Findings:**
- ✅ Default page size (50), max (200) specified
- ✅ Filter params have type validation (week_number: 1–53, year: 2000–2100)
- ✅ Cross-tenant isolation covered by BDD scenario
- ⚠️ Resolved: Sort order (year DESC, week DESC) specified in Pseudocode

---

### US-3: Delete plan row

**INVEST Analysis:**

| Criterion | Score | Notes |
|-----------|-------|-------|
| Independent | ✅ 15/15 | No external dependencies |
| Negotiable | ✅ 14/15 | 404 vs 403 on cross-tenant delete is policy, documented in Refinement |
| Valuable | ✅ 18/20 | Needed to correct upload mistakes |
| Estimable | ✅ 15/15 | Simple DELETE with ownership check |
| Small | ✅ 15/15 | Single endpoint, minimal logic |
| Testable | ✅ 13/20 | 3 scenarios defined; happy path, 404, cross-tenant |

**Validation Findings:**
- ✅ Cross-tenant delete returns 404 (not 403) — prevents existence leakage; documented
- ✅ HTTP 204 on success (no body)
- ✅ Subquery-based ownership check in Pseudocode (no JOIN needed for DELETE)

---

### Cross-cutting: Tenant Isolation

**Assessment:**

| Check | Status | Evidence |
|-------|--------|---------|
| Barcode lookup is org-scoped | ✅ | `lookup_skus_by_barcode(org_id=org_id)` — Pseudocode §4 |
| List query joins through skus.org_id | ✅ | Architecture §5, Pseudocode list_plans |
| Delete verifies org ownership | ✅ | Subquery `WHERE sku_id IN (SELECT id FROM skus WHERE org_id=...)` |
| UPSERT uses pre-validated sku_id only | ✅ | Barcode resolved with org scope before upsert |
| Cross-tenant barcode → RowError, not silent | ✅ | US-1 BDD scenario "Unknown SKU barcode (cross-tenant protection)" |

**Score: 91/100.** The tenant isolation design is solid. No `org_id` column on `distribution_plans` is a deliberate design choice (consistent with the existing schema), mitigated by mandatory JOIN pattern.

---

### Cross-cutting: Error Handling

**Assessment:**

| Scenario | HTTP Code | Documented |
|----------|-----------|-----------|
| Wrong Content-Type | 422 | ✅ |
| File too large | 422 | ✅ |
| Empty file | 422 | ✅ |
| Missing CSV columns | 422 | ✅ |
| Row-level validation errors | 200 + errors[] | ✅ |
| SKU barcode not in org | 200 + errors[] | ✅ |
| Platform name not found | 200 + errors[] | ✅ |
| DB integrity error during upsert | 422 (wrapped) | ✅ |
| Plan not found (DELETE) | 404 | ✅ |
| Insufficient role | 403 | ✅ |

**Score: 85/100.** All error paths are specified. The distinction between file-level (422) and row-level (200 + errors[]) is clear and consistent.

---

## Issues Found and Resolved

| Issue | Severity | Resolution |
|-------|----------|-----------|
| Week 53 ISO validity not checked | Minor | Documented as out-of-scope in Refinement; user responsibility |
| `platform_name` fuzzy matching absent | Minor | Documented as v2.0 feature; exact case-insensitive match for MVP |
| `application/octet-stream` in allowed MIME types | Major | Removed — only `text/csv` and `application/csv` accepted |
| `idx_skus_org_barcode` index not in original migration | Major | Added to migration 0005 (consistent with stock-plan-upload implementation) |
| Concurrent uploads — last-committed-wins not documented | Minor | Added to Refinement §Edge Cases |

---

## BDD Scenarios Coverage

| Scenario | Status |
|----------|--------|
| Valid CSV upload | ✅ Covered |
| Viewer cannot upload | ✅ Covered |
| File too large | ✅ Covered |
| Wrong content type | ✅ Covered |
| Missing CSV columns | ✅ Covered |
| Partial import (row errors) | ✅ Covered |
| Cross-tenant barcode | ✅ Covered |
| Unknown platform | ✅ Covered |
| Case-insensitive platform match | ✅ Covered |
| Idempotent re-upload | ✅ Covered |
| UPSERT overwrites plan_tt_count | ✅ Covered |
| cp1251 encoding | ✅ Covered |
| List with filters | ✅ Covered |
| Cross-tenant list isolation | ✅ Covered |
| Delete own row | ✅ Covered |
| Delete non-existent | ✅ Covered |
| Delete cross-tenant returns 404 | ✅ Covered |

---

## Verdict

**All user stories PASS validation.** Minimum score 70/100 met across all dimensions. Zero BLOCKED items. Feature is ready for Phase 3 implementation.
