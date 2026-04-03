# Specification: Excel Export — Content Scores

**Feature:** `excel-export-content`
**Date:** 2026-04-02

---

## API Endpoint

### GET /api/v1/reports/content-export

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date_from` | `date` (YYYY-MM-DD) | Yes | Start date, inclusive |
| `date_to` | `date` (YYYY-MM-DD) | Yes | End date, inclusive; must be >= `date_from` |
| `platform_id` | `UUID` | No | Narrows results to a single platform |

#### Success Response — HTTP 200

```
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="content_scores_{date_from}_{date_to}.xlsx"
Content-Length: <byte count>

<binary .xlsx body>
```

#### Error Responses

| Status | Condition | Detail |
|--------|-----------|--------|
| 400 | `date_to < date_from` | `INVALID_DATE_RANGE: date_to must be >= date_from` |
| 400 | Range > 366 days | `INVALID_DATE_RANGE: maximum range is 366 days` |
| 401 | Missing or invalid JWT | (FastAPI security dependency) |
| 422 | Missing `date_from` or `date_to`; malformed date; non-UUID `platform_id` | FastAPI validation error body |
| 500 | Unhandled exception in service or repository | `INTERNAL_ERROR` |

---

## Excel Workbook Structure

### Sheet Name

`Content Scores`

### Row Layout

| Row | Content |
|-----|---------|
| 1 | Merged A1:I1 — period sub-header: `"Отчёт по контенту: {date_from} — {date_to}"` |
| 2 | Column headers (bold, blue fill #4472C4, white font) |
| 3+ | Data rows |

### Column Definitions

| # | Header | Source Field | Width (chars) | Type |
|---|--------|-------------|---------------|------|
| 1 | Бренд | `brand_name` | 20 | String |
| 2 | Артикул | `sku_article` | 15 | String (or `—` if NULL) |
| 3 | Название SKU | `sku_name` | 40 | String |
| 4 | Платформа | `platform_name` | 20 | String |
| 5 | Дата оценки | `scored_at` | 14 | ISO date string (YYYY-MM-DD) |
| 6 | Оценка изображения | `image_score` | 20 | String (`n.n` or `—`) |
| 7 | Оценка описания | `description_score` | 18 | String (`n.n` or `—`) |
| 8 | Оценка состава | `composition_score` | 17 | String (`n.n` or `—`) |
| 9 | Итого контент | `content_total` | 16 | String (`n.n` or `—`) |

### Workbook Features

- Header row height: 30 points
- Frozen panes at A3 (header rows always visible when scrolling)
- Auto-filter on header row A2:I2
- Header fill: `PatternFill("solid", fgColor="4472C4")`
- Header font: Calibri bold, white (#FFFFFF)
- Body font: Calibri size 11
- Body vertical alignment: center

---

## Color Coding Rules

Color is applied to **all score columns (6–9)** based on `content_total` value only:

| Condition | Fill Color (hex) | Meaning |
|-----------|-----------------|---------|
| `content_total >= 80` | `#C6EFCE` (green) | Good content quality |
| `50 <= content_total < 80` | `#FFEB9C` (yellow) | Acceptable, improvement needed |
| `content_total < 50` | `#FFC7CE` (red) | Poor content quality |
| `content_total IS NULL` | No fill | ML scores not yet computed |

Score values are formatted as strings with one decimal place (`f"{value:.1f}"`). NULL scores are rendered as `—` (em-dash).

---

## Date Range Validation Rules

Applied in `_validate_date_range()` before any service call:

1. **Reversed range:** `if date_to < date_from` → HTTP 400
2. **Excessive range:** `if (date_to - date_from).days > 366` → HTTP 400

Both conditions return `detail` strings prefixed with `INVALID_DATE_RANGE:` to allow clients to distinguish this error from other 400s.

Maximum range constant: `_MAX_DATE_RANGE_DAYS = 366`

---

## Null Handling

| Field | NULL Rendered As |
|-------|-----------------|
| `sku_article` | `"—"` |
| `image_score` | `"—"` |
| `description_score` | `"—"` |
| `composition_score` | `"—"` |
| `content_total` | `"—"` (and no fill applied) |

---

## Security Constraints

- `current_user.org_id` is always passed as the `org_id` parameter to the service — never a user-supplied value
- Date parameters are FastAPI `date` types — FastAPI validates format before handler runs
- `platform_id` is FastAPI `Optional[UUID]` — invalid UUID formats return 422 before handler runs
- All SQL queries use SQLAlchemy ORM parameterized queries — no string interpolation

---

## Response Filename Convention

```
content_scores_{date_from}_{date_to}.xlsx
```

Examples:
- `content_scores_2026-01-01_2026-01-31.xlsx`
- `content_scores_2026-01-01_2026-12-31.xlsx`
