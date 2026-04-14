# Refinement: Excel Export — Content Scores

**Feature:** `excel-export-content`
**Date:** 2026-04-02

---

## Edge Cases

### Repository Layer

| Case | Handling |
|------|---------|
| No content scores match the date range | Returns empty `[]` — service produces header-only workbook, not an error |
| `platform_id` is a valid UUID but matches no platform | Query returns `[]` — same handling as empty result |
| `sku_article` is NULL | Rendered as `"—"` in Excel cell |
| Any score column is NULL | `_fmt_score(None)` returns `"—"`; `_score_fill(None)` returns `None` (no fill applied) |
| All score columns NULL for a row | Row gets no color fill on columns 6–9 |
| Scores partially NULL (e.g., `image_score` set but `content_total` NULL) | `content_total` drives the fill decision; partially scored row gets no fill |
| Platform deleted after score was recorded | Cannot happen — INNER JOIN requires platform row to exist (FK + CASCADE behavior) |
| Brand deleted after score was recorded | Cannot happen — INNER JOIN requires brand row to exist |

### Router Layer

| Case | Handling |
|------|---------|
| `date_to < date_from` | HTTP 400, detail `INVALID_DATE_RANGE: date_to must be >= date_from` |
| `(date_to - date_from).days > 366` | HTTP 400, detail `INVALID_DATE_RANGE: maximum range is 366 days` |
| `date_from == date_to` | Valid (single-day export) |
| `date_to - date_from == 366 days` | Valid (at the boundary) |
| `date_to - date_from == 367 days` | Invalid (exceeds limit by 1 day) |
| Missing `date_from` | FastAPI returns HTTP 422 before router handler runs |
| Missing `date_to` | FastAPI returns HTTP 422 before router handler runs |
| Malformed date string (e.g. `2026-13-45`) | FastAPI returns HTTP 422 |
| Non-UUID `platform_id` | FastAPI returns HTTP 422 |
| No JWT token | `get_current_user` dependency raises HTTP 401 |
| Expired JWT | `get_current_user` dependency raises HTTP 401 |
| Unhandled exception in service | Caught by `except Exception`, logged server-side, HTTP 500 with `INTERNAL_ERROR` |

---

## Large Dataset Handling

For organisations with large SKU catalogues (1000+ rows per export):

- The repository query returns all rows in a single SQL query — no pagination (this is an export, not a paginated list)
- openpyxl builds the workbook row by row in memory — O(n) memory
- For 10,000 rows at ~9 cells per row, memory overhead is approximately 10–50 MB (acceptable for a VPS deployment)
- No streaming row-by-row write is used (openpyxl's streaming mode exists but was not implemented — see known limitation below)

**Known Limitation:** For very large exports (50,000+ rows), openpyxl's default write mode holds the entire workbook in memory. If this becomes a problem, migration to `openpyxl.writer.excel.ExcelWriter` with `write_only=True` mode is the fix.

---

## openpyxl Column Width Gotcha

From `.claude/rules/coding-style.md`:

> openpyxl column widths: Must be set explicitly after writing data — `Worksheet.column_dimensions[col].width`. Auto-size not supported.

The implementation sets widths during header row construction (row 2 loop), not after all data rows are written. This is correct — `column_dimensions` is not data-dependent in this case because widths are fixed constants defined in `_COLUMNS`.

If auto-sizing is needed in the future, the workaround is to iterate all rows after writing and compute `max(len(str(cell.value)))` per column, then set `column_dimensions` accordingly.

---

## Multi-Tenant Isolation Test

The critical security property: an export for Org A must never include rows belonging to Org B, even if a user somehow supplies Org B's `org_id` (which is prevented by always using `current_user.org_id`).

Test scenario (`test_content_export_cross_tenant_isolation`):

```
Setup:
  - Create Org A and Org B
  - Create Brand A (org_id=A), Brand B (org_id=B)
  - Create SKU A (org_id=A), SKU B (org_id=B)
  - Create SKUPlatform entries for both SKUs on the same platform
  - Create ContentScore for SKU A (content_total=85) and SKU B (content_total=72)
  - Same scored_at date for both

Query:
  get_content_scores_for_export(db, org_id=ORG_A_ID, date_from=..., date_to=...)

Assert:
  len(rows) == 1
  rows[0].sku_article == "A-001"     # only Org A's data
  rows[0].brand_name == "Brand A"    # Org B's score is not present
```

This test is implemented in `services/api/tests/e2e/test_reports_api.py`.

---

## NULL Score Display Test

Test scenario (`test_build_workbook_null_scores_no_fill`):

```
Setup:
  Row with all score fields = None

Build workbook and check:
  - Cell value at column 6-9 = "—"
  - Fill type for column 9 is None/"none" (no color applied)
```

Implemented in `test_reports_api.py::test_build_workbook_null_scores_no_fill`.

---

## Color Coding Tests

Three content_total values tested explicitly:

| content_total | Expected fill hex |
|---------------|------------------|
| `85.00` | `C6EFCE` (green) |
| `55.00` | `FFEB9C` (yellow) |
| `25.00` | `FFC7CE` (red) |

Boundary values not explicitly tested: `80.0` (green/yellow boundary) and `50.0` (yellow/red boundary). The `>=` operator means `80.0` is green and `50.0` is yellow.

---

## Security Considerations

- `org_id` comes exclusively from `current_user.org_id` (JWT claim) — not from any query parameter. Even if a malicious user were to construct a request with a different org's UUID, the router ignores it.
- `platform_id` is validated as a UUID type by FastAPI before reaching the handler — SQL injection via this parameter is impossible with SQLAlchemy parameterized queries.
- Score data is read from CAT's own database (not from scraped external input) — no XSS or injection risk in Excel cell values.
- Large file generation could be a DoS vector (slow 366-day export for large orgs) — mitigated by the 366-day maximum and by inheriting the 100 req/min global rate limit.

---

## Testing Strategy Summary

| Test | File | Type |
|------|------|------|
| Unauthenticated → 401 | `test_reports_api.py` | E2E |
| Missing date params → 422 | `test_reports_api.py` | E2E |
| `date_to < date_from` → 400 | `test_reports_api.py` | E2E |
| Range > 366 days → 400 | `test_reports_api.py` | E2E |
| Valid request → 200 + xlsx Content-Type | `test_reports_api.py` | E2E |
| Valid request → Content-Disposition filename | `test_reports_api.py` | E2E |
| Viewer role → 200 (allowed) | `test_reports_api.py` | E2E |
| Cross-tenant isolation | `test_reports_api.py` | Integration |
| Header row structure | `test_reports_api.py` | Unit |
| Color coding green/yellow/red | `test_reports_api.py` | Unit |
| NULL scores → no fill, em-dash | `test_reports_api.py` | Unit |

Missing test coverage (follow-up):
- Boundary values for color thresholds (`content_total == 80.0`, `content_total == 50.0`)
- `platform_id` filter narrows rows correctly (integration test with fixture data)
- `Content-Length` header matches actual byte count
- Workbook readable by openpyxl after round-trip (bytes → `load_workbook`)
