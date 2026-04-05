# Architecture — Frontend: Prices & Reviews Pages

---

## Component Structure

```
services/frontend/src/
├── api/
│   ├── prices.ts          ← NEW: typed API client for 4 price endpoints
│   └── reviews.ts         ← NEW: typed API client for 4 review endpoints
├── pages/
│   ├── Prices/
│   │   └── index.tsx      ← REPLACE stub (12 lines → ~280 lines)
│   └── Reviews/
│       └── index.tsx      ← REPLACE stub (12 lines → ~260 lines)
```

No new components/hooks needed — reuse patterns from Content and Alerts pages.

---

## Data Flow

```
User selects SKU
  → skuId state updates
  → React Query re-fetches with new skuId
    Prices: [latest, anomalies, stats, history] in parallel
    Reviews: [summary, stats, history] in parallel
  → Tables/Charts render from query data
```

---

## State Architecture

### Prices Page state
```typescript
skuId: string | undefined         // selected SKU — drives all queries
dateRange: [Dayjs, Dayjs] | null  // for history/stats/anomalies
platformId: string | undefined    // for history chart (optional filter)
historyPage: number               // pagination not needed (history is all-in)
```

### Reviews Page state
```typescript
skuId: string | undefined
dateRange: [Dayjs, Dayjs] | null
sentimentFilter: 'positive' | 'neutral' | 'negative' | undefined
reviewPage: number               // offset-based pagination for history
```

---

## React Query Keys

```typescript
// Prices
['prices-latest', skuId]
['prices-anomalies', skuId, dateFrom, dateTo]
['prices-history', skuId, platformId, dateFrom, dateTo]
['prices-stats', skuId, platformId, dateFrom, dateTo]

// Reviews
['reviews-summary', skuId, dateFrom, dateTo]
['reviews-stats', skuId, dateFrom, dateTo]
['reviews-history', skuId, platformId, sentiment, dateFrom, dateTo, page]

// Shared
['skus-list']   // for SKU selector — staleTime: 10 min
```

---

## ECharts Components

### Price History Line Chart
- X axis: `collected_at` formatted as `DD.MM`
- Y axis: price in ₽
- Series: one line per platform (different color)
- Tooltip: date + platform + price + discount

### Reviews Weekly Trend Bar Chart
- X axis: `week_start` formatted as `DD.MM`
- Y axis: positive_share %
- Bar color: green gradient
- Tooltip: week + positive% + review count

### Sentiment Pie Chart
- 3 segments: Positive (green `#52c41a`), Neutral (gray `#8c8c8c`), Negative (red `#ff4d4f`)
- Center label: total review count
- Legend below

---

## Reused Patterns (from existing codebase)

| Pattern | Source | Reuse |
|---------|--------|-------|
| `useQuery` + `staleTime: 5*60*1000` | Content page | ✅ |
| `cleanParams()` utility | `api/content.ts` | ✅ copy into prices.ts, reviews.ts |
| `DatePicker.RangePicker` default last 30 days | Alerts page | ✅ |
| Empty state when skuId is null | Alerts page | adapt |
| `Table` with server-side pagination | Alerts page | ✅ for reviews history |
| ECharts `ReactECharts` | Dashboard page | ✅ |

---

## Security

- All API calls go through `apiClient` (axios with Bearer token interceptor)
- SKU selector only shows SKUs from caller's org (filtered server-side)
- No client-side org_id filtering needed — server enforces tenant isolation
