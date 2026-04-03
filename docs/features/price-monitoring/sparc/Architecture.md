# Architecture — Price Monitoring

**SPARC Phase 5: Architecture** | Feature: price-monitoring

---

## 1. Domain Placement

Price monitoring is a new domain within the existing `services/api` FastAPI monolith:

```
services/api/app/
├── core/           ← existing (db, config, deps, security)
├── catalog/        ← existing (SKU, Platform, Brand ORM models)
├── stock/          ← existing
├── reports/        ← existing
├── alerts/         ← existing
└── prices/         ← NEW (this feature)
    ├── __init__.py
    ├── models.py      # PriceSnapshot ORM (read-only — table already exists)
    ├── schemas.py     # Pydantic request/response schemas
    ├── repository.py  # DB queries (all tenant-scoped via JOIN)
    ├── service.py     # Business logic (stats, anomaly detection)
    └── router.py      # FastAPI routes (4 GET endpoints)
```

No new DB tables. No new Alembic migration required. `price_snapshots` already exists (migration 0003). One optional migration adds a covering index if needed.

---

## 2. Data Model

### Existing Table — `price_snapshots`

```sql
CREATE TABLE price_snapshots (
    id               UUID PRIMARY KEY,
    sku_platform_id  UUID REFERENCES sku_platforms(id) ON DELETE CASCADE,
    price            DECIMAL(10,2) NOT NULL,
    original_price   DECIMAL(10,2) NOT NULL,
    discount_pct     DECIMAL(5,2) NOT NULL DEFAULT 0.00,
    promo_label      VARCHAR(255),
    collected_at     TIMESTAMPTZ NOT NULL
);
-- Existing index: idx_price_snapshots_sp_time (sku_platform_id, collected_at DESC)
```

**Tenant isolation:** No `org_id` on `price_snapshots`. Isolation enforced by JOIN chain:
```
price_snapshots.sku_platform_id
  → sku_platforms.sku_id
  → skus.org_id = :org_id  ← mandatory filter on every query
```

### ORM Model (read-only mapping)

```python
# services/api/app/prices/models.py

class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"
    __table_args__ = {"extend_existing": True}  # table defined in migration 0003

    id               = Column(UUID(as_uuid=True), primary_key=True)
    sku_platform_id  = Column(UUID(as_uuid=True), ForeignKey("sku_platforms.id"))
    price            = Column(Numeric(10, 2))
    original_price   = Column(Numeric(10, 2))
    discount_pct     = Column(Numeric(5, 2))
    promo_label      = Column(String(255))
    collected_at     = Column(DateTime(timezone=True))
```

**Note:** `extend_existing=True` prevents `InvalidRequestError` if `price_snapshots` is mapped elsewhere. The table is not mapped in any other domain module (collector writes directly via raw SQL or its own session).

---

## 3. Query Patterns

### 3.1 History Query (US-1)

```sql
SELECT
    ps.id,
    sp.platform_id,
    p.name AS platform_name,
    ps.price,
    ps.original_price,
    ps.discount_pct,
    ps.promo_label,
    ps.collected_at
FROM price_snapshots ps
JOIN sku_platforms sp ON sp.id = ps.sku_platform_id
JOIN platforms p ON p.id = sp.platform_id
JOIN skus s ON s.id = sp.sku_id
WHERE s.org_id = :org_id
  AND s.id = :sku_id
  AND (:platform_id IS NULL OR sp.platform_id = :platform_id)
  AND ps.collected_at >= :date_from
  AND ps.collected_at < :date_to_exclusive
ORDER BY ps.collected_at ASC
LIMIT :limit;
```

Uses existing `idx_price_snapshots_sp_time` index for the inner loop.

### 3.2 Latest Query (US-2) — DISTINCT ON pattern

```sql
SELECT DISTINCT ON (sp.platform_id)
    sp.platform_id,
    p.name AS platform_name,
    ps.price,
    ps.original_price,
    ps.discount_pct,
    ps.promo_label,
    ps.collected_at
FROM price_snapshots ps
JOIN sku_platforms sp ON sp.id = ps.sku_platform_id
JOIN platforms p ON p.id = sp.platform_id
JOIN skus s ON s.id = sp.sku_id
WHERE s.org_id = :org_id
  AND s.id = :sku_id
ORDER BY sp.platform_id, ps.collected_at DESC;
```

PostgreSQL `DISTINCT ON` is O(n log n) — efficient given the existing index.

### 3.3 Stats Query (US-3) — Single aggregation

```sql
WITH ordered AS (
    SELECT ps.price, ps.discount_pct, ps.collected_at,
           ROW_NUMBER() OVER (ORDER BY ps.collected_at ASC) AS rn_asc,
           ROW_NUMBER() OVER (ORDER BY ps.collected_at DESC) AS rn_desc
    FROM price_snapshots ps
    JOIN sku_platforms sp ON sp.id = ps.sku_platform_id
    JOIN skus s ON s.id = sp.sku_id
    WHERE s.org_id = :org_id
      AND s.id = :sku_id
      AND (:platform_id IS NULL OR sp.platform_id = :platform_id)
      AND ps.collected_at >= :date_from
      AND ps.collected_at < :date_to
)
SELECT
    COUNT(*)                                             AS snapshot_count,
    MIN(price)                                           AS price_min,
    MAX(price)                                           AS price_max,
    AVG(price)                                           AS price_avg,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price)  AS price_median,
    MAX(CASE WHEN rn_asc = 1 THEN price END)             AS first_price,
    MAX(CASE WHEN rn_desc = 1 THEN price END)            AS last_price,
    AVG(discount_pct)                                    AS discount_avg
FROM ordered;
```

Single round-trip. Median via `PERCENTILE_CONT` (PostgreSQL native).

### 3.4 Anomalies Query (US-4) — LAG window function

```sql
WITH price_series AS (
    SELECT
        ps.collected_at::date AS date,
        sp.platform_id,
        p.name AS platform_name,
        ps.price,
        LAG(ps.price) OVER (
            PARTITION BY ps.sku_platform_id
            ORDER BY ps.collected_at
        ) AS price_prev
    FROM price_snapshots ps
    JOIN sku_platforms sp ON sp.id = ps.sku_platform_id
    JOIN platforms p ON p.id = sp.platform_id
    JOIN skus s ON s.id = sp.sku_id
    WHERE s.org_id = :org_id
      AND s.id = :sku_id
      AND (:platform_id IS NULL OR sp.platform_id = :platform_id)
      AND ps.collected_at >= :date_from
      AND ps.collected_at < :date_to
    ORDER BY ps.sku_platform_id, ps.collected_at
)
SELECT
    date,
    platform_id,
    platform_name,
    price_prev        AS price_before,
    price             AS price_after,
    (price - price_prev)                    AS change_abs,
    (price - price_prev) / price_prev * 100 AS change_pct
FROM price_series
WHERE price_prev IS NOT NULL
  AND ABS((price - price_prev) / price_prev * 100) >= :threshold
  AND (
    :direction = 'both'
    OR (:direction = 'down' AND price < price_prev)
    OR (:direction = 'up'   AND price > price_prev)
  );
```

One SQL query per request. No N+1.

---

## 4. API Layer

```
services/api/app/prices/router.py
  GET /api/v1/prices/history   → PriceHistoryResponse
  GET /api/v1/prices/latest    → PriceLatestResponse
  GET /api/v1/prices/stats     → PriceStatsResponse
  GET /api/v1/prices/anomalies → PriceAnomaliesResponse
```

All routes:
- Require `get_current_user` (any role)
- Accept `sku_id` and validate SKU belongs to `current_user.org_id` before query
- Thin: validate params → call service → return schema

### SKU Ownership Check

```python
# In router, before each query:
sku = await catalog_repo.get_sku(db, sku_id, org_id=current_user.org_id)
if sku is None:
    raise HTTPException(status_code=404, detail="SKU_NOT_FOUND")
```

This is a fast indexed lookup (`idx_skus_org_id + id filter`). Prevents the need to embed org_id checks in every price repository query.

---

## 5. Service Layer

```python
# services/api/app/prices/service.py

async def get_price_history(db, org_id, sku_id, platform_id, date_from, date_to, limit)
    → list[PriceHistoryItem]

async def get_latest_prices(db, org_id, sku_id)
    → PriceLatestResult

async def get_price_stats(db, org_id, sku_id, platform_id, date_from, date_to)
    → PriceStats | None

async def get_price_anomalies(db, org_id, sku_id, platform_id, date_from, date_to, threshold, direction)
    → list[PriceAnomaly]
```

Service receives `org_id` as parameter. Validates SKU ownership once at router layer (not repeated in service). All actual DB queries delegated to `repository.py`.

`_validate_date_range(date_from, date_to)` — shared helper:
- Sets defaults: `date_from = today - 30d`, `date_to = today`
- Raises `ValueError` if `date_from > date_to` or range > 366 days

---

## 6. File Structure

```
services/api/app/prices/
├── __init__.py       # empty
├── models.py         # PriceSnapshot ORM (extend_existing=True)
├── schemas.py        # 8 Pydantic schemas
├── repository.py     # 4 async query functions
├── service.py        # 4 service functions + _validate_date_range
└── router.py         # 4 GET endpoints

services/api/tests/e2e/
└── test_prices_api.py   # 20+ tests

infrastructure/postgres/migrations/
└── 0009_add_price_snapshot_org_lookup_index.py  # optional covering index
```

---

## 7. Optional Migration — Covering Index

The existing index `idx_price_snapshots_sp_time (sku_platform_id, collected_at DESC)` accelerates queries when `sku_platform_id` is known. Our queries always JOIN through `skus.id → sku_platforms.sku_id`, filtering `skus.org_id AND skus.id`.

A covering index on `sku_platforms (sku_id, platform_id)` would accelerate the JOIN. It already exists (`uq_sku_platforms UNIQUE (sku_id, platform_id)`). No additional migration needed for the basic case.

**Migration 0009** adds one index to support the stats/anomalies queries which scan all snapshots for a SKU across multiple platforms:

```python
# 0009_add_price_snapshot_org_lookup_index.py
op.create_index(
    "idx_sku_platforms_sku_id",
    "sku_platforms",
    ["sku_id"],
)
# This is NOT a duplicate — the UNIQUE constraint on (sku_id, platform_id)
# provides a composite index. A single-column index on (sku_id) alone
# allows faster filtered scans when platform_id is not part of the WHERE clause.
```

---

## 8. Main.py Registration

```python
# services/api/app/main.py
from app.prices.router import router as prices_router
app.include_router(prices_router, prefix="/api/v1/prices", tags=["prices"])
```

---

## 9. Key Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| SKU ownership check | Once in router, via catalog_repo | Avoids duplicating tenant logic in every price query |
| Median computation | `PERCENTILE_CONT(0.5)` in SQL | Correct statistical median; no Python post-processing |
| Latest price | `DISTINCT ON (platform_id)` + `ORDER BY collected_at DESC` | One query, correct semantics, uses existing index |
| Anomaly detection | LAG window function in SQL | Single query, no Python loop over rows |
| Extend_existing | `True` on PriceSnapshot | Prevents `InvalidRequestError` — table mapped nowhere else but safety guard |
| ClickHouse | Not used in MVP | PostgreSQL sufficient for 90 days; ClickHouse queries add complexity |
| No N+1 | All endpoints max 2 DB queries | 1 for SKU ownership check + 1 for price data |
