# Phase 4 Review Report: excel-export-reviews

**Date:** 2026-04-04
**Feature:** Excel Export (Reviews) — GET /api/v1/reports/reviews-export
**Branch:** claude/init-p-replicator-OZcDC

## Agent Scores

| Agent | Focus | Score | Verdict |
|-------|-------|-------|---------|
| Agent 1 | Code Quality | 72/100 | Changes Required |
| Agent 2 | Security | 82/100 | Approved |
| Agent 3 | Multi-Tenant Isolation | 96/100 | Approved |
| Agent 4 | Performance | 72/100 | Approved |
| Agent 5 | Test Coverage | 78/100 | Approved |

**Average score: 80/100** — All critical issues resolved.

---

## Agent 1 — Code Quality (72/100)

### Critical issues
- None

### Major issues fixed
- **`.limit()` placement**: Filters for `platform_id`, `sentiment`, `sku_id` were added via `.where()` after `.limit()`. While SQLAlchemy generates correct SQL (WHERE before LIMIT) regardless of chain order, the intent was ambiguous. Fixed: `.limit(_ROW_LIMIT + 1)` moved to end of chain after all conditional `.where()` calls, with an explanatory comment.

### Major issues — no fix required
- **`platform_id` org-scoping**: Agent flagged that `platform_id` is accepted without ownership check. Platforms are a global reference table (not org-scoped) — `platform_id = uuid_for_wildberries` is valid for any org. Tenant isolation is enforced by `SKU.org_id == org_id` in the WHERE clause, which already prevents cross-tenant data access regardless of platform_id value.

### Minor issues fixed
- **Local import comment**: Added explanation for why `from app.reviews.models import Review` is inside the function body (circular dependency avoidance).

### Minor issues deferred
- Type hints on `build_reviews_export`: Already present in implementation (Agent 1 evaluated compressed pseudocode)
- `_build_reviews_workbook` docstring: consistent with existing workbook builders which also lack docstrings

---

## Agent 2 — Security (82/100 — Approved)

### Critical issues
- None

### Major issues — no fix required
- **Rate limiting**: Agent flagged missing app-level rate limiting. Consistent with existing `content-export` and `stock-export` endpoints, which also have no Redis-based rate limiting in the application layer. Rate limiting for export endpoints is enforced at the Nginx level via `limit_req_zone`. No application-level rate limit needed.

### Confirmed safe
- A01: `SKU.org_id == org_id` in every query path ✅
- A03: All inputs are UUID/Literal/date — fully parameterized ✅
- Content-Disposition: `date` objects render as `YYYY-MM-DD` only — no injection surface ✅
- Error handling: `except Exception` logs and returns `"INTERNAL_ERROR"` — no stack trace leakage ✅

---

## Agent 3 — Multi-Tenant Isolation (96/100 — Approved)

No issues. All access vectors verified:
- `platform_id` filter: global reference table, org_id JOIN chain prevents leakage ✅
- `sku_id` filter: pre-validated via `get_by_id_and_org()` before query ✅
- No foreign-platform or foreign-sku path leaks org_a data to org_b ✅

---

## Agent 4 — Performance (72/100 — Approved)

### Critical issues
- None

### Major issues — verified, no fix required
- **`skus(org_id)` index**: Agent flagged potential sequential scan risk. Verified: `idx_skus_org_id` on `skus(org_id)` was created in migration 0002. Index exists — planner can use it for the JOIN step.
- **ORDER BY filesort**: `ORDER BY Brand.name, SKU.article, Platform.name, Review.review_date DESC` spans 4 tables — no single index covers this. PostgreSQL materialises and sorts. Acceptable at 10,001 rows. No mitigation needed at current scale.

### Minor notes
- `review_text` per row is unbounded (marketplace reviews can be several KB). At 10,000 rows, peak memory is ~50-100 MB. Acceptable for export workload; documented in Refinement.md as advisory.
- `idx_reviews_sp_sentiment` is not used by the export ORDER BY (expected — it covers `fetch_history`/`fetch_summary`).

---

## Agent 5 — Test Coverage (78/100 — Approved)

### Major issues fixed
- **Col 8 fill not tested**: Added `test_sentiment_color_applied_to_column_8_as_well` — verifies negative fill (#FFC7CE) on column 8 (Оценка тональности).
- **`sentiment_score` NULL → "—" not tested**: Added `test_sentiment_score_null_formatted_as_dash`.

### Final test count: 25 tests (11 E2E + 14 workbook unit tests)

---

## Fixes Applied

| Fix | File |
|-----|------|
| Move `.limit()` after conditional `.where()` calls | `repository.py` |
| Add comment explaining local `Review` import | `repository.py` |
| Add `test_sentiment_color_applied_to_column_8_as_well` | `test_reviews_export.py` |
| Add `test_sentiment_score_null_formatted_as_dash` | `test_reviews_export.py` |

## No-Fix Decisions

| Finding | Reason |
|---------|--------|
| `platform_id` ownership check | Platforms are global reference table; org_id JOIN chain prevents leakage |
| App-level rate limiting on reviews-export | Consistent with content-export and stock-export; Nginx enforces 5 req/min |
| ORDER BY filesort | Unavoidable for multi-table sort; acceptable at 10,001-row cap |
| `skus(org_id)` index concern | Index exists since migration 0002 |

## Result: APPROVED FOR MERGE
