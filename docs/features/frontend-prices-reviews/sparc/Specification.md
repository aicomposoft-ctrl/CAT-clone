# Specification — Frontend: Prices & Reviews Pages

---

## 1. API Contracts (consumed)

### Prices — existing endpoints

**GET /api/v1/prices/latest?sku_id=UUID**
```json
{
  "sku_id": "uuid",
  "cheapest_platform_id": "uuid | null",
  "items": [
    {
      "platform_id": "uuid",
      "platform_name": "Wildberries",
      "price": "299.00",
      "original_price": "350.00",
      "discount_pct": "14.57",
      "promo_label": "string | null",
      "collected_at": "2026-04-05T10:00:00Z"
    }
  ]
}
```

**GET /api/v1/prices/anomalies?sku_id=UUID&date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&threshold=0.05**
```json
{
  "sku_id": "uuid",
  "threshold": 0.05,
  "items": [
    {
      "platform_id": "uuid",
      "platform_name": "Ozon",
      "date": "2026-04-01",
      "price_before": "350.00",
      "price_after": "299.00",
      "change_abs": "-51.00",
      "change_pct": "-14.57",
      "direction": "down"
    }
  ]
}
```

**GET /api/v1/prices/history?sku_id=UUID&platform_id=UUID&date_from=&date_to=**
```json
{
  "sku_id": "uuid",
  "items": [{"id":"uuid","platform_id":"uuid","platform_name":"WB","price":"299.00","original_price":"350.00","discount_pct":"14.57","promo_label":null,"collected_at":"..."}],
  "total": 30
}
```

**GET /api/v1/prices/stats?sku_id=UUID&platform_id=UUID&date_from=&date_to=**
```json
{
  "sku_id": "uuid", "platform_id": "uuid",
  "snapshot_count": 30,
  "price_min": "280.00", "price_max": "350.00",
  "price_avg": "312.50", "price_median": "310.00",
  "change_abs": "-20.00", "change_pct": "-6.06",
  "discount_avg": "12.50"
}
```

### Reviews — existing endpoints

**GET /api/v1/reviews/summary?sku_id=UUID&date_from=&date_to=**
```json
{
  "sku_id": "uuid", "total": 87,
  "items": [
    {
      "platform_id": "uuid", "platform_name": "Wildberries",
      "review_count": 52, "avg_rating": "4.2",
      "positive_count": 38, "neutral_count": 9, "negative_count": 5,
      "positive_pct": "73.1", "neutral_pct": "17.3", "negative_pct": "9.6",
      "last_review_date": "2026-04-01"
    }
  ]
}
```

**GET /api/v1/reviews/history?sku_id=UUID&platform_id=UUID&sentiment=positive&date_from=&date_to=&limit=100&offset=0**
```json
{
  "sku_id": "uuid", "total": 52, "limit": 100, "offset": 0,
  "items": [
    {
      "id": "uuid", "platform_id": "uuid", "platform_name": "WB",
      "review_text": "string", "rating": 5,
      "sentiment": "positive | neutral | negative | null",
      "sentiment_score": "0.92", "review_date": "2026-04-01"
    }
  ]
}
```

**GET /api/v1/reviews/stats?sku_id=UUID&date_from=&date_to=**
```json
{
  "sku_id": "uuid",
  "review_count": 87, "avg_rating": "4.1",
  "rating_distribution": {"1":2,"2":3,"3":8,"4":24,"5":50},
  "sentiment_share": {"positive":"73.5","neutral":"17.2","negative":"9.3"},
  "weekly_trend": [{"week_start":"2026-03-25","positive_share":"75.0","avg_rating":"4.2","review_count":18}]
}
```

**GET /api/v1/skus?page=1&size=200** — for SKU selector dropdown

---

## 2. TypeScript Interfaces

### prices.ts

```typescript
export interface PriceLatestItem {
  platform_id: string
  platform_name: string
  price: string
  original_price: string
  discount_pct: string
  promo_label: string | null
  collected_at: string
}

export interface PriceLatestResponse {
  sku_id: string
  cheapest_platform_id: string | null
  items: PriceLatestItem[]
}

export interface PriceAnomaly {
  platform_id: string
  platform_name: string
  date: string
  price_before: string
  price_after: string
  change_abs: string
  change_pct: string
  direction: 'up' | 'down'
}

export interface PriceAnomaliesResponse {
  sku_id: string
  threshold: number
  items: PriceAnomaly[]
}

export interface PriceHistoryItem {
  id: string
  platform_id: string
  platform_name: string
  price: string
  original_price: string
  discount_pct: string
  promo_label: string | null
  collected_at: string
}

export interface PriceHistoryResponse {
  sku_id: string
  items: PriceHistoryItem[]
  total: number
}

export interface PriceStats {
  sku_id: string
  platform_id: string | null
  date_from: string
  date_to: string
  snapshot_count: number
  price_min: string | null
  price_max: string | null
  price_avg: string | null
  price_median: string | null
  change_abs: string | null
  change_pct: string | null
  discount_avg: string | null
}
```

### reviews.ts

```typescript
export interface ReviewHistoryItem {
  id: string
  platform_id: string
  platform_name: string
  review_text: string
  rating: number
  sentiment: 'positive' | 'neutral' | 'negative' | null
  sentiment_score: string | null
  review_date: string
}

export interface ReviewHistoryResponse {
  sku_id: string
  total: number
  limit: number
  offset: number
  items: ReviewHistoryItem[]
}

export interface ReviewSummaryItem {
  platform_id: string
  platform_name: string
  review_count: number
  avg_rating: string | null
  positive_count: number
  neutral_count: number
  negative_count: number
  positive_pct: string
  neutral_pct: string
  negative_pct: string
  last_review_date: string | null
}

export interface ReviewSummaryResponse {
  sku_id: string
  date_from: string
  date_to: string
  total: number
  items: ReviewSummaryItem[]
}

export interface ReviewStats {
  sku_id: string
  review_count: number
  avg_rating: string | null
  rating_distribution: Record<string, number>
  sentiment_share: { positive: string; neutral: string; negative: string } | null
  weekly_trend: { week_start: string; positive_share: string; avg_rating: string | null; review_count: number }[]
}
```

---

## 3. Acceptance Criteria

### Prices Page

```gherkin
Feature: Prices Page

Scenario: Page loads with SKU selector
  Given I navigate to /prices
  Then I see a SKU dropdown (populated from /api/v1/skus)
  And the "Latest Prices" and "Anomalies" sections show "Select a SKU" empty state

Scenario: Manager selects a SKU and sees latest prices
  Given I select "Индейка Индилайт" from the SKU dropdown
  Then GET /api/v1/prices/latest?sku_id=<id> is called
  And I see a table with columns: Platform | Price | Original | Discount | Cheapest | Updated
  And the cheapest platform row is highlighted in green

Scenario: Anomalies table shows direction indicator
  Given price anomalies are loaded
  Then each "down" direction row shows a red ↓ arrow
  And each "up" direction row shows a green ↑ arrow

Scenario: Price history chart renders on platform selection
  Given I select a platform from the filter
  Then GET /api/v1/prices/history is called with platform_id
  And an ECharts line chart renders with dates on X axis, price on Y axis

Scenario: Stats card updates with date range
  Given I select date range 2026-03-01 → 2026-04-01
  Then GET /api/v1/prices/stats is called
  And I see min/max/avg/change summary cards
```

```gherkin
Feature: Reviews Page

Scenario: Page loads with SKU selector
  Given I navigate to /reviews
  Then I see a SKU dropdown
  And sections show "Select a SKU" empty state

Scenario: Sentiment summary loads after SKU selection
  Given I select a SKU
  Then GET /api/v1/reviews/summary is called
  And I see a table: Platform | Count | Avg Rating | Positive% | Neutral% | Negative%
  And progress bars show sentiment distribution

Scenario: Sentiment pie chart renders
  Given /api/v1/reviews/stats returns sentiment_share
  Then an ECharts pie chart shows positive/neutral/negative segments
  And positive = green, neutral = gray, negative = red

Scenario: Review history filtered by sentiment
  Given I click "Negative" filter
  Then GET /api/v1/reviews/history?sentiment=negative is called
  And each row shows the review text, rating stars, sentiment tag, date

Scenario: Null sentiment reviews show "Pending" tag
  Given a review has sentiment = null
  Then I see a gray "Pending" tag instead of sentiment label
```
