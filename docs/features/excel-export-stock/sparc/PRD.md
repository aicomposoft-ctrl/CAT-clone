# PRD: Excel Export — Stock Distribution

**Feature:** `excel-export-stock`
**Date:** 2026-04-02
**Status:** Phase 1 — Planning (retroactive)

---

## Executive Summary

A backend-only Excel export endpoint that lets managers and viewers download a `.xlsx` report combining daily stock facts (in_stock flag, warehouse quantity) with distribution plan targets (planned trade-point count) for the same ISO week. The report is generated in memory with no disk I/O and returned as a streaming binary response. Color-coded rows (green = in stock, red = out of stock) allow at-a-glance reading without chart tooling.

---

## Problem Statement

FMCG brand managers upload distribution plans via CSV (SKU × Platform × Week → planned trade-point count) but have no automated way to compare those targets against actual daily availability scraped from 110+ platforms. Without a combined view, managers must:

- Export stock facts from one system
- Export the plan from another
- Manually VLOOKUP plan quantities onto daily facts in a local spreadsheet

This manual process takes 30–60 minutes per report cycle and is error-prone. The existing content-export feature already proves the Excel-streaming pattern; this feature extends it to the stock domain with LEFT JOIN plan data.

---

## User Stories

### US-01 — Download Stock Excel Report

> As a **manager or viewer**, I want to download a `.xlsx` file of daily stock facts for my organisation, so that I can analyse availability data offline without needing database access.

**Acceptance Criteria:**
- GET /api/v1/reports/stock-export returns HTTP 200 with `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- Response includes `Content-Disposition: attachment; filename="stock_{date_from}_{date_to}.xlsx"`
- Workbook has a single sheet named "Stock"
- Row 1 is a merged title cell: `"Отчёт по дистрибуции: {date_from} — {date_to}"`
- Row 2 contains column headers
- Data begins at row 3
- Auto-filter is applied to the header row
- Pane is frozen at A3
- Unauthenticated request returns HTTP 401

### US-02 — Filter by Date Range

> As a **manager**, I want to specify `date_from` and `date_to` query parameters, so that I can limit the report to the period relevant to my review.

**Acceptance Criteria:**
- Both `date_from` and `date_to` are required; omitting either returns HTTP 422
- `date_to` must be >= `date_from`; violation returns HTTP 400 with `detail` containing `"INVALID_DATE_RANGE"`
- Date range must not exceed 366 days; violation returns HTTP 400 with `"INVALID_DATE_RANGE"` and the day limit
- Dates are inclusive on both ends (scored_at >= date_from AND scored_at <= date_to)
- Valid range with no matching rows returns HTTP 200 with a header-only workbook (no error)

### US-03 — Filter by Platform

> As a **manager**, I want to optionally pass a `platform_id` UUID, so that I can narrow the report to a single platform without downloading data for all 110+ platforms.

**Acceptance Criteria:**
- `platform_id` is optional; absent = all platforms for the org
- Valid UUID narrows results to rows where `sku_platforms.platform_id = platform_id`
- Invalid UUID format returns HTTP 422 (FastAPI param validation)
- UUID for a platform not belonging to this org returns HTTP 200 with an empty workbook (no 403 — the JOIN simply produces no matching rows)

### US-04 — Color-Coded Rows (In Stock vs Out of Stock)

> As a **manager**, I want rows to be highlighted green when the SKU is in stock and red when it is out of stock, so that I can spot availability gaps without reading the text values.

**Acceptance Criteria:**
- Rows where `in_stock = True`: all 10 columns filled with green (`#C6EFCE`)
- Rows where `in_stock = False`: all 10 columns filled with red (`#FFC7CE`)
- Rows where `in_stock = NULL`: no fill applied (excluded from query — this criterion is informational)
- The "В наличии" column shows "Да" for True, "Нет" for False, "—" for NULL

### US-05 — Plan vs Fact (Distribution Plan Target Column)

> As a **manager**, I want to see the planned trade-point count alongside each daily stock fact, so that I can compare actual availability coverage against the plan target without manual VLOOKUP.

**Acceptance Criteria:**
- Column "План (ТТ)" shows the `plan_tt_count` from the matching distribution plan row for the same SKU × Platform × ISO week
- When no distribution plan exists for that week, the column shows "—" (NULL plan is not an error)
- The plan match uses ISO week number and year extracted from `scored_at` — not a date range join
- Plan data is LEFT JOINed so stock facts always appear even without a plan

---

## Non-Functional Requirements

| Category | Requirement |
|----------|-------------|
| Performance | Excel generation in memory (BytesIO) — no temp files, no disk I/O |
| Memory | Streaming response; workbook not held in process memory after response sent |
| Auth | JWT required; `current_user.org_id` scopes all DB queries |
| RBAC | All three roles (admin, manager, viewer) can download |
| Date range | Max 366 days to prevent runaway queries on large orgs |
| Empty result | Valid state — returns header-only workbook, not an error |
| Error masking | Internal exceptions logged, never returned to client (HTTP 500 `"INTERNAL_ERROR"`) |
| Filename | Dynamic: `stock_{date_from}_{date_to}.xlsx` |

---

## Out of Scope

- Chart generation inside the Excel file
- Scheduled / email delivery of reports
- Per-SKU drill-down tabs
- Writing or modifying distribution plan data (read-only endpoint)
- Frontend UI changes (this is a backend-only feature; the download is triggered from the existing Reports page or via direct API call)
- Scraping pipeline changes

---

## Success Metrics

- Manager downloads a combined stock + plan Excel for 4 weeks of data in under 5 seconds on an org with 500 SKUs × 10 platforms
- Report contains the correct plan target for every stock row that has a matching plan
- Rows without a plan show "—" and are not omitted from the report
- Zero cross-tenant data leakage (automated test: Org B query returns no Org A rows)
