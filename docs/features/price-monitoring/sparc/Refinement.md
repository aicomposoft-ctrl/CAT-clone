# Refinement — Price Monitoring

**Feature ID:** price-monitoring
**Sprint:** 6

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `price_snapshots` can have 1M+ rows for large orgs | Medium | High | All queries use `idx_price_snapshots_sp_time`; always filter by `sku_platform_id` set; date range capped at 366 days |
| `DISTINCT ON` not portable to SQLite (tests) | High | Low | Use `text()` for the latest query; test DB is PostgreSQL via Docker |
| `PERCENTILE_CONT` is PostgreSQL-specific | High | Low | Same mitigation: PostgreSQL in tests; document constraint |
| `price_prev = 0` causes division by zero in anomaly SQL | Medium | High | Guard `AND price_prev != 0` in CTE |
| Same SKU scraped multiple times per day — noisy anomalies | Medium | Medium | Anomaly direction threshold filters; future: daily deduplicate via `DATE_TRUNC('day')` aggregate (v2.0) |
| SKU has no price_snapshots yet (just added to monitoring) | High | Low | Empty list response, not error |
| Cross-org barcode collisions (different orgs, same SKU article) | N/A | Critical | Mitigated by `skus.org_id` filter in every query — FK chain guarantees isolation |

---

## Edge Cases

### No price snapshots for the given filters
- `/history` → `{ "items": [], "total": 0 }` (HTTP 200)
- `/latest` → `{ "cheapest_platform_id": null, "items": [] }` (HTTP 200)
- `/stats` → All numeric fields null, `snapshot_count: 0` (HTTP 200)
- `/anomalies` → `{ "items": [] }` (HTTP 200)

### Single snapshot in date range (stats)
- `first_price == last_price`
- `change_abs = 0`, `change_pct = 0.00`
- `price_min == price_max == price_avg == price_median == first_price`

### Price = 0.00 in snapshot
Legitimate: item is free/promotional. `discount_pct` may be 100%. Anomaly query guards `price_prev != 0` to avoid division-by-zero. Price = 0 is valid data, not filtered.

### `promo_label` NULL vs empty string
`promo_label` in `price_snapshots` is VARCHAR(255) NULLABLE. Response schema: `promo_label: str | None`. Never coerce NULL → "". Collectors may store NULL when no promo is active.

### Platform deactivated after snapshots collected
`platforms.is_active = False` does NOT filter historical data. The query joins on `platforms.id` (not filtering by `is_active`). Historical price data remains accessible even if the platform is later deactivated.

### SKU soft-deleted (`is_active = False`)
The SKU ownership check uses `catalog_repository.get_sku_by_id(db, sku_id)` which returns the SKU regardless of `is_active`. Historical price data for inactive SKUs remains accessible.

### Concurrent requests from same user
No locking required. All price endpoints are read-only.

### `collected_at` timezone handling
`price_snapshots.collected_at` is `TIMESTAMPTZ` (UTC). Date comparisons in queries use `::date` cast which uses the DB server timezone (UTC). `date_from` / `date_to` query params are dates, compared as `collected_at >= date_from::timestamptz` at midnight UTC. This may miss late-night snapshots if the client expects local-time semantics. **Documented limitation for MVP.** v2.0 can add timezone param.

---

## Dependencies

| Dependency | Status | Notes |
|------------|--------|-------|
| `price_snapshots` table | ✅ Exists | Migration 0003 |
| `idx_price_snapshots_sp_time` index | ✅ Exists | Migration 0003 |
| `sku_platforms`, `skus`, `platforms` tables | ✅ Exist | Migration 0002 |
| `uq_sku_platforms` UNIQUE (provides index on sku_id, platform_id) | ✅ Exists | Migration 0002 |
| `catalog_repository.get_sku_by_id` | Must exist or create | Used for SKU ownership check |
| `PERCENTILE_CONT` | PostgreSQL 9.4+ | ✅ PostgreSQL 16 in stack |
| `DISTINCT ON` | PostgreSQL-specific | ✅ OK for PostgreSQL 16 |

---

## Testing Strategy

### Unit Tests
- `test_validate_date_range_defaults` — no params → 30 days back to today
- `test_validate_date_range_inverted` → ValueError
- `test_validate_date_range_too_long` → ValueError (366+ days)
- `test_compute_stats_single_snapshot` → change_abs=0, change_pct=0
- `test_compute_stats_no_data` → all nulls
- `test_anomaly_direction_filter_down` — only returns down moves
- `test_anomaly_direction_filter_up` — only returns up moves
- `test_anomaly_price_prev_zero_excluded` — zero prev price → not in results

### E2E Tests (full HTTP stack)

```python
# test_prices_api.py — required tests

# /history
test_history_returns_ordered_by_collected_at_asc
test_history_with_platform_filter
test_history_empty_returns_200
test_history_cross_tenant_returns_404
test_history_date_from_after_date_to_returns_422
test_history_date_range_over_366_days_returns_422
test_history_viewer_can_read
test_history_limit_param_respected

# /latest
test_latest_returns_most_recent_per_platform
test_latest_orders_by_price_asc
test_latest_cheapest_platform_id_correct
test_latest_cross_tenant_returns_404
test_latest_no_snapshots_returns_empty

# /stats
test_stats_correct_min_max_avg
test_stats_median_correct_odd_count
test_stats_change_pct_calculation
test_stats_no_data_returns_nulls
test_stats_cross_tenant_returns_404

# /anomalies
test_anomalies_detects_price_drop
test_anomalies_detects_price_increase
test_anomalies_threshold_respected
test_anomalies_direction_down_only
test_anomalies_stable_prices_empty_list
test_anomalies_cross_tenant_returns_404

# Multi-tenant isolation (mandatory)
test_prices_cross_tenant_isolation
```

### Multi-Tenant Test (mandatory per testing rules)
```python
async def test_prices_cross_tenant_isolation(db_session, auth_headers_org_a, auth_headers_org_b):
    """Org B cannot see Org A's prices."""
    sku_a = await create_test_sku(db_session, org_id=ORG_A_ID)
    sp_a = await create_test_sku_platform(db_session, sku_id=sku_a.id)
    await create_test_price_snapshot(db_session, sku_platform_id=sp_a.id, price=Decimal("299.00"))

    response = client.get(
        f"/api/v1/prices/history?sku_id={sku_a.id}",
        headers=auth_headers_org_b,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "SKU_NOT_FOUND"
```

---

## Performance Optimizations

### Query Plan Validation
Before deploy, run `EXPLAIN ANALYZE` on the history and anomalies queries with a production-size dataset:
- Expected: `Index Scan` on `idx_price_snapshots_sp_time` for inner scan
- Red flag: `Seq Scan` on `price_snapshots` → missing index

### Cache Considerations (v2.0)
Stats and anomalies for completed date ranges (not including today) are immutable. Can be cached in Redis with TTL = 1 hour. MVP does not implement caching.

### Limit Enforcement
`/history` has `limit` param (default 500, max 1000). Returns `total` count separately. If `total > limit`, client must paginate using `date_from`/`date_to` narrowing (no cursor needed for time-series data).

---

## Alternatives Considered

### Alt 1: Aggregate daily in Python, not SQL
Rejected. Python loops over thousands of rows per request = slow and wasteful. SQL aggregation is the right tool.

### Alt 2: ClickHouse for all price queries
Rejected for MVP. PostgreSQL has 90 days of data with good indexes. ClickHouse adds connection complexity. ClickHouse path remains for v2.0 when historical range > 90 days is required.

### Alt 3: Materialized view for stats
Deferred. Would improve stats latency to < 10ms. Requires refresh logic (nightly or trigger-based). Added complexity not justified for MVP.

### Alt 4: Store `change_pct` in price_snapshots directly
Rejected. Denormalization. The scraper has no context of previous price — computing delta at query time is correct.
