# Specification — Price Monitoring

**Feature ID:** price-monitoring
**Sprint:** 6

---

## User Stories

### US-1: View price history for a SKU

```gherkin
Feature: Price History

Scenario: Manager views price history for one SKU on one platform
  Given I am authenticated as a manager
  And SKU "Индейка Индилайт" (id=SKU-1) has price_snapshots on Wildberries
  When I GET /api/v1/prices/history?sku_id=SKU-1&platform_id=PLAT-WB&date_from=2026-03-01&date_to=2026-03-31
  Then the response is 200
  And "items" is a list of daily price points
  And each item has: date, price, original_price, discount_pct, promo_label
  And items are ordered by collected_at ASC
  And all items belong to my org

Scenario: History with no snapshots returns empty list
  Given no price_snapshots exist for the specified filters
  When I GET /api/v1/prices/history?sku_id=SKU-NONE&platform_id=PLAT-1
  Then the response is 200
  And "items" is []
  And "total" is 0

Scenario: History for SKU belonging to other org returns 404
  Given SKU-FOREIGN belongs to a different org
  When org_A requests history for SKU-FOREIGN
  Then the response is 404
  And detail is "SKU_NOT_FOUND"

Scenario: date_from > date_to returns 422
  When I GET /api/v1/prices/history?date_from=2026-04-01&date_to=2026-03-01
  Then the response is 422
  And detail contains "date_from must be before date_to"

Scenario: Date range exceeds 366 days returns 422
  When date_to - date_from > 366 days
  Then the response is 422
  And detail contains "Date range cannot exceed 366 days"

Scenario: Viewer can read price history (read-only)
  Given I am authenticated as a viewer
  When I GET /api/v1/prices/history?sku_id=SKU-1
  Then the response is 200

Scenario: History for all platforms (no platform_id filter)
  Given SKU-1 has snapshots on Wildberries and Ozon
  When I GET /api/v1/prices/history?sku_id=SKU-1
  Then items from both platforms are returned
  And each item includes platform_id for disambiguation
```

---

### US-2: Compare latest prices across platforms

```gherkin
Feature: Platform Price Comparison

Scenario: Manager compares latest price on all platforms for one SKU
  Given SKU-1 has recent snapshots on Wildberries (299₽), Ozon (319₽), Самокат (289₽)
  When I GET /api/v1/prices/latest?sku_id=SKU-1
  Then the response is 200
  And "items" contains 3 entries, one per platform
  And each entry has: platform_id, platform_name, price, original_price, discount_pct, collected_at
  And entries are ordered by price ASC
  And "cheapest" field indicates the minimum-price platform

Scenario: Latest — "most recent snapshot" semantics
  Given Wildberries has snapshots from 2026-03-01, 2026-03-02, 2026-04-01
  When I GET /api/v1/prices/latest?sku_id=SKU-1
  Then the WB entry shows the 2026-04-01 snapshot data (most recent)

Scenario: Cross-tenant isolation
  Given org_A and org_B both monitor the same SKU article on Wildberries
  When org_A requests latest prices for their SKU-A
  Then only org_A's data is returned
  And org_B's prices are not visible
```

---

### US-3: Price statistics over a period

```gherkin
Feature: Price Statistics

Scenario: Manager views price statistics for a SKU on a platform
  When I GET /api/v1/prices/stats?sku_id=SKU-1&platform_id=PLAT-WB&date_from=2026-03-01&date_to=2026-03-31
  Then the response is 200
  And response contains:
    | field          | type    |
    | price_min      | decimal |
    | price_max      | decimal |
    | price_avg      | decimal |
    | price_median   | decimal |
    | snapshot_count | integer |
    | first_price    | decimal |
    | last_price     | decimal |
    | change_abs     | decimal |  -- last_price - first_price
    | change_pct     | decimal |  -- (last - first) / first * 100
    | discount_avg   | decimal |  -- avg discount_pct over period

Scenario: Stats with no data returns nulls
  When no snapshots exist for the filter
  Then the response is 200
  And all numeric fields are null
  And snapshot_count is 0

Scenario: Stats across all platforms (no platform_id)
  When I GET /api/v1/prices/stats?sku_id=SKU-1
  Then stats are computed across all platforms combined
```

---

### US-4: Detect price anomalies

```gherkin
Feature: Price Anomalies

Scenario: Manager detects significant price drops
  Given SKU-1 on WB had price 299₽ on 2026-03-14 and 229₽ on 2026-03-15 (drop of 23.4%)
  When I GET /api/v1/prices/anomalies?sku_id=SKU-1&threshold=10
  Then the response is 200
  And "items" contains at least 1 anomaly for 2026-03-15
  And anomaly has: date, platform_id, price_before, price_after, change_pct, direction

Scenario: No anomalies in stable period
  Given SKU-1 prices fluctuated by < 5% daily
  When I GET /api/v1/prices/anomalies?sku_id=SKU-1&threshold=10
  Then "items" is []

Scenario: Default threshold is 10%
  When I GET /api/v1/prices/anomalies?sku_id=SKU-1 (no threshold param)
  Then threshold defaults to 10.0

Scenario: Threshold validation
  When threshold < 0 or threshold > 100
  Then the response is 422

Scenario: Direction filter — only drops
  When I GET /api/v1/prices/anomalies?sku_id=SKU-1&direction=down
  Then only anomalies where price_after < price_before are returned

Scenario: Direction filter — only increases
  When I GET /api/v1/prices/anomalies?sku_id=SKU-1&direction=up
  Then only anomalies where price_after > price_before are returned
```

---

## API Contract

### GET /api/v1/prices/history

**Query params:**
| Param | Type | Required | Default | Constraints |
|-------|------|----------|---------|-------------|
| `sku_id` | UUID | Yes | — | Must belong to org |
| `platform_id` | UUID | No | all | — |
| `date_from` | date | No | 30 days ago | — |
| `date_to` | date | No | today | max range 366 days |
| `limit` | int | No | 500 | max 1000 |

**Response 200:**
```json
{
  "sku_id": "uuid",
  "items": [
    {
      "id": "uuid",
      "platform_id": "uuid",
      "platform_name": "Wildberries",
      "price": "299.00",
      "original_price": "399.00",
      "discount_pct": "25.06",
      "promo_label": "Скидка дня",
      "collected_at": "2026-03-15T03:00:00Z"
    }
  ],
  "total": 47
}
```

---

### GET /api/v1/prices/latest

**Query params:**
| Param | Type | Required |
|-------|------|----------|
| `sku_id` | UUID | Yes |

**Response 200:**
```json
{
  "sku_id": "uuid",
  "cheapest_platform_id": "uuid",
  "items": [
    {
      "platform_id": "uuid",
      "platform_name": "Самокат",
      "price": "289.00",
      "original_price": "289.00",
      "discount_pct": "0.00",
      "promo_label": null,
      "collected_at": "2026-04-02T22:00:00Z"
    }
  ]
}
```

---

### GET /api/v1/prices/stats

**Query params:** `sku_id` (required), `platform_id` (optional), `date_from`, `date_to`

**Response 200:**
```json
{
  "sku_id": "uuid",
  "platform_id": "uuid or null",
  "date_from": "2026-03-01",
  "date_to": "2026-03-31",
  "snapshot_count": 87,
  "price_min": "259.00",
  "price_max": "399.00",
  "price_avg": "311.50",
  "price_median": "299.00",
  "first_price": "299.00",
  "last_price": "279.00",
  "change_abs": "-20.00",
  "change_pct": "-6.69",
  "discount_avg": "18.50"
}
```

---

### GET /api/v1/prices/anomalies

**Query params:** `sku_id` (required), `platform_id` (optional), `date_from`, `date_to`, `threshold` (default 10.0), `direction` (up|down|both, default both)

**Response 200:**
```json
{
  "sku_id": "uuid",
  "threshold": 10.0,
  "items": [
    {
      "platform_id": "uuid",
      "platform_name": "Wildberries",
      "date": "2026-03-15",
      "price_before": "299.00",
      "price_after": "229.00",
      "change_abs": "-70.00",
      "change_pct": "-23.41",
      "direction": "down"
    }
  ]
}
```

---

## Non-Functional Requirements

| Category | Requirement |
|----------|-------------|
| Latency | p95 < 200 ms for history (30 days, 1 SKU + 3 platforms) |
| Latency | p95 < 100 ms for stats and anomalies |
| Isolation | All queries scoped to org_id via JOIN |
| Rate limiting | 60 req/min per user (read-heavy endpoint) |
| Date range | Maximum 366 days per request |
| Data freshness | Price data may be up to 24h old (scrapers run nightly) |
| Auth | All endpoints require Bearer JWT; all roles allowed (read-only) |
