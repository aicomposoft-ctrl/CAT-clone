# PRD — Frontend: Prices & Reviews Pages

**Feature:** frontend-prices-reviews
**Sprint:** 2 (frontend completion)
**Priority:** P1
**Story Points:** 13

---

## 1. Problem Statement

CAT has fully implemented backend APIs for price monitoring (4 endpoints) and reviews/NLP (4 endpoints), but the frontend pages `Prices/index.tsx` and `Reviews/index.tsx` are empty 12-line stubs. Users logged into the dashboard see placeholder text "Sprint 2" instead of functional analytics.

## 2. Business Value

- Managers can monitor price anomalies and trends per SKU without leaving the dashboard
- Brand analysts can review sentiment breakdown (positive/neutral/negative) by platform
- Removes last two non-functional pages from Sprint 1 dashboard, completing the MVP UI

## 3. Target Users

| Persona | Goal |
|---------|------|
| Trade Marketing Manager | Monitor prices vs competitors, spot anomalies |
| Brand Analyst | Review sentiment trends, understand customer feedback |
| Viewer | Read-only access to price/review data |

## 4. Feature Scope (MVP)

### Prices Page (`/prices`)

| Component | Priority | Description |
|-----------|----------|-------------|
| SKU selector | P0 | Dropdown to pick SKU (required — all endpoints need sku_id) |
| Latest prices table | P0 | Platform × price × discount × cheapest flag |
| Price anomalies table | P0 | Significant changes with direction (up/down) |
| Price history chart | P1 | ECharts line chart — price over time per platform |
| Stats summary | P1 | Min/max/avg/change over date range |
| Date range filter | P1 | DatePicker.RangePicker for history/stats/anomalies |

### Reviews Page (`/reviews`)

| Component | Priority | Description |
|-----------|----------|-------------|
| SKU selector | P0 | Dropdown to pick SKU |
| Sentiment summary table | P0 | Per-platform: positive/neutral/negative % + avg rating |
| Sentiment pie chart | P0 | ECharts pie — total positive/neutral/negative share |
| Reviews history table | P1 | Paginated individual reviews with sentiment tag + rating |
| Sentiment filter | P1 | Filter history by positive/neutral/negative |
| Weekly trend chart | P1 | ECharts bar — weekly positive share trend |
| Date range filter | P1 | DatePicker.RangePicker |

### Out of scope
- Competitor price tracking view (v2)
- AI-generated review summaries
- Review reply management

## 5. User Stories

### US-1: Manager views current prices across platforms
```gherkin
As a manager,
I want to see the latest price for my SKU on all platforms,
So that I can identify the cheapest platform and pricing inconsistencies.
```

### US-2: Manager detects price anomalies
```gherkin
As a manager,
I want to see significant price changes flagged as anomalies,
So that I can react to competitor promotions or price drops.
```

### US-3: Manager views price history chart
```gherkin
As a manager,
I want to see a price trend chart for a date range,
So that I can understand historical pricing dynamics.
```

### US-4: Brand analyst views sentiment breakdown
```gherkin
As a brand analyst,
I want to see positive/neutral/negative percentages per platform,
So that I can identify which platforms have the most negative feedback.
```

### US-5: Brand analyst reads individual reviews
```gherkin
As a brand analyst,
I want to browse individual reviews filtered by sentiment,
So that I can read actual customer feedback.
```

## 6. Success Metrics

| Metric | Target |
|--------|--------|
| All P0 components rendered on page load | 100% |
| No "Sprint 2" placeholders remain | 0 |
| TypeScript: zero type errors | 0 |
| API calls respect org_id tenant isolation (via JWT) | 100% |
