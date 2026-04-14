# PRD: Excel Export — Content Scores

**Feature:** `excel-export-content`
**Date:** 2026-04-02
**Status:** Phase 1 — Retroactive Documentation (feature already implemented)

---

## Executive Summary

API endpoint that allows authenticated users of any role to download an `.xlsx` report of content scores for their organisation's SKUs across platforms, filtered by date range and optionally by platform. The report is generated entirely in memory (BytesIO, no disk I/O) and streamed directly as a binary HTTP response. Color coding on score columns provides instant visual quality assessment.

---

## Problem Statement

Brand managers track content quality (image, description, composition scores) per SKU across 110+ platforms via the CAT scoring pipeline. The data exists in PostgreSQL but is only accessible through raw API JSON responses. There is no way to:

- Export content score history into a shareable Excel file for stakeholder reporting
- Apply visual quality thresholds (green/yellow/red) without manual formatting in Excel
- Filter scores by date range or a specific platform before export
- Generate a branded, consistently formatted report without manual copy-paste

---

## User Stories

### US-01 — Download Content Score Report

> As a **manager**, I want to download an Excel file of content scores for my organisation filtered by date range, so that I can share quality reports with stakeholders.

**Acceptance Criteria:**
- `GET /api/v1/reports/content-export?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD` returns a `.xlsx` file
- Response Content-Type is `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- `Content-Disposition` header includes filename `content_scores_{date_from}_{date_to}.xlsx`
- `Content-Length` header is present
- File contains a report-period sub-header in row 1 and column headers in row 2
- Data rows start from row 3
- Rows are ordered by Brand → SKU Article → Platform → Date (ascending)

### US-02 — Filter Report by Platform

> As a **manager**, I want to filter the content score export by a specific platform, so that I can produce a single-platform report for a platform partner.

**Acceptance Criteria:**
- Optional query parameter `platform_id` (UUID) narrows results to a single platform
- Omitting `platform_id` returns all platforms for the organisation
- Invalid (non-UUID) `platform_id` returns HTTP 422
- Non-existent `platform_id` (valid UUID but no data) returns an empty workbook (headers only), not an error

### US-03 — Color-Coded Score Columns

> As a **viewer**, I want score cells color-coded by threshold, so that I can immediately identify underperforming SKUs without reading the numbers.

**Acceptance Criteria:**
- `content_total >= 80` → green fill (#C6EFCE) on score columns 6–9
- `50 <= content_total < 80` → yellow fill (#FFEB9C) on score columns 6–9
- `content_total < 50` → red fill (#FFC7CE) on score columns 6–9
- `content_total IS NULL` → no fill (scores not yet computed by ML pipeline)
- Null score values are displayed as `—` (em-dash), not empty or `None`

### US-04 — Date Range Validation

> As a **developer integrating CAT**, I want clear error responses for invalid date parameters, so that I can surface actionable messages to end users.

**Acceptance Criteria:**
- `date_to < date_from` returns HTTP 400 with detail `INVALID_DATE_RANGE: date_to must be >= date_from`
- Range exceeding 366 days returns HTTP 400 with detail `INVALID_DATE_RANGE: maximum range is 366 days`
- Missing `date_from` or `date_to` returns HTTP 422 (FastAPI query validation)
- Malformed date string (e.g. `2026-13-01`) returns HTTP 422

### US-05 — Access by All Authenticated Roles

> As a **viewer**, I want to download content score exports, so that I can share reports without requiring manager permissions.

**Acceptance Criteria:**
- All three roles (admin, manager, viewer) can call the endpoint successfully
- Unauthenticated requests (missing or invalid JWT) return HTTP 401
- Each user's export is scoped to their organisation — cross-org data is never returned

---

## Non-Functional Requirements

| Category | Requirement |
|----------|------------|
| Auth | JWT Bearer token required; 401 on missing/expired token |
| RBAC | admin, manager, viewer all permitted (read-only export) |
| Multi-tenancy | All data filtered by `current_user.org_id`; no cross-org leakage |
| Performance | Response under 5 seconds for up to 10,000 rows |
| Memory | BytesIO only — no temporary files written to disk |
| Max date range | 366 days per request |
| Content-Type | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| Error opacity | Internal exceptions logged server-side; client receives `INTERNAL_ERROR` only |
| Rate limiting | Inherits global API rate limits (100 req/min per user) |

---

## Out of Scope

- Stock/distribution export (separate endpoint `/reports/stock-export`)
- Frontend download button UI (frontend scaffold separate feature)
- Email delivery of reports (alerts feature)
- Scheduled/automated report generation (Celery task — separate feature)
- PDF export
- Custom column selection by the user

---

## Success Metrics

- Manager can download a dated `.xlsx` file for any date range up to 366 days
- Color coding applied correctly so quality issues are visible without reading numbers
- Unauthenticated or cross-org requests never return data
- Empty result set returns a valid workbook (not an error), usable as a template
