# Architecture: Excel Export — Stock Distribution

**Feature:** `excel-export-stock`
**Date:** 2026-04-02

---

## Module Placement

This feature extends the existing `reports` module. It does not introduce new modules or migrations. All additions are:

| File | Change |
|------|--------|
| `services/api/app/reports/repository.py` | Add `StockRow` dataclass + `get_stock_data_for_export()` |
| `services/api/app/reports/service.py` | Add `_STOCK_COLUMNS`, `_STOCK_FILLS`, `_fmt_bool`, `_fmt_int`, `_stock_row_fill`, `_build_stock_workbook`, `build_stock_export` |
| `services/api/app/reports/router.py` | Add `export_stock_data` route at `GET /stock-export` + shared `_validate_date_range()` helper |
| `services/api/app/reports/models.py` | Read-only model only — no change needed for stock export (uses `ContentScoreRead` already) |

No new database migrations. No new Alembic revisions. No frontend changes.

---

## Layer Architecture

```
HTTP Layer (router.py)
  ↓  validates date range, extracts org_id from JWT
Service Layer (service.py)
  ↓  calls repository, builds workbook, returns bytes
Repository Layer (repository.py)
  ↓  SQLAlchemy async query → list[StockRow]
Database (PostgreSQL)
  content_scores JOIN sku_platforms JOIN skus JOIN brands JOIN platforms
  LEFT JOIN distribution_plans (ISO week match)
```

The router is thin: it validates parameters and delegates entirely to `service.build_stock_export`. The service has no HTTP concerns. The repository has no Excel concerns.

---

## JOIN Chain and Tenant Isolation

The `content_scores` table has **no `org_id` column**. Tenant isolation is enforced by the join path:

```
content_scores.sku_platform_id
  → sku_platforms.id
  → sku_platforms.sku_id
  → skus.id  ← WHERE skus.org_id = :org_id  ← ISOLATION POINT
```

This is the same isolation pattern used for the content export query. Any attempt to query `content_scores` directly without going through `skus` would bypass tenant isolation — this is why the reports module uses `ContentScoreRead` (a read-only mapping) and always JOINs through `sku_platforms → skus`.

---

## Distribution Plan Model Reuse

The `distribution_plans` table is owned by the `stock` domain. Rather than defining a duplicate SQLAlchemy mapping in the reports domain, the reports module imports the existing model directly:

```python
from app.stock.models import DistributionPlan as DistributionPlanRead
```

The alias `DistributionPlanRead` signals intent (read-only in this context) without duplicating the class. Using `extend_existing=True` or creating a second `__tablename__ = "distribution_plans"` mapping would raise SQLAlchemy's "table already defined" error at startup.

---

## ISO Week Extraction Strategy

The LEFT JOIN condition must match `distribution_plans.week_number` to the ISO week of `content_scores.scored_at`. This requires a computed expression, not a stored column:

```python
func.extract("week", ContentScoreRead.scored_at)
```

This expression appears **twice** in the query:
1. In the `SELECT` clause (labeled `week_num` and `year_num`) for the `StockRow` dataclass
2. In the `LEFT JOIN ON` condition for the plan match

SQLAlchemy compiles `func.extract` to:
- PostgreSQL: `EXTRACT(week FROM content_scores.scored_at)` — ISO 8601 week (1-53)
- SQLite: `strftime('%W', content_scores.scored_at)` — week 00-53

This dual-dialect compatibility allows the same query to run in production (PostgreSQL) and in tests (SQLite in-memory), without conditional logic or fixture tricks.

---

## Shared Date Range Validator

Both export endpoints (`/content-export` and `/stock-export`) share the same validation helper:

```python
def _validate_date_range(date_from: date, date_to: date) -> None:
    if date_to < date_from: raise HTTPException(400, ...)
    if (date_to - date_from).days > _MAX_DATE_RANGE_DAYS: raise HTTPException(400, ...)
```

`_MAX_DATE_RANGE_DAYS = 366` — allows a full year including leap days while preventing runaway queries on large orgs.

The helper raises `HTTPException` directly because it is called from the router layer (acceptable — service layer raises `ValueError` / `PermissionError`).

---

## Excel Generation (In-Memory)

```
build_stock_export()
  → get_stock_data_for_export()  [async, returns list[StockRow]]
  → _build_stock_workbook(rows, date_from, date_to)  [sync, returns Workbook]
  → io.BytesIO() → wb.save(buf) → buf.read()  [returns bytes]
```

The `BytesIO` buffer is created, written, and read within `build_stock_export`. It is not stored anywhere after the function returns. The workbook object is also dereferenced. This means peak memory = size of one workbook + the returned bytes (brief overlap), after which both are garbage collected.

The caller (`export_stock_data` in router.py) passes the bytes directly to `fastapi.Response(content=xlsx_bytes, ...)`. FastAPI does not buffer this further — it streams immediately to the client.

---

## Concurrency Safety

`_build_stock_workbook` is a pure synchronous function with no shared state. The `PatternFill` objects (`_STOCK_FILLS`, `_HEADER_FILL`) are module-level constants shared across requests. `openpyxl` fill objects are read-only after creation — no mutation risk.

`build_stock_export` is `async` but contains only one `await` (the DB query). The synchronous workbook building does not block the event loop for realistic data volumes (< 50k rows for a 30-day export of a large org).

---

## File Locations

| Component | Path |
|-----------|------|
| Route handler | `services/api/app/reports/router.py` |
| Service (Excel gen) | `services/api/app/reports/service.py` |
| Repository (DB query) | `services/api/app/reports/repository.py` |
| Read-only ORM models | `services/api/app/reports/models.py` |
| Stock domain model (reused) | `services/api/app/stock/models.py` |
| E2E tests | `services/api/tests/e2e/test_stock_export_api.py` |
