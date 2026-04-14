# PRD: Distribution Dashboard

**Feature:** `distribution-dashboard`
**Date:** 2026-04-01
**Status:** Phase 1 — Planning

---

## Executive Summary

React frontend dashboard that lets managers and viewers see distribution plan data per SKU across retail platforms, filtered by week and year. Phase 1 displays plan quantities. "Fact vs Plan" comparison is scoped as Phase 2 (requires availability scraper data — separate feature).

---

## Problem Statement

Brand managers upload distribution plans via CSV but have no visual tool to review them. After upload, the data is inaccessible except through raw API calls. There is no way to:

- See which SKUs are planned for which platform/week
- Filter plans by platform, week, or year
- Identify missing or zero-quantity plan entries at a glance
- Delete incorrect rows from the UI

---

## User Stories

### US-01 — View Distribution Plan Table

> As a **manager**, I want to see a paginated table of distribution plans filtered by platform, week, and year, so that I can review what was uploaded.

**Acceptance Criteria:**
- Table columns: SKU barcode, Platform, Group, Plan Qty, Week, Year
- Default view: current week, current year
- Pagination: 50 rows per page, server-side
- Loading skeleton while data fetches
- Empty state with "Upload a plan to get started" message

### US-02 — Filter by Platform / Week / Year

> As a **manager**, I want to filter the table by platform, week, and year, so that I can focus on a specific planning period.

**Acceptance Criteria:**
- Platform selector: dropdown populated from existing plans (unique platforms in data)
- Week selector: number input 1–53
- Year selector: current year ± 1
- Filters combine with AND logic
- URL query params updated on filter change (shareable link)
- "Reset filters" button clears all to defaults

### US-03 — Delete Distribution Plan Row

> As a **manager**, I want to delete an incorrect distribution plan row, so that I can correct upload mistakes.

**Acceptance Criteria:**
- Delete icon per row, visible on hover
- Confirmation popconfirm before deletion
- Optimistic UI update (row greyed while deleting)
- Toast notification on success/error
- Viewers do NOT see delete controls

### US-04 — Upload Plan from Dashboard

> As a **manager**, I want to upload a new CSV directly from the dashboard page, so that I do not have to switch screens.

**Acceptance Criteria:**
- "Upload Plan" button opens Ant Design Upload component
- Accepts .csv files only
- Shows success/error count after upload (from API response)
- Table auto-refreshes after successful upload

---

## Non-Functional Requirements

| Category | Requirement |
|----------|------------|
| Performance | Initial render < 2s on 100 rows |
| Auth | JWT from localStorage; 401 redirects to /login |
| RBAC | Viewers: read-only (no upload/delete buttons); Managers: full |
| Pagination | Server-side (not client-side sort/filter) |
| Empty state | Informative, not blank |
| Error state | API error → red alert, not white screen |
| URL state | Filters reflected in query params |

---

## Out of Scope (Phase 1)

- Fact vs Plan comparison (requires availability scraper data — separate feature)
- ECharts visualisation (histogram or bar chart by platform) — Phase 2
- Export to Excel from dashboard — separate reporting feature
- Inline editing of plan quantities

---

## Success Metrics

- Manager can view and filter the full plan table without API calls
- Manager can delete a row and see it removed within 1 second
- Manager can upload CSV and see results without leaving the page
