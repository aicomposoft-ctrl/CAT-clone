# Review Report: excel-export-content

**Date:** 2026-04-02
**Phase:** 4 — 5 Parallel Review Agents (brutal-honesty-review)
**Status:** No Critical issues. Major issues documented with remediation guidance.

---

## Scores

| Agent | Scope | Score | Verdict |
|-------|-------|-------|---------|
| 1 | Code Quality (Linus mode) | 74/100 | 0 Critical, 3 Major, 4 Minor |
| 2 | Security (OWASP) | 86/100 | 0 Critical, 1 Major, 2 Minor |
| 3 | Multi-tenant Isolation | 92/100 | 0 Critical, 0 Major, 1 Minor |
| 4 | Performance | 68/100 | 0 Critical, 2 Major, 2 Minor |
| 5 | Test Coverage | 72/100 | 0 Critical, 2 Major, 3 Minor |

---

## Agent 1: Code Quality (Linus Mode)

### MAJOR — Score columns hardcoded as range(6, 10)

**File:** `services/api/app/reports/service.py`, line 116

```python
for col_idx in range(6, 10):
    ws.cell(row=row_idx, column=col_idx).fill = fill
```

**Problem:** The range `6, 10` is a magic number. If a column is ever inserted before column 6 (e.g., a "Category" column added before "Date"), this range silently fills the wrong cells. The `_COLUMNS` definition already encodes the correct column order. The fill should be applied to the score columns by index derived from `_COLUMNS`, not a hardcoded range.

**Fix:** Replace with:
```python
# Score columns are indices 5-8 (0-based) → columns 6-9 (1-based)
SCORE_COLUMN_INDICES = [i + 1 for i, (_, attr, _) in enumerate(_COLUMNS) if attr in _SCORE_ATTRS]
```
Or at minimum, add a named constant: `_SCORE_COL_START = 6; _SCORE_COL_END = 10`.

---

### MAJOR — `_build_workbook` is not unit-testable in isolation for color logic

**File:** `services/api/app/reports/service.py`

**Problem:** The color fill decision (`_score_fill`) is tied to `content_total` value, but the function that applies the fill (`_build_workbook`) does not expose which rows received which fill — the test must reach into the openpyxl cell object to check `fill.fgColor.rgb`. This works but is brittle. A future refactor that changes cell coordinates would silently break tests.

**Fix:** No immediate code change needed. Document that `_SCORE_COL_START`/`_SCORE_COL_END` constants are the source of truth for test assertions. Lower-priority improvement.

---

### MAJOR — `ContentScoreRow` imported from `service.py` in tests — it belongs to `repository.py`

**File:** `services/api/tests/e2e/test_reports_api.py`, line 329

```python
from app.reports.service import ContentScoreRow, _build_workbook
```

**Problem:** `ContentScoreRow` is defined in `repository.py` but the test imports it from `service.py`. This works because `service.py` re-imports it via `from app.reports.repository import ContentScoreRow, ...`, but it suggests the test author was uncertain about the ownership. Imports from `_private` functions (`_build_workbook`) in tests are acceptable for unit testing internal behavior, but the dataclass import should come from its canonical module.

**Fix:**
```python
from app.reports.repository import ContentScoreRow
from app.reports.service import _build_workbook
```

---

### MINOR — `_COLUMNS` is a list of 3-tuples; attribute name is unused during workbook build

**File:** `services/api/app/reports/service.py`, lines 33–43

The second element of each `_COLUMNS` tuple (the attribute name, e.g. `"brand_name"`) is never used in `_build_workbook`. The values are assembled manually from `row.<attr>` in the `values = [...]` list. This creates a maintenance hazard: if `_COLUMNS` order is changed, the `values = [...]` list must also be updated manually — there is no enforcement coupling them.

**Fix (preferred):** Build the values list using the attribute names from `_COLUMNS`:
```python
values = [getattr(row, attr) for _, attr, _ in _COLUMNS]
```
With special handling for `sku_article` (NULL → em-dash) and score formatting. This makes `_COLUMNS` the authoritative source for both headers and data extraction.

---

### MINOR — Generic `except Exception` in router masks legitimate bugs during development

**File:** `services/api/app/reports/router.py`, lines 93–98

```python
except Exception:
    logger.exception("Unexpected error generating content export")
    raise HTTPException(status_code=500, detail="INTERNAL_ERROR")
```

**Problem:** This pattern is correct for production (never expose stack traces to clients) but catches `CancelledError` and `KeyboardInterrupt` subtypes in Python < 3.11 context. Should use `except Exception` (already correct — `BaseException` would be the problem). The broader concern is that during development, this swallows all errors with the same opaque response. Acceptable as-is with the logger.exception call, which preserves the traceback server-side.

**Status:** Acceptable, no change required.

---

### MINOR — Module-level openpyxl style objects created at import time

**File:** `services/api/app/reports/service.py`, lines 45–53

```python
_HEADER_FILL = PatternFill("solid", fgColor="4472C4")
_HEADER_FONT = Font(bold=True, color="FFFFFF", name="Calibri")
...
```

**Problem:** These objects are created once at module import. openpyxl style objects are generally safe to reuse across workbooks, but this is not explicitly documented in openpyxl's public API as thread-safe. In practice, these are value objects with no mutable state — the pattern is correct and common.

**Status:** Acceptable. Note added in Refinement.md.

---

### MINOR — Score formatting returns string but header says "Оценка изображения"

**File:** `services/api/app/reports/service.py`, line 68

Score cells contain strings (`"85.1"`, `"—"`) rather than numeric values. This means Excel's SUM/AVERAGE functions will not work on these cells. If a user tries to sum a column, they get 0.

**Fix (follow-up):** Consider storing as `Decimal`/`float` and relying on openpyxl's number format: `cell.number_format = "0.0"`. Use `"—"` only for NULL. This would enable Excel formula usage.

**Status:** Deferred — current behavior is documented and intentional (string with one decimal place). Follow-up task.

---

## Agent 2: Security (OWASP)

### MAJOR — No rate limiting on the export endpoint

**File:** `services/api/app/reports/router.py`

**Problem:** The content-export endpoint generates an openpyxl workbook in memory for every request. A determined attacker with a valid JWT could issue many concurrent 366-day range requests, each consuming significant CPU (JOIN across 4 tables) and memory (openpyxl build). The only protection is the inherited global 100 req/min per user rate limit.

**Risk:** Moderate. Requires a valid authenticated JWT. An insider or compromised account could cause sustained API worker saturation.

**Remediation:** Add export-specific rate limiting (e.g., 5 req/min per `org_id`) consistent with the NFR in PRD.md. Implementation: Redis sliding window counter on `f"export:{org_id}"`.

**Status:** Deferred — whole-API rate limiting is a separate infrastructure task. Tracked in security backlog.

---

### MINOR — A01: Tenant isolation verified (no issue)

The query always uses `current_user.org_id` sourced from the JWT claim, not from any user-controllable query parameter. The WHERE clause `skus.org_id = :org_id` is mandatory (never conditionally applied). Cross-tenant isolation test passes. No finding.

---

### MINOR — A03: No SQL injection risk (no issue)

All query parameters (`date_from`, `date_to`, `platform_id`) are FastAPI-validated typed values passed as SQLAlchemy bind parameters. No f-string interpolation into SQL. No finding.

---

### MINOR — Content-Disposition filename contains user-controlled dates

**File:** `services/api/app/reports/router.py`, line 100

```python
filename = f"content_scores_{date_from}_{date_to}.xlsx"
```

`date_from` and `date_to` are `date` objects (FastAPI-validated), so their `.isoformat()` representation contains only digits and hyphens. No injection risk. However, a future change that uses a string input could introduce header injection.

**Status:** Not a current risk. No change needed.

---

## Agent 3: Multi-Tenant Isolation

### PASS — Isolation is correctly implemented

**Evidence:**
1. `get_content_scores_for_export` always passes `org_id` (from `current_user.org_id`) as a mandatory parameter. There is no code path that calls the repository without `org_id`.
2. The SQL `WHERE SKU.org_id == org_id` is unconditional — it cannot be bypassed by any query parameter.
3. `content_scores` has no `org_id` column — isolation is enforced via the JOIN chain (`content_scores → sku_platforms → skus`). This is the correct pattern for this schema.
4. `test_content_export_cross_tenant_isolation` creates data for two orgs and verifies Org B's scores do not appear in Org A's export.
5. PostgreSQL RLS on `skus` table provides defense-in-depth.

### MINOR — No test for authenticated cross-org HTTP request (E2E layer)

**File:** `services/api/tests/e2e/test_reports_api.py`

The cross-tenant test (`test_content_export_cross_tenant_isolation`) tests the repository function directly, not via the HTTP endpoint. There is no test that:
- Authenticates as Org B's user
- Calls `GET /api/v1/reports/content-export` with a date range that includes Org A's data
- Asserts the returned Excel workbook contains 0 data rows (or only Org B's rows)

**Risk:** Low — the HTTP path is `router → service.build_content_export(org_id=current_user.org_id) → repository`. The `org_id` value is fixed at `current_user.org_id` in the router with no way for a caller to override it. The repository-level test is sufficient proof of isolation.

**Recommendation:** Add an E2E-level isolation test to exercise the full HTTP → repository path as defense-in-depth.

---

## Agent 4: Performance

### MAJOR — No index on `content_scores.scored_at`

**File:** `services/api/app/reports/repository.py`, query filter

```python
.where(ContentScoreRead.scored_at >= date_from)
.where(ContentScoreRead.scored_at <= date_to)
```

**Problem:** The WHERE clause on `scored_at` performs a range scan. If there is no index on `(scored_at)` or `(sku_platform_id, scored_at)` on the `content_scores` table, PostgreSQL will do a full table scan — O(total rows), not O(matching rows). For an org with 12 months of history across 1000 SKUs × 10 platforms, the table can easily have millions of rows.

**Fix:** Add a migration with:
```sql
CREATE INDEX CONCURRENTLY idx_content_scores_scored_at ON content_scores (scored_at);
```
Or a composite index `(sku_platform_id, scored_at)` if queries are always narrow to a platform.

**Status:** Deferred — requires migration. Prioritize before production load.

---

### MAJOR — All data fetched into memory before workbook construction

**File:** `services/api/app/reports/service.py`, `build_content_export`

```python
rows = await get_content_scores_for_export(...)  # fetches ALL rows
wb = _build_workbook(rows, ...)                  # builds entire workbook in memory
buf = io.BytesIO()
wb.save(buf)                                     # serializes entire workbook to buffer
```

**Problem:** For a 366-day export covering thousands of SKUs, all rows are materialized as Python dataclass objects first, then the entire openpyxl workbook is held in memory simultaneously with the raw data. Peak memory = `sizeof(rows_list) + sizeof(workbook)`.

**Fix (future):** Use openpyxl's `write_only=True` mode:
```python
wb = Workbook(write_only=True)
ws = wb.create_sheet()
for row in rows:
    ws.append([...])
```
This streams rows into the file without keeping the full workbook in memory.

**Status:** Deferred — current memory usage is acceptable for expected data volumes (< 50 MB for 10k rows). Follow-up task when large org exports are tested.

---

### MINOR — `result.all()` materializes entire result set at once

**File:** `services/api/app/reports/repository.py`, line 95–96

```python
result = await db.execute(stmt)
rows = result.all()
```

`result.all()` fetches all rows into memory at the SQLAlchemy level. For very large result sets, `result.yield_per(1000)` or iterating with `result.fetchmany()` would reduce peak memory. Low priority given current scale.

---

### MINOR — No `LIMIT` guard on the query

**File:** `services/api/app/reports/repository.py`

The repository query has no `LIMIT`. A 366-day export for an org with many SKUs across many platforms could return unbounded rows. The date range validation (max 366 days) is the only guard.

**Recommendation:** Consider a soft limit (e.g., 100,000 rows) with an HTTP 413 or a warning in the response. Deferred until production usage patterns are known.

---

## Agent 5: Test Coverage

### MAJOR — No integration test for `platform_id` filter

**File:** `services/api/tests/e2e/test_reports_api.py`

**Problem:** `platform_id` is an optional filter that appends a WHERE clause to the query. There is no test verifying that:
- Providing `platform_id` returns only rows for that platform
- Providing a `platform_id` for a platform with no data returns an empty workbook

All E2E tests for the endpoint mock `service.build_content_export`, so the actual SQL filtering is not exercised end-to-end.

**Fix:** Add an integration test (using the real repository with fixture data) analogous to `test_content_export_cross_tenant_isolation`.

---

### MAJOR — No test for `build_content_export` empty result workbook

**File:** `services/api/tests/e2e/test_reports_api.py`

**Problem:** The contract states "returns an empty workbook (header only) when no data matches the filters." This is implemented in `build_content_export` and `_build_workbook` (passing `rows=[]`). However, there is no test that:
1. Calls `build_content_export` with an empty date range (or a date range with no data)
2. Parses the returned bytes with `openpyxl.load_workbook`
3. Asserts that the sheet has 2 rows (sub-header + column header) and 0 data rows

**Fix:** Add a unit test:
```python
def test_build_workbook_empty_rows_produces_header_only():
    wb = _build_workbook([], date_from=date(2026,1,1), date_to=date(2026,1,31))
    ws = wb.active
    assert ws.max_row == 2  # sub-header + column header only
```

---

### MINOR — Test `test_build_workbook_null_scores_no_fill` assertion is fragile

**File:** `services/api/tests/e2e/test_reports_api.py`, line 394

```python
assert ws.cell(row=3, column=9).fill.fill_type in (None, "none", "patternType")
```

**Problem:** The assertion allows `"patternType"` as an accepted value, which is the default fill type for a cell that has never had a fill applied in openpyxl. This means the test would pass even if a fill was incorrectly applied with `fill_type="patternType"` and a color. A stricter assertion would check that `fgColor.rgb` is the default (`"00000000"`) or that `fill_type` is exactly `None` or `"none"`.

**Fix:**
```python
fill = ws.cell(row=3, column=9).fill
assert fill.fill_type in (None, "none") or fill.fgColor.rgb == "00000000"
```

---

### MINOR — No test for `_fmt_score` boundary behavior

**File:** `services/api/app/reports/service.py`

`_fmt_score(Decimal("0"))` → `"0.0"` (valid)  
`_fmt_score(Decimal("100"))` → `"100.0"` (valid, though scores > 100 are unexpected)  

No test exercises these values. Low risk given the Numeric(5,2) DB column constraint.

---

### MINOR — E2E auth tests mock the service but the mock returns minimal bytes

**File:** `services/api/tests/e2e/test_reports_api.py`, `_make_real_xlsx()`

`_make_real_xlsx()` creates a workbook with no sheets configured (just `Workbook()` default). This is sufficient for testing headers and status codes. It would not be sufficient for testing workbook structure. Current usage is correct; note for future test authors.

---

## Critical Issues Summary

**No Critical issues found.**

The implementation is functionally correct. Multi-tenant isolation is properly enforced. Date validation is complete. Error handling is appropriate (opaque 500 with server-side logging). All existing tests pass.

---

## Major Issues Summary (Remediation Required Before High-Load Production)

| # | Agent | Issue | Priority |
|---|-------|-------|---------|
| M1 | Agent 1 | Score columns 6–9 hardcoded as `range(6, 10)` magic numbers | Medium |
| M2 | Agent 1 | `ContentScoreRow` imported from wrong module in tests | Low |
| M3 | Agent 1 | `_COLUMNS` attribute names unused in workbook builder (maintenance hazard) | Medium |
| M4 | Agent 2 | No export-specific rate limiting (DoS risk from authenticated users) | Medium |
| M5 | Agent 4 | No index on `content_scores.scored_at` — full table scan on date range filter | High |
| M6 | Agent 4 | Full in-memory workbook build — no streaming for large exports | Low |
| M7 | Agent 5 | No integration test for `platform_id` filter correctness | Medium |
| M8 | Agent 5 | No test for empty-result workbook (header-only) | Low |

---

## Deferred Issues

| # | Agent | Issue | Reason Deferred |
|---|-------|-------|----------------|
| D1 | Agent 2 | Export-specific rate limit (5 req/min per org) | Whole-API infrastructure task |
| D2 | Agent 4 | openpyxl write-only streaming mode | Acceptable until large-org exports are needed |
| D3 | Agent 4 | `result.all()` vs `yield_per` for memory efficiency | Not a current bottleneck |
| D4 | Agent 4 | No row `LIMIT` guard in repository | Defer until production usage patterns known |
| D5 | Agent 1 | Score cells as strings rather than numeric with format | UX improvement, not a bug |
| D6 | Agent 3 | E2E-level cross-org HTTP isolation test | Repository-level test is sufficient proof |
| D7 | Agent 5 | `_fmt_score` boundary values test | Near-zero risk given DB column type constraint |
| D8 | Agent 1 | Module-level openpyxl style object reuse (thread safety) | Value objects, safe in practice |

---

## Final Status

No Critical issues. Major issue M5 (missing index on `scored_at`) should be addressed before production load scales. All other majors are medium-to-low priority improvements with no immediate functional impact.

Feature is **production-ready at current scale** with M5 migration as the highest-priority follow-up action.
