# Specification — Web Dashboard
> Feature: web-dashboard | SPARC Phase 3 | CAT Project

---

## 1. User Stories with Acceptance Criteria

---

### US-01: Dashboard Overview (KPI-сводка)

```gherkin
Feature: Dashboard Overview

Scenario: Brand Manager sees KPI summary on load
  Given I am authenticated as any role
  When I navigate to "/" or "/dashboard"
  Then I see 4 KPI cards:
    - "Avg Content Score" (org-wide, last 24h)
    - "Active Alerts" (count of unacknowledged)
    - "Distribution Coverage" (fact/plan %)
    - "SKUs Monitored" (total active SKU-platform pairs)
  And each card has a trend indicator (vs 7 days ago)
  And data is scoped to my org_id only

Scenario: Manager sees top-5 problematic SKUs
  Given content scores are available
  When Dashboard loads
  Then I see a "Red Zone" widget: top-5 SKUs with lowest content_total
  And each row shows: SKU name | Platform | Score | Trend

Scenario: Manager sees recent alerts
  Given alert_events exist
  When Dashboard loads
  Then I see last 5 alerts with type, SKU, platform, time
  And I can click any alert to navigate to Alerts page
```

---

### US-02: Content Score Table

```gherkin
Feature: Content Score Table

Scenario: Manager views content scores
  Given collected data exists for last 7 days
  When I navigate to "/content"
  Then I see a table with columns:
    [Platform | Brand | Article | SKU Name | Content Total | Image Front | Description | Composition | Collected At | URL]
  And Content Total is color-coded:
    - Green background for score ≥ 80
    - Yellow background for 50 ≤ score < 80
    - Red background for score < 50
  And table supports: sort by any column, server-side pagination (50/page)

Scenario: Manager filters by platform
  Given platforms exist: Samokat_APP, WB, Ozon, Lenta
  When I select platform "Samokat_APP" in filter
  Then table shows only rows for Samokat_APP
  And URL reflects filter: ?platform=samokat_app

Scenario: Manager filters by score range
  When I set filter "Score below 50"
  Then only red-zone SKUs are shown

Scenario: Manager filters by date
  When I select date "2026-04-01"
  Then scores for that date are shown (or nearest available)

Scenario: Manager exports filtered data
  When I click "Export to Excel"
  Then browser downloads content_scores_YYYYMMDD.xlsx
  And file contains only currently filtered rows
```

---

### US-03: Content Score Drill-down

```gherkin
Feature: Content Score Drill-down

Scenario: Manager drills into low-scoring SKU
  Given SKU "3927" has Content Total = 42% on Samokat_APP
  When I click on that row
  Then a right drawer opens showing:
    - SKU name, platform, article
    - Score breakdown: Image Front / Description / Composition with progress bars
    - Side-by-side: collected image vs reference image
    - Diff text: collected description vs reference description (changed words highlighted)
    - Diff text: collected composition vs reference composition
    - Historical chart: content_total over last 30 days (ECharts line)
    - "Open in marketplace" link (external, new tab)

Scenario: Manager navigates between SKUs in drawer
  When drawer is open
  Then I can use ← → arrows to go to prev/next SKU in current filtered list
```

---

### US-04: Distribution Monitoring

```gherkin
Feature: Distribution Monitoring

Scenario: Manager views distribution plan vs fact
  When I navigate to "/stock"
  Then I see a table with columns:
    [Brand | SKU | Group | Platform | Plan TT | Fact TT | Coverage % | Week | Year]
  And Coverage % is color-coded (green ≥ 90%, yellow 70–89%, red < 70%)
  And I can filter by: week, platform, brand, group

Scenario: Manager sees distribution heatmap
  When I click "Heatmap" tab
  Then I see an ECharts heatmap: platforms (Y) × weeks (X) × color = coverage %
  And hovering shows tooltip with exact plan/fact numbers
```

---

### US-05: Price Monitoring

```gherkin
Feature: Price Monitoring

Scenario: Manager views current prices
  When I navigate to "/prices"
  Then I see a table:
    [SKU | Platform | Current Price | Original Price | Discount % | Promo Label | vs. 7 days ago]
  And "vs. 7 days ago" shows: +5% (red) or -3% (green) with arrow icon
  And anomalies (price change > threshold) are highlighted

Scenario: Manager views price trend for SKU
  When I click on a SKU row
  Then a drawer shows ECharts line chart: price history (90 days)
  And I can toggle: show/hide competitors on same chart
```

---

### US-06: Reviews Dashboard

```gherkin
Feature: Reviews Dashboard

Scenario: Manager views sentiment distribution
  When I navigate to "/reviews"
  Then I see an ECharts pie/bar chart: positive / neutral / negative % per brand
  And I can filter by: platform, date range, category

Scenario: Manager views recent reviews list
  When I scroll down
  Then I see paginated list of reviews:
    [Rating stars | Sentiment badge | Review text (truncated) | Platform | Date]
  And I can filter by: sentiment (positive/negative/neutral), rating, date

Scenario: Manager sees review trend
  When I select "Trend" tab
  Then I see line chart: sentiment ratio over 90 days per brand
```

---

### US-07: Alerts Feed

```gherkin
Feature: Alerts Feed

Scenario: Manager views active alerts
  When I navigate to "/alerts"
  Then I see a table:
    [Type | SKU | Platform | Value Before | Value After | Triggered At | Status]
  And Type icons: content_drop (icon) | price_change | competitor_promo | oos
  And unacknowledged alerts have "New" badge

Scenario: Manager acknowledges alert
  When I click "Acknowledge" on an alert
  Then alert status changes to "Acknowledged"
  And it moves to bottom of list / can be filtered out

Scenario: Manager filters alerts by type
  When I filter by type "price_change"
  Then only price_change alerts are shown
```

---

### US-08: Excel Export Trigger

```gherkin
Feature: Excel Export from UI

Scenario: Manager triggers content score export
  When I click "Export" button on Content page
  Then a modal shows: date picker + platform multiselect
  And I click "Download"
  Then POST /api/v1/reports/content-export is called
  And browser downloads the .xlsx file

Scenario: Manager triggers reviews export
  When I click "Export" button on Reviews page
  Then browser downloads reviews_export_YYYYMMDD.xlsx
```

---

### US-09: SKU Management

```gherkin
Feature: SKU Management

Scenario: Admin creates a SKU
  Given I am authenticated as admin or manager
  When I navigate to "/settings/skus"
  And I click "Add SKU"
  And I fill the form: brand, article, name, barcode, category, platforms
  And I click "Save"
  Then SKU is created and appears in list

Scenario: Admin uploads reference image
  Given SKU exists
  When I open SKU detail and upload a reference image
  Then image is stored in S3
  And content scoring uses new image from next cycle

Scenario: Admin bulk uploads SKUs via CSV
  When I upload a CSV file
  Then valid rows are imported
  And invalid rows are shown in error table with line numbers
```

---

### Cross-Cutting: Multi-Tenant Isolation

```gherkin
Feature: Multi-Tenant Isolation

Scenario: User from Org A cannot see Org B data
  Given user_a is authenticated for organization "BrandCo" (org_a)
  And user_b has created SKUs and content scores in organization "RetailInc" (org_b)
  When user_a navigates to /content
  Then user_a sees only scores belonging to org_a
  And no data from org_b appears in any table, chart, or KPI card

Scenario: Cross-tenant alert isolation
  Given alert events exist for org_b
  When user_a navigates to /alerts
  Then user_a sees no alerts from org_b
```

---

### Cross-Cutting: RBAC Enforcement

```gherkin
Feature: Role-Based Access Control

Scenario: Viewer cannot access SKU settings
  Given I am authenticated as viewer
  When I navigate to /settings/skus directly
  Then I am redirected to /dashboard
  And no SKU create/edit/delete buttons are visible

Scenario: Viewer cannot acknowledge alerts
  Given I am authenticated as viewer
  When I view the Alerts page
  Then the "Acknowledge" button is not rendered

Scenario: Viewer cannot trigger Excel export
  Given I am authenticated as viewer
  When I view any domain page
  Then the "Export" button is not rendered

Scenario: Manager can create SKU but not manage users
  Given I am authenticated as manager
  When I navigate to /settings/skus
  Then I can create, edit, and deactivate SKUs
  And there is no "Manage Users" option visible
```

---

### Cross-Cutting: UI States (applies to all pages)

```gherkin
Feature: Common UI States

Scenario: Table loading state
  Given I navigate to any domain page
  When data is being fetched from API
  Then skeleton rows are shown in the table
  And filters are disabled during loading

Scenario: Empty state after filtering
  Given I am on the Content page
  When I apply a filter that matches no rows
  Then "No SKUs match the selected filters" message is shown
  And a "Clear filters" button is visible

Scenario: API error state
  Given the API returns a 500 error
  When I navigate to any page
  Then a toast "Server error, try again" is shown
  And the last successfully loaded data remains visible (not replaced with blank)

Scenario: Empty org (new user)
  Given my organization has no SKUs configured
  When I navigate to /dashboard
  Then each KPI card shows 0 or "-"
  And a "Get started: Add your first SKU" banner is shown
  And Red Zone widget shows "No data yet"
```

---

### US-10: Authentication

```gherkin
Feature: Authentication

Scenario: User logs in successfully
  Given I am on /login
  When I enter valid email + password
  Then I receive JWT access token (15 min) + refresh token (7 days)
  And I am redirected to /dashboard

Scenario: User enters wrong password
  Given I am on /login
  When I enter a valid email but incorrect password
  Then a 401 response is returned
  And an inline error "Invalid email or password" is shown under the form
  And I remain on /login

Scenario: Login button shows loading state
  Given I am on /login
  When I click the login button
  Then the button shows a spinner and is disabled until the API responds

Scenario: Token auto-refresh
  Given my access token expires
  When I make any API request
  Then Axios interceptor uses refresh token to get new access token
  And original request is retried transparently

Scenario: Refresh token expired — session expired
  Given my refresh token has expired (7 days elapsed)
  When any API call triggers a 401 and the refresh attempt fails
  Then I am redirected to /login
  And a banner "Session expired, please log in again" is shown

Scenario: User logs out
  When I click "Logout"
  Then access token is cleared from in-memory Zustand store
  And refresh token is cleared from sessionStorage
  And I am redirected to /login
```

---

## 2. Price Anomaly Threshold Definition

Per US-05, a price is flagged as an anomaly when:
- Price change > **20%** compared to price 24h ago (MVP hardcoded threshold)
- Or `discount_pct` appears for the first time (new promo)

This is displayed with a red highlight in the price table. Future: configurable per org in Settings.

---

## 3. Token Storage Decision

**Chosen approach:** access token in Zustand (in-memory), refresh token in `sessionStorage`.

**Rationale:** httpOnly refresh cookies require backend CORS + cookie config changes that are out of scope for this sprint. `sessionStorage` is scoped per-tab and cleared on tab close, reducing the attack surface vs `localStorage`. XSS mitigation is handled via strict CSP (`default-src 'self'`), no `dangerouslySetInnerHTML`, and scraped text treated as plain strings.

**Accepted risk:** If an XSS vector exists, sessionStorage can be read. Mitigation: CSP headers + input sanitization at collector level.

---

## 4. Non-Functional Requirements

### Performance
- Dashboard initial render: LCP < 2s
- Table with 1000 rows: virtual scroll, render < 300ms
- API calls: all list endpoints < 500ms p95
- Charts: ECharts render < 200ms

### Security
- All API calls include `Authorization: Bearer <token>`
- org_id never sent from frontend — derived from JWT on backend
- No tokens stored in localStorage (use in-memory + httpOnly refresh cookie where possible)
- CSP headers via Nginx: `default-src 'self'`

### Accessibility
- All interactive elements keyboard-navigable
- Color coding always has secondary indicator (icon or text), not color alone
- Min contrast ratio 4.5:1 for text

### Responsiveness
- Min supported width: 1280px (desktop-first)
- Tables support horizontal scroll on smaller viewports

---

## 3. Feature Matrix

| Feature | MVP (v1) | v2 |
|---------|----------|----|
| Dashboard KPI cards | ✅ | |
| Content score table + drill-down | ✅ | |
| Distribution plan/fact | ✅ | |
| Price monitoring table | ✅ | |
| Reviews sentiment | ✅ | |
| Alerts feed + acknowledge | ✅ | |
| Excel export trigger | ✅ | |
| SKU CRUD | ✅ | |
| Alert rule configurator | | ✅ |
| Competitor view | | ✅ |
| Mobile responsive | | ✅ |
| Real-time WebSocket | | ✅ |
