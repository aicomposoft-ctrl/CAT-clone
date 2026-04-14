# PRD: Excel Export — Reviews

**Feature:** `excel-export-reviews`
**Sprint:** 7 | **Priority:** P1 | **Story Points:** 5
**Date:** 2026-04-04

---

## Problem

Brand managers reviewing sentiment trends (via the NLP pipeline from Sprint 7) need to share review data with account managers, QA teams, and clients. The in-app `/reviews/stats` and `/reviews/history` API is useful for interactive exploration, but analysts need an offline, shareable, filterable Excel file that includes the full review text alongside sentiment labels — structured identically to the content and stock exports already in use.

Without this export, users must manually copy data from the web UI or request raw DB dumps from engineers.

---

## Solution

Extend the existing `reports` domain (which already contains content-export and stock-export) with a third export endpoint: `GET /api/v1/reports/reviews-export`. The endpoint returns an `.xlsx` file with one row per review, color-coded by sentiment, filterable by platform, sentiment label, and SKU.

---

## User Stories

### US-1: Download Reviews Export

**As a** brand manager (role: manager or viewer),
**I want to** download an Excel file of all reviews for my org within a date range,
**So that** I can share and analyze review data offline.

**Acceptance Criteria:**
- `GET /api/v1/reports/reviews-export?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD` → HTTP 200 with `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` body
- File is named `reviews_{date_from}_{date_to}.xlsx`
- Contains all reviews for the authenticated org within the date range
- Rows ordered: brand_name → sku_article → platform_name → review_date DESC
- Returns header-only workbook when no reviews match (no 404)
- Only reviews belonging to the authenticated user's org are included (multi-tenant isolation)
- Maximum 10,000 rows per export; if exceeded, a warning row is appended to the workbook

### US-2: Filter by Platform

**As a** brand manager,
**I want to** filter the export to a single platform (e.g., Wildberries only),
**So that** I can compare platform-specific review quality.

**Acceptance Criteria:**
- Optional `platform_id` query param (UUID) — when provided, only reviews from that platform are included
- If the platform_id is valid but has no reviews in the caller's org, returns header-only workbook (200) — not 404 (the org_id filter handles isolation silently)
- Invalid UUID → HTTP 422 (FastAPI validation)

### US-3: Filter by Sentiment

**As a** brand manager,
**I want to** export only negative reviews,
**So that** I can triage urgent feedback efficiently.

**Acceptance Criteria:**
- Optional `sentiment` query param: `positive | neutral | negative`
- Invalid value → HTTP 422
- When provided, only reviews with that sentiment label are included
- Reviews with NULL sentiment (unscored) are excluded from filtered results

### US-4: Filter by SKU

**As a** brand manager managing many SKUs,
**I want to** export reviews for a specific SKU,
**So that** I can deep-dive into one product's feedback.

**Acceptance Criteria:**
- Optional `sku_id` query param (UUID)
- If the SKU does not exist OR belongs to a different org → HTTP 404 with `detail="SKU_NOT_FOUND"` (no distinction between "not found" and "wrong org" — prevents org discovery)
- When provided and ownership confirmed, only reviews for that SKU are included

---

## Out of Scope

- Pagination inside the Excel file (all matching rows are included)
- PDF export
- Sending export by email (covered by Alerts feature)
- Chart/pivot tables inside the workbook
- Reviews from platforms not yet scraped (collector service scope)
