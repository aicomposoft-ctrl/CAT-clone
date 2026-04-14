# Refinement: Excel Export — Reviews

**Feature:** `excel-export-reviews`
**Date:** 2026-04-04

---

## Risk Register

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|-----------|--------|------------|
| R1 | Large review volumes (>10K rows) cause memory spike | Medium | Medium | Hard row cap at 10,000; warning row appended; BytesIO in-memory |
| R2 | `review_text` contains XSS-like content rendered as HTML in Excel | Low | Low | openpyxl writes plain text cells — no HTML rendering by Excel |
| R3 | `Review` ORM import in `reports/repository.py` creates circular dependency | Low | Medium | Local import inside function body avoids top-level circular import |
| R4 | `sentiment_score` is Decimal; serialisation precision varies | Low | Low | Formatted explicitly to 3 d.p. via `f"{value:.3f}"` |
| R5 | Cross-tenant data leak via `sku_id` param | Low | Critical | `SKURepository.get_by_id_and_org()` validates org_id before query |

---

## Edge Cases

### Empty date range (same day)
- `date_from == date_to` is valid — returns reviews from that single day
- `date_to < date_from` → HTTP 400

### All reviews already scored (all have sentiment)
- Normal case — export includes sentiment fill on all rows

### Reviews with NULL sentiment
- Unscored reviews are included by default (no filter)
- No fill on columns 7–8
- `—` in columns 7 and 8

### review_text is NULL or empty string
- `_fmt_text(None)` → `"—"`
- `_fmt_text("")` → `"—"`

### review_text exactly 500 chars
- Not truncated (truncation only for > 500)

### sku_id provided, SKU belongs to caller's org, SKU has no reviews
- Repo returns empty list, `truncated=False`
- Header-only workbook returned with HTTP 200

### sku_id provided, belongs to different org
- `SKURepository.get_by_id_and_org()` returns None → HTTP 404
- Query never reaches repository

### sentiment filter with no matching reviews
- Returns header-only workbook (HTTP 200)

### Exactly 10,000 reviews
- `len(raw) == 10,000` → `truncated = False` (no warning row)
- All 10,000 rows included

### Exactly 10,001 reviews
- `len(raw) == 10,001` → `truncated = True`
- 10,000 rows + warning row

---

## Technical Debt

### validate_date_range duplication
`reports/router.py` has its own `_validate_date_range` (shared by content-export, stock-export, and now reviews-export). The `reviews/router.py` and `prices/router.py` each have their own copies. Extraction into `app.core.utils` is a clean-up task for a future sprint.

### Review ORM model location
`Review` model lives in `app.reviews.models`. The `reports` domain imports it via a local import to avoid circular dependency (`app.reports.repository` → `app.reviews.models`). If the reports domain grows further, consider an explicit `app.catalog.review_models` shim or restructuring.

---

## Implementation Ordering

1. **repository.py** — add `ReviewRow`, `get_reviews_for_export()` (independent)
2. **service.py** — add `_build_reviews_workbook()`, `build_reviews_export()` (depends on 1)
3. **router.py** — add `export_reviews()` endpoint (depends on 2)
4. **tests** — e2e tests + workbook unit tests (can be written in parallel with 1–3)

No DB migration. No `main.py` change.

---

## Definition of Done

- [ ] `GET /api/v1/reports/reviews-export` returns valid `.xlsx` with correct MIME type
- [ ] Sentiment color coding applied to columns 7–8 only
- [ ] `sku_id` ownership validated (404 on mismatch)
- [ ] `org_id` filter present in repository query
- [ ] Row limit warning row appended when result > 10,000
- [ ] Review text truncated to 500 chars with `…`
- [ ] Empty result returns header-only workbook (not 404)
- [ ] E2E tests cover: happy path, empty, sentiment filter, platform filter, sku_id cross-tenant 404, date 400, unauth 401
- [ ] Workbook unit tests cover: color coding, truncation, warning row, NULL handling
