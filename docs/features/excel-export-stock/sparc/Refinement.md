# Refinement: Excel Export — Stock Distribution

**Feature:** `excel-export-stock`
**Date:** 2026-04-02

---

## Edge Cases

### NULL in_stock Rows Excluded

**Case:** A `content_scores` row exists because the ML scorer ran (it populates `image_score`, `description_score`, etc.) but the stock collection task has not run yet. The row has `in_stock = NULL` and `warehouse_qty = NULL`.

**Handling:** The query includes `.where(ContentScoreRead.in_stock.is_not(None))`. These rows are silently excluded. The workbook contains only rows where a stock task has produced a result.

**Why this is correct:** Showing a row with `in_stock = NULL` and no fill would be indistinguishable from a data error. The feature is named "stock export" — rows with no stock data are not relevant.

---

### NULL plan_tt_count — No Plan for This Week

**Case:** A stock fact row exists for SKU × Platform on 2026-01-15 (ISO week 3), but no distribution plan was uploaded for that SKU × Platform × Week 3.

**Handling:** The LEFT JOIN returns `NULL` for `plan_tt_count`. The `StockRow.plan_tt_count` is `Optional[int]`. In `_build_stock_workbook`, `_fmt_int(None)` returns `"—"`. The cell value is the string dash.

**User experience:** The row appears in the export with all stock fact columns populated and "—" in the Plan (ТТ) column. The row is NOT omitted. This is the correct behavior — the absence of a plan is itself informative.

---

### ISO Week vs Calendar Week Edge Case

**Case:** `scored_at = 2026-01-01` (Thursday). In PostgreSQL, `EXTRACT(week FROM '2026-01-01')` returns `1` (ISO week 1 of 2026). In SQLite, `strftime('%W', '2026-01-01')` returns `00` (week 0 — days before the first Monday are week 0 in SQLite's convention).

**Impact:** In tests using SQLite, a plan with `week_number = 0` would match `strftime('%W', '2026-01-01') = '00'`. In production with PostgreSQL, `EXTRACT(week FROM '2026-01-01') = 1`.

**Current state:** The tests do not test the LEFT JOIN matching at repository level (they test the workbook rendering with pre-built `StockRow` objects). The discrepancy exists but does not cause test failures. In production, PostgreSQL ISO week semantics apply consistently.

**Recommendation (deferred):** Add a repository-level integration test with PostgreSQL to verify the week match for boundary dates (Jan 1, Dec 31). Document the SQLite/PostgreSQL week divergence in test fixtures.

---

### Cross-Tenant Isolation via Indirect Join

**Case:** An attacker (Org B user) requests the stock export. `content_scores` has no `org_id` column. Without the `WHERE skus.org_id = :org_id` filter, all organizations' stock data would be exposed.

**Handling:** The filter `WHERE skus.org_id == org_id` is mandatory and applied at the ORM join chain (`content_scores → sku_platforms → skus → WHERE skus.org_id`). The `org_id` is taken from `current_user.org_id` (decoded from JWT) — it cannot be supplied by the client.

**Test coverage:** The E2E test suite includes `test_stock_export_requires_authentication` but does not include a cross-tenant isolation test at the DB query level. This is a gap (see Review Report).

---

### Empty Result — Header-Only Workbook

**Case:** The query returns zero rows (no stock data collected for the requested period/platform, or org has no SKUs yet).

**Handling:** `build_stock_export` passes an empty `rows=[]` list to `_build_stock_workbook`. The function still writes row 1 (period header), row 2 (column headers), applies freeze panes, and sets auto-filter. No data rows are written. The returned workbook is valid and openable.

**Why not a 404?** An empty date range is not an error — it may simply mean collection is in progress or the org is new. Returning a valid workbook is consistent with the content-export behavior and avoids client-side error handling for a normal state.

---

### DistributionPlan Table Conflict Resolution

**Case:** SQLAlchemy maintains a registry of mapped tables. When `app.reports.repository` imports `DistributionPlan` from `app.stock.models`, it uses the same `Base` and the same `__tablename__ = "distribution_plans"`. If a second class with `__tablename__ = "distribution_plans"` were defined anywhere, SQLAlchemy would raise `InvalidRequestError: Table 'distribution_plans' is already defined for this MetaData instance`.

**Handling:** The reports domain does NOT define its own `DistributionPlan` class. It imports the existing one with an alias:

```python
from app.stock.models import DistributionPlan as DistributionPlanRead
```

The alias is for readability only — it signals that writes are not intended in this context. No `extend_existing=True` workaround is needed because no duplicate definition exists.

---

### Ordering Stability with NULL Articles

**Case:** Some SKUs have `article = NULL` (the field is optional in the catalog). `ORDER BY skus.article` with NULLs is undefined by default in PostgreSQL (NULLs sort last by default, but this is implementation-dependent).

**Handling:** The ORDER BY clause uses `.order_by(SKU.article.nulls_last())`. SQLite also supports `NULLS LAST` in modern versions. SKUs without an article appear at the end of each brand group.

---

## Security Considerations

### Tenant Isolation
- `org_id` is never supplied by the client — it is always read from `current_user.org_id` (JWT payload)
- The JOIN chain enforces isolation: `content_scores` has no `org_id`, so all rows must be reached through `sku_platforms → skus → WHERE skus.org_id`
- PostgreSQL RLS policies provide a defense-in-depth second layer

### Output Safety
- Excel cell values come from the database: brand names, SKU names, platform names — all from the org's own catalog
- No user-supplied strings are written to cells without sanitisation
- `openpyxl` does not evaluate formulas on write — no formula injection risk

### Rate Limiting Gap
- No per-org or per-user rate limiting is applied to the export endpoint
- A user could repeatedly request large exports and exhaust DB connection pool
- Mitigation: the 366-day cap limits query scope; production Nginx can add rate limiting

---

## Performance Considerations

### func.extract Per Row
The LEFT JOIN ON condition calls `func.extract("week", ...)` and `func.extract("year", ...)` for every candidate row. These are cheap arithmetic operations on PostgreSQL (no index scan). For the typical case (30-day export, ~500 SKUs × 5 platforms = 75k rows), this adds negligible overhead.

### Missing Index on content_scores.scored_at
The query filters `content_scores.scored_at` in a range condition. If no index exists on `content_scores(sku_platform_id, scored_at)`, PostgreSQL will perform a sequential scan on the content_scores table filtered by date, then hash-join to sku_platforms. For large tables this can be slow. A composite index `(sku_platform_id, scored_at)` would support both the JOIN and the date range filter.

### Distribution Plan Join Performance
The LEFT JOIN on `distribution_plans` uses the unique constraint index `uq_distribution_plans_key (sku_id, platform_id, week_number, year)` for lookups. This is an O(1) lookup per stock row — no performance concern.

---

## Testing Strategy

### Covered by test_stock_export_api.py

| Test | Coverage |
|------|---------|
| `test_stock_export_requires_authentication` | 401 on missing JWT |
| `test_stock_export_missing_dates_returns_422` | 422 on absent params |
| `test_stock_export_date_to_before_date_from_returns_400` | date validation |
| `test_stock_export_range_exceeds_limit_returns_400` | 366-day cap |
| `test_stock_export_returns_xlsx_content_type` | content-type + filename headers |
| `test_stock_export_viewer_role_allowed` | viewer RBAC |
| `test_stock_workbook_has_correct_headers` | workbook structure |
| `test_stock_workbook_in_stock_row_is_green` | green fill |
| `test_stock_workbook_out_of_stock_row_is_red` | red fill |
| `test_stock_workbook_null_in_stock_no_fill` | no-fill guard |
| `test_stock_workbook_missing_plan_shows_dash` | NULL plan → "—" |
| `test_stock_workbook_in_stock_field_formatted_as_da_or_net` | "Да"/"Нет" formatting |

### Gaps

| Gap | Severity | Notes |
|-----|---------|-------|
| No cross-tenant isolation test at repository level | Major | Org B query should return empty — currently not tested |
| No LEFT JOIN matching test with real DB | Moderate | Plan with week=3 should appear in StockRow.plan_tt_count; tested only via workbook unit test with pre-built StockRow |
| No ISO week boundary test (Jan 1, Dec 31) | Minor | Only matters with PostgreSQL; SQLite divergence documented above |
| No 500-error path test | Minor | Exception handler logs and returns INTERNAL_ERROR; not tested |
