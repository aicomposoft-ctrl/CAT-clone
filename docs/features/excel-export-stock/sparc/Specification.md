# Specification: Excel Export — Stock Distribution

**Feature:** `excel-export-stock`
**Date:** 2026-04-02

---

## API Endpoint

### GET /api/v1/reports/stock-export

**Summary:** Export stock distribution data to Excel

**Auth:** JWT Bearer token required (any role: admin, manager, viewer)

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date_from` | `date` (YYYY-MM-DD) | Yes | Start date, inclusive |
| `date_to` | `date` (YYYY-MM-DD) | Yes | End date, inclusive |
| `platform_id` | `UUID` | No | Narrow to a single platform |

**Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| 200 | Success (even if 0 rows) | Binary `.xlsx` stream |
| 400 | `date_to < date_from` or range > 366 days | `{"detail": "INVALID_DATE_RANGE: ..."}` |
| 401 | Missing or invalid JWT | `{"detail": "Not authenticated"}` |
| 422 | Missing required param or invalid UUID | FastAPI validation error body |
| 500 | Unexpected internal error | `{"detail": "INTERNAL_ERROR"}` |

**Response Headers (200):**

```
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="stock_{date_from}_{date_to}.xlsx"
Content-Length: <bytes>
```

**Date Range Validation:**

Shared helper `_validate_date_range(date_from, date_to)`:
- Raises HTTP 400 if `date_to < date_from`
- Raises HTTP 400 if `(date_to - date_from).days > 366`
- Error detail format: `"INVALID_DATE_RANGE: <reason>"`

---

## Excel Workbook Structure

**Sheet name:** `"Stock"`

**Row 1:** Period header (merged A1:J1)
- Value: `"Отчёт по дистрибуции: {date_from} — {date_to}"`
- Font: Calibri Bold 12pt
- Alignment: center horizontal

**Row 2:** Column headers
- Background fill: solid `#4472C4` (blue)
- Font: Calibri Bold White
- Height: 30px
- Alignment: center horizontal, center vertical, wrap_text=True

**Row 3+:** Data rows (ordered by brand → article → platform → date)

**Freeze panes:** A3

**Auto-filter:** A2:J2

---

## Column Definitions

| # | Header | Source Field | Column Width |
|---|--------|-------------|--------------|
| 1 | Бренд | `brand_name` | 20 |
| 2 | Артикул | `sku_article` (or "—") | 15 |
| 3 | Название SKU | `sku_name` | 40 |
| 4 | Платформа | `platform_name` | 20 |
| 5 | Дата сбора | `scored_at` (ISO string) | 14 |
| 6 | Неделя | `week_number` (int) | 9 |
| 7 | Год | `year` (int) | 7 |
| 8 | В наличии | `in_stock` → "Да" / "Нет" / "—" | 12 |
| 9 | Остаток на складе | `warehouse_qty` → str / "—" | 20 |
| 10 | План (ТТ) | `plan_tt_count` → str / "—" | 12 |

**Formatting functions:**

- `_fmt_bool(value)`: `True` → `"Да"`, `False` → `"Нет"`, `None` → `"—"`
- `_fmt_int(value)`: `None` → `"—"`, otherwise `str(value)`
- All cells: Calibri 11pt, vertical center alignment

---

## Row-Level Color Coding

Color is applied to **all 10 columns** of the data row based on `in_stock` value:

| Condition | Fill Color | Hex |
|-----------|-----------|-----|
| `in_stock = True` | Green | `#C6EFCE` |
| `in_stock = False` | Red | `#FFC7CE` |
| `in_stock = None` | No fill | — |

Implementation: `_stock_row_fill(in_stock: Optional[bool]) -> Optional[PatternFill]`

Note: Rows where `in_stock IS NULL` are excluded from the query result (see Data Query section), so in practice the "no fill" branch in `_stock_row_fill` applies only to the guard against unexpected NULL values that bypass the DB filter.

---

## Data Query Specification

### Source Tables

```
content_scores          (main facts: in_stock, warehouse_qty, scored_at)
  JOIN sku_platforms    ON sku_platform_id = sku_platforms.id
  JOIN skus             ON sku_id = skus.id            ← org_id filter here
  JOIN brands           ON brand_id = brands.id
  JOIN platforms        ON platform_id = platforms.id
  LEFT JOIN distribution_plans
    ON  distribution_plans.sku_id        = skus.id
    AND distribution_plans.platform_id   = sku_platforms.platform_id
    AND distribution_plans.week_number   = EXTRACT(week FROM content_scores.scored_at)
    AND distribution_plans.year          = EXTRACT(year FROM content_scores.scored_at)
```

### Mandatory Filter

```sql
WHERE skus.org_id = :org_id
  AND content_scores.scored_at >= :date_from
  AND content_scores.scored_at <= :date_to
  AND content_scores.in_stock IS NOT NULL
```

### Optional Filter

```sql
-- Applied only when platform_id parameter is provided:
AND sku_platforms.platform_id = :platform_id
```

### Ordering

```sql
ORDER BY brands.name ASC,
         skus.article ASC NULLS LAST,
         platforms.name ASC,
         content_scores.scored_at ASC
```

### ISO Week Extraction

Week and year are computed via `func.extract("week", ...)` and `func.extract("year", ...)`:
- PostgreSQL: maps to `EXTRACT(week FROM ...)` — returns ISO week number (1–53)
- SQLite (tests): maps to `strftime('%W', ...)` — returns week 0-based; equivalent for matching purposes

The same expressions are used in both the SELECT clause (for the StockRow dataclass fields) and the LEFT JOIN ON condition.

---

## Data Projection (StockRow dataclass)

```python
@dataclass(slots=True)
class StockRow:
    brand_name: str
    sku_article: Optional[str]
    sku_name: str
    platform_name: str
    scored_at: date
    week_number: int        # int(func.extract("week", scored_at))
    year: int               # int(func.extract("year", scored_at))
    in_stock: Optional[bool]
    warehouse_qty: Optional[int]
    plan_tt_count: Optional[int]   # NULL when no plan for this SKU×Platform×Week
```

---

## Error Responses

### HTTP 400 — Invalid Date Range

```json
{"detail": "INVALID_DATE_RANGE: date_to must be >= date_from"}
{"detail": "INVALID_DATE_RANGE: maximum range is 366 days"}
```

### HTTP 401 — Unauthenticated

Standard FastAPI/JWT `"Not authenticated"` response.

### HTTP 422 — Missing Parameters

FastAPI default validation error when `date_from` or `date_to` is absent or non-parseable.

### HTTP 500 — Internal Error

```json
{"detail": "INTERNAL_ERROR"}
```

The real exception is logged via `logger.exception(...)` but never exposed to the client.
