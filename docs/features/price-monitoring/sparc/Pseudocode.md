# Pseudocode — Price Monitoring

**Feature:** Price Monitoring API
**Service:** `services/api/app/prices/`

---

## 1. Shared Helper — `_validate_date_range`

```
FUNCTION _validate_date_range(
    date_from: date | None,
    date_to: date | None,
    default_days_back: int = 30,
    max_range_days: int = 366,
) -> tuple[date, date]:

    today = date.today()

    IF date_from IS None:
        date_from = today - timedelta(days=default_days_back)

    IF date_to IS None:
        date_to = today

    IF date_from > date_to:
        RAISE ValueError("date_from must be before date_to")

    IF (date_to - date_from).days > max_range_days:
        RAISE ValueError(f"Date range cannot exceed {max_range_days} days")

    RETURN date_from, date_to
```

---

## 2. Router — Shared SKU Validation

```
# Called at top of every route handler before delegation to service

ASYNC FUNCTION _validate_sku_access(
    sku_id: UUID,
    org_id: UUID,
    db: AsyncSession,
) -> None:
    sku = await catalog_repository.get_sku_by_id(db, sku_id)
    IF sku IS None OR sku.org_id != org_id:
        RAISE HTTP 404 "SKU_NOT_FOUND"
    # SKU exists and belongs to org — proceed
```

---

## 3. GET /api/v1/prices/history

### router.py

```
ASYNC FUNCTION get_price_history_endpoint(
    sku_id: UUID,
    platform_id: UUID | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    limit: int = Query(500, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PriceHistoryResponse:

    # 1. Validate SKU access
    await _validate_sku_access(sku_id, current_user.org_id, db)

    # 2. Validate date range
    TRY:
        date_from, date_to = _validate_date_range(date_from, date_to)
    EXCEPT ValueError AS exc:
        RAISE HTTP 422 str(exc)

    # 3. Delegate
    items = await price_service.get_price_history(
        db=db, org_id=current_user.org_id, sku_id=sku_id,
        platform_id=platform_id, date_from=date_from, date_to=date_to, limit=limit,
    )

    RETURN PriceHistoryResponse(sku_id=sku_id, items=items, total=len(items))
```

### service.py

```
ASYNC FUNCTION get_price_history(
    db, org_id, sku_id, platform_id, date_from, date_to, limit,
) -> list[PriceHistoryItem]:
    rows = await price_repository.fetch_history(
        db=db, org_id=org_id, sku_id=sku_id,
        platform_id=platform_id, date_from=date_from, date_to=date_to, limit=limit,
    )
    RETURN [PriceHistoryItem.from_row(row) FOR row IN rows]
```

### repository.py — fetch_history

```
ASYNC FUNCTION fetch_history(
    db, org_id, sku_id, platform_id, date_from, date_to, limit,
) -> list[Row]:

    date_to_exclusive = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
    date_from_dt = datetime.combine(date_from, time.min, tzinfo=timezone.utc)

    stmt = (
        select(
            PriceSnapshot.id,
            SKUPlatform.platform_id,
            Platform.name.label("platform_name"),
            PriceSnapshot.price,
            PriceSnapshot.original_price,
            PriceSnapshot.discount_pct,
            PriceSnapshot.promo_label,
            PriceSnapshot.collected_at,
        )
        .join(SKUPlatform, SKUPlatform.id == PriceSnapshot.sku_platform_id)
        .join(Platform, Platform.id == SKUPlatform.platform_id)
        .join(SKU, SKU.id == SKUPlatform.sku_id)
        .where(SKU.org_id == org_id)
        .where(SKU.id == sku_id)
        .where(PriceSnapshot.collected_at >= date_from_dt)
        .where(PriceSnapshot.collected_at < date_to_exclusive)
        .order_by(PriceSnapshot.collected_at.asc())
        .limit(limit)
    )

    IF platform_id IS NOT None:
        stmt = stmt.where(SKUPlatform.platform_id == platform_id)

    result = await db.execute(stmt)
    RETURN result.all()
```

---

## 4. GET /api/v1/prices/latest

### repository.py — fetch_latest

```
ASYNC FUNCTION fetch_latest(db, org_id, sku_id) -> list[Row]:
    """
    Uses PostgreSQL DISTINCT ON to get the most recent snapshot per platform.
    Executes as a single query — no subquery loop.
    """
    stmt = text("""
        SELECT DISTINCT ON (sp.platform_id)
            sp.platform_id,
            p.name  AS platform_name,
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
        ORDER BY sp.platform_id, ps.collected_at DESC
    """)
    result = await db.execute(stmt, {"org_id": org_id, "sku_id": sku_id})
    RETURN result.all()
```

### service.py — get_latest_prices

```
ASYNC FUNCTION get_latest_prices(db, org_id, sku_id) -> PriceLatestResult:
    rows = await price_repository.fetch_latest(db, org_id, sku_id)

    IF NOT rows:
        RETURN PriceLatestResult(sku_id=sku_id, cheapest_platform_id=None, items=[])

    # Find cheapest platform
    cheapest = min(rows, key=lambda r: r.price)

    items = [PriceLatestItem.from_row(r) FOR r IN sorted(rows, key=lambda r: r.price)]

    RETURN PriceLatestResult(
        sku_id=sku_id,
        cheapest_platform_id=cheapest.platform_id,
        items=items,
    )
```

---

## 5. GET /api/v1/prices/stats

### repository.py — fetch_stats

```
ASYNC FUNCTION fetch_stats(db, org_id, sku_id, platform_id, date_from, date_to) -> Row | None:
    """
    Single aggregation query using CTE + window functions for first/last price.
    PERCENTILE_CONT for median — requires PostgreSQL.
    """
    platform_filter = "AND sp.platform_id = :platform_id" IF platform_id ELSE ""

    stmt = text(f"""
        WITH ordered AS (
            SELECT
                ps.price,
                ps.discount_pct,
                ps.collected_at,
                ROW_NUMBER() OVER (ORDER BY ps.collected_at ASC)  AS rn_asc,
                ROW_NUMBER() OVER (ORDER BY ps.collected_at DESC) AS rn_desc
            FROM price_snapshots ps
            JOIN sku_platforms sp ON sp.id = ps.sku_platform_id
            JOIN skus s ON s.id = sp.sku_id
            WHERE s.org_id = :org_id
              AND s.id = :sku_id
              {platform_filter}
              AND ps.collected_at >= :date_from
              AND ps.collected_at < :date_to
        )
        SELECT
            COUNT(*)                                              AS snapshot_count,
            MIN(price)                                            AS price_min,
            MAX(price)                                            AS price_max,
            ROUND(AVG(price), 2)                                  AS price_avg,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price)   AS price_median,
            MAX(CASE WHEN rn_asc = 1 THEN price END)              AS first_price,
            MAX(CASE WHEN rn_desc = 1 THEN price END)             AS last_price,
            ROUND(AVG(discount_pct), 2)                           AS discount_avg
        FROM ordered
    """)

    params = {"org_id": org_id, "sku_id": sku_id, "date_from": date_from, "date_to": date_to}
    IF platform_id:
        params["platform_id"] = platform_id

    result = await db.execute(stmt, params)
    row = result.one_or_none()

    IF row IS None OR row.snapshot_count == 0:
        RETURN None
    RETURN row
```

### service.py — get_price_stats

```
ASYNC FUNCTION get_price_stats(db, org_id, sku_id, platform_id, date_from, date_to) -> PriceStats:
    row = await price_repository.fetch_stats(db, org_id, sku_id, platform_id, date_from, date_to)

    IF row IS None:
        RETURN PriceStats(
            sku_id=sku_id, snapshot_count=0,
            price_min=None, price_max=None, price_avg=None, price_median=None,
            first_price=None, last_price=None, change_abs=None, change_pct=None,
            discount_avg=None,
        )

    change_abs = row.last_price - row.first_price
    change_pct = (change_abs / row.first_price * 100).quantize(Decimal("0.01")) IF row.first_price != 0 ELSE None

    RETURN PriceStats(
        sku_id=sku_id,
        snapshot_count=row.snapshot_count,
        price_min=row.price_min,
        price_max=row.price_max,
        price_avg=row.price_avg,
        price_median=row.price_median,
        first_price=row.first_price,
        last_price=row.last_price,
        change_abs=change_abs,
        change_pct=change_pct,
        discount_avg=row.discount_avg,
    )
```

---

## 6. GET /api/v1/prices/anomalies

### repository.py — fetch_anomalies

```
ASYNC FUNCTION fetch_anomalies(
    db, org_id, sku_id, platform_id, date_from, date_to, threshold, direction,
) -> list[Row]:
    """
    LAG window function to compute price delta between consecutive snapshots.
    All computation in SQL — single query.
    """
    platform_filter = "AND sp.platform_id = :platform_id" IF platform_id ELSE ""

    direction_filter = {
        "down": "AND ps2.price < ps2.price_prev",
        "up":   "AND ps2.price > ps2.price_prev",
        "both": "",
    }[direction]

    stmt = text(f"""
        WITH price_series AS (
            SELECT
                ps.collected_at::date                AS date,
                sp.platform_id,
                p.name                               AS platform_name,
                ps.price,
                LAG(ps.price) OVER (
                    PARTITION BY ps.sku_platform_id
                    ORDER BY ps.collected_at
                )                                    AS price_prev
            FROM price_snapshots ps
            JOIN sku_platforms sp ON sp.id = ps.sku_platform_id
            JOIN platforms p ON p.id = sp.platform_id
            JOIN skus s ON s.id = sp.sku_id
            WHERE s.org_id = :org_id
              AND s.id = :sku_id
              {platform_filter}
              AND ps.collected_at >= :date_from
              AND ps.collected_at < :date_to
        ),
        ps2 AS (
            SELECT *,
                (price - price_prev)                    AS change_abs,
                (price - price_prev) / price_prev * 100 AS change_pct
            FROM price_series
            WHERE price_prev IS NOT NULL
              AND price_prev != 0
        )
        SELECT
            date, platform_id, platform_name,
            price_prev AS price_before,
            price      AS price_after,
            change_abs, change_pct
        FROM ps2
        WHERE ABS(change_pct) >= :threshold
        {direction_filter}
        ORDER BY date ASC, ABS(change_pct) DESC
    """)

    params = {
        "org_id": org_id, "sku_id": sku_id,
        "date_from": date_from, "date_to": date_to,
        "threshold": threshold,
    }
    IF platform_id:
        params["platform_id"] = platform_id

    result = await db.execute(stmt, params)
    RETURN result.all()
```

### service.py — get_price_anomalies

```
ASYNC FUNCTION get_price_anomalies(
    db, org_id, sku_id, platform_id, date_from, date_to, threshold, direction,
) -> list[PriceAnomaly]:
    rows = await price_repository.fetch_anomalies(
        db, org_id, sku_id, platform_id, date_from, date_to, threshold, direction,
    )
    RETURN [
        PriceAnomaly(
            platform_id=row.platform_id,
            platform_name=row.platform_name,
            date=row.date,
            price_before=row.price_before,
            price_after=row.price_after,
            change_abs=row.change_abs,
            change_pct=row.change_pct,
            direction="down" IF row.change_pct < 0 ELSE "up",
        )
        FOR row IN rows
    ]
```

---

## 7. Data Schemas

```python
# services/api/app/prices/schemas.py

class PriceHistoryItem(BaseModel):
    id: UUID
    platform_id: UUID
    platform_name: str
    price: Decimal
    original_price: Decimal
    discount_pct: Decimal
    promo_label: str | None
    collected_at: datetime

class PriceHistoryResponse(BaseModel):
    sku_id: UUID
    items: list[PriceHistoryItem]
    total: int

class PriceLatestItem(BaseModel):
    platform_id: UUID
    platform_name: str
    price: Decimal
    original_price: Decimal
    discount_pct: Decimal
    promo_label: str | None
    collected_at: datetime

class PriceLatestResponse(BaseModel):
    sku_id: UUID
    cheapest_platform_id: UUID | None
    items: list[PriceLatestItem]

class PriceStats(BaseModel):
    sku_id: UUID
    platform_id: UUID | None
    date_from: date
    date_to: date
    snapshot_count: int
    price_min: Decimal | None
    price_max: Decimal | None
    price_avg: Decimal | None
    price_median: Decimal | None
    first_price: Decimal | None
    last_price: Decimal | None
    change_abs: Decimal | None
    change_pct: Decimal | None
    discount_avg: Decimal | None

class PriceAnomaly(BaseModel):
    platform_id: UUID
    platform_name: str
    date: date
    price_before: Decimal
    price_after: Decimal
    change_abs: Decimal
    change_pct: Decimal
    direction: Literal["up", "down"]

class PriceAnomaliesResponse(BaseModel):
    sku_id: UUID
    threshold: float
    items: list[PriceAnomaly]
```

---

## 8. Edge Cases

### `price_prev = 0` in anomaly query
Division by zero in `change_pct` calculation. Guard: `AND price_prev != 0` in the CTE WHERE clause. Rows with `price_prev = 0` are excluded (data quality issue, not an anomaly).

### Same-day multiple snapshots
If a scraper runs multiple times per day, `collected_at` is used (not date). The LAG window runs over `collected_at` ordering, so intraday changes are also detected as anomalies.

### `DISTINCT ON` not supported in SQLAlchemy ORM
Use `text()` with raw SQL for the `fetch_latest` query. The ORM does not natively support `DISTINCT ON`.

### All roles read-only
No write endpoints. No `require_role()` beyond `get_current_user`. Admin, manager, viewer all have full read access to price data.
