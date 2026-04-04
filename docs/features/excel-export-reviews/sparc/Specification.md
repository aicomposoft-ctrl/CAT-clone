# Specification: Excel Export — Reviews

**Feature:** `excel-export-reviews`
**Date:** 2026-04-04

---

## API Endpoint

### GET /api/v1/reports/reviews-export

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date_from` | `date` (YYYY-MM-DD) | Yes | Start date, inclusive (by `review_date`) |
| `date_to` | `date` (YYYY-MM-DD) | Yes | End date, inclusive; must be >= `date_from` |
| `platform_id` | `UUID` | No | Narrows results to a single platform |
| `sentiment` | `"positive" \| "neutral" \| "negative"` | No | Narrows results to a single sentiment label |
| `sku_id` | `UUID` | No | Narrows results to a single SKU (must belong to caller's org) |

#### Success Response — HTTP 200

```
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="reviews_{date_from}_{date_to}.xlsx"
Content-Length: <byte count>

<binary .xlsx body>
```

#### Error Responses

| Status | Condition | Detail |
|--------|-----------|--------|
| 400 | `date_to < date_from` | `INVALID_DATE_RANGE: date_to must be >= date_from` |
| 400 | Range > 366 days | `INVALID_DATE_RANGE: maximum range is 366 days` |
| 401 | Missing or invalid JWT | (FastAPI security dependency) |
| 404 | `sku_id` provided but SKU not found or not owned by caller's org | `SKU_NOT_FOUND` |
| 422 | Missing `date_from` or `date_to`; malformed date; non-UUID; invalid sentiment enum | FastAPI validation error body |
| 500 | Unhandled exception in service or repository | `INTERNAL_ERROR` |

---

## Excel Workbook Structure

### Sheet Name

`Reviews`

### Row Layout

| Row | Content |
|-----|---------|
| 1 | Merged A1:I1 — period sub-header: `"Отчёт по отзывам: {date_from} — {date_to}"` |
| 2 | Column headers (bold, blue fill #4472C4, white font) |
| 3+ | Data rows |

### Column Definitions

| # | Header | Source Field | Width (chars) | Type |
|---|--------|-------------|---------------|------|
| 1 | Бренд | `brand_name` | 20 | String |
| 2 | Артикул | `sku_article` | 15 | String (or `—` if NULL) |
| 3 | Название SKU | `sku_name` | 40 | String |
| 4 | Платформа | `platform_name` | 20 | String |
| 5 | Дата отзыва | `review_date` | 14 | ISO date string (YYYY-MM-DD) |
| 6 | Рейтинг | `rating` | 10 | Integer (1–5) or `—` if NULL |
| 7 | Тональность | `sentiment` | 14 | `"positive"` / `"neutral"` / `"negative"` or `—` if NULL |
| 8 | Оценка тональности | `sentiment_score` | 20 | `"0.000"` – `"1.000"` formatted to 3 d.p., or `—` if NULL |
| 9 | Текст отзыва | `review_text` | 60 | String, truncated to 500 chars if longer (with `…` suffix) |

### Workbook Features

- Header row height: 30 points
- Frozen panes at A3 (header rows always visible when scrolling)
- Auto-filter on header row A2:I2
- Header fill: `PatternFill("solid", fgColor="4472C4")`
- Header font: Calibri bold, white (#FFFFFF)
- Body font: Calibri size 11
- Body vertical alignment: center
- Row wrap text: enabled for column 9 (review text)

### Sentiment Color Coding

| Sentiment | Cell Background (columns 7–8) |
|-----------|------------------------------|
| `positive` | Green — `#C6EFCE` |
| `neutral` | Yellow — `#FFEB9C` |
| `negative` | Red — `#FFC7CE` |
| NULL (unscored) | No fill |

Color is applied to columns 7 (Тональность) and 8 (Оценка тональности) only — not the full row.

---

## Data Query

### Source Tables

```
reviews r
  JOIN sku_platforms sp  ON sp.id = r.sku_platform_id
  JOIN skus s            ON s.id  = sp.sku_id          ← org_id filter
  JOIN brands b          ON b.id  = s.brand_id
  JOIN platforms p       ON p.id  = sp.platform_id
```

### Mandatory Filters

- `s.org_id = :org_id` — tenant isolation
- `r.review_date BETWEEN :date_from AND :date_to`

### Optional Filters

- `sp.platform_id = :platform_id` — when `platform_id` is provided
- `r.sentiment = :sentiment` — when `sentiment` is provided
- `s.id = :sku_id` — when `sku_id` is provided

### Sort Order

```sql
ORDER BY b.name ASC, s.article ASC NULLS LAST, p.name ASC, r.review_date DESC
```

### Row Limit

10,000 rows maximum per export. If the result set exceeds 10,000 rows, a warning row is appended:
```
Row 10,003: "⚠ Превышен лимит 10 000 строк. Используйте фильтры для сужения выборки."
```
(merged A:I, yellow fill, bold)

---

## BDD Scenarios

### Scenario 1: Basic export returns correct sheet structure
```gherkin
Given an authenticated manager with org reviews in the DB
When GET /api/v1/reports/reviews-export?date_from=2026-01-01&date_to=2026-03-31
Then response status is 200
And Content-Type is application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
And Content-Disposition contains "reviews_2026-01-01_2026-03-31.xlsx"
And the workbook has a sheet named "Reviews"
And row 1 is merged A1:I1 with period header text
And row 2 has 9 column headers
And data rows start at row 3
```

### Scenario 2: Sentiment color coding
```gherkin
Given reviews with sentiment positive, neutral, negative, and NULL
When the export is downloaded
Then positive rows have columns 7–8 filled with #C6EFCE
And neutral rows have columns 7–8 filled with #FFEB9C
And negative rows have columns 7–8 filled with #FFC7CE
And NULL sentiment rows have no fill on columns 7–8
```

### Scenario 3: No reviews returns header-only workbook
```gherkin
Given no reviews exist in the date range
When GET /api/v1/reports/reviews-export?date_from=2026-01-01&date_to=2026-01-01
Then response status is 200
And the workbook has 2 rows (merged header + column headers)
And no data rows are present
```

### Scenario 4: Sentiment filter
```gherkin
Given reviews with mixed sentiment (positive, negative, neutral)
When GET /api/v1/reports/reviews-export?...&sentiment=negative
Then only negative reviews appear in the export
And the export does not contain positive or neutral rows
```

### Scenario 5: Platform filter
```gherkin
Given reviews across 3 platforms
When GET /api/v1/reports/reviews-export?...&platform_id=<uuid>
Then only reviews from that platform appear
```

### Scenario 6: SKU filter - owned SKU
```gherkin
Given sku_a belongs to org_a
And user is authenticated as manager of org_a
When GET /api/v1/reports/reviews-export?...&sku_id=<sku_a.id>
Then only reviews for sku_a appear
And status is 200
```

### Scenario 7: SKU filter - cross-tenant
```gherkin
Given sku_b belongs to org_b
And user is authenticated as manager of org_a
When GET /api/v1/reports/reviews-export?...&sku_id=<sku_b.id>
Then response status is 404
And detail is "SKU_NOT_FOUND"
```

### Scenario 8: Invalid date range
```gherkin
When GET /api/v1/reports/reviews-export?date_from=2026-03-01&date_to=2026-01-01
Then response status is 400
And detail contains "INVALID_DATE_RANGE"
```

### Scenario 9: Date range over 366 days
```gherkin
When GET /api/v1/reports/reviews-export?date_from=2025-01-01&date_to=2026-06-01
Then response status is 400
And detail contains "366"
```

### Scenario 10: Unauthenticated request
```gherkin
When GET /api/v1/reports/reviews-export?date_from=...&date_to=...  (no JWT)
Then response status is 401
```

### Scenario 11: Viewer role can download
```gherkin
Given user has role "viewer"
When GET /api/v1/reports/reviews-export?date_from=...&date_to=...
Then response status is 200
```

### Scenario 12: Review text truncation
```gherkin
Given a review with review_text of 600 characters
When the export is downloaded
Then column 9 for that row contains the first 500 characters followed by "…"
```

### Scenario 13: Rating NULL formatted as dash
```gherkin
Given a review with rating = NULL
When the export is downloaded
Then column 6 (Рейтинг) shows "—"
```

### Scenario 14: Cross-tenant isolation (no sku_id filter)
```gherkin
Given manager_b (org_b) makes request without sku_id filter
When GET /api/v1/reports/reviews-export?date_from=...&date_to=...
Then only org_b reviews appear (org_a reviews are not returned)
```

### Scenario 15: Row limit warning
```gherkin
Given 10,001 reviews exist in the date range
When the export is downloaded
Then the workbook contains exactly 10,000 data rows
And row 10,003 contains the limit warning message
```

### Scenario 16: platform_id from different org returns empty workbook (not 404)
```gherkin
Given platform_id belongs to a valid platform with reviews for org_b
And user is authenticated as manager of org_a
When GET /api/v1/reports/reviews-export?...&platform_id=<platform_id>
Then response status is 200
And the workbook contains only header rows (no data rows for org_b's reviews)
```
