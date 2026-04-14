# Pseudocode: Excel Export — Stock Distribution

**Feature:** `excel-export-stock`
**Date:** 2026-04-02

---

## Repository: get_stock_data_for_export

```python
async def get_stock_data_for_export(
    db: AsyncSession,
    org_id: UUID,
    date_from: date,
    date_to: date,
    platform_id: Optional[UUID] = None,
) -> list[StockRow]:

    # Compute ISO week and year as SQLAlchemy expressions (PostgreSQL + SQLite compatible)
    week_of_scored_at = func.extract("week", ContentScoreRead.scored_at).label("week_num")
    year_of_scored_at = func.extract("year", ContentScoreRead.scored_at).label("year_num")

    stmt = (
        select(
            Brand.name.label("brand_name"),
            SKU.article.label("sku_article"),
            SKU.name.label("sku_name"),
            Platform.name.label("platform_name"),
            ContentScoreRead.scored_at,
            week_of_scored_at,
            year_of_scored_at,
            ContentScoreRead.in_stock,
            ContentScoreRead.warehouse_qty,
            DistributionPlanRead.plan_tt_count,   # NULL when no plan
        )
        # INNER JOINs — build the tenant-scoped fact rows
        .join(SKUPlatform, ContentScoreRead.sku_platform_id == SKUPlatform.id)
        .join(SKU, SKUPlatform.sku_id == SKU.id)
        .join(Brand, SKU.brand_id == Brand.id)
        .join(Platform, SKUPlatform.platform_id == Platform.id)
        # LEFT JOIN — attach plan if exists for same SKU × Platform × ISO week
        .outerjoin(
            DistributionPlanRead,
            (DistributionPlanRead.sku_id == SKU.id)
            & (DistributionPlanRead.platform_id == SKUPlatform.platform_id)
            & (DistributionPlanRead.week_number == func.extract("week", ContentScoreRead.scored_at))
            & (DistributionPlanRead.year == func.extract("year", ContentScoreRead.scored_at)),
        )
        # Mandatory filters
        .where(SKU.org_id == org_id)                          # tenant isolation
        .where(ContentScoreRead.scored_at >= date_from)       # date range start
        .where(ContentScoreRead.scored_at <= date_to)         # date range end
        .where(ContentScoreRead.in_stock.is_not(None))        # exclude ML-only rows
        # Deterministic ordering for Excel
        .order_by(
            Brand.name,
            SKU.article.nulls_last(),
            Platform.name,
            ContentScoreRead.scored_at,
        )
    )

    # Optional platform filter
    IF platform_id IS NOT None:
        stmt = stmt.where(SKUPlatform.platform_id == platform_id)

    result = await db.execute(stmt)
    rows = result.all()

    RETURN [
        StockRow(
            brand_name     = r.brand_name,
            sku_article    = r.sku_article,
            sku_name       = r.sku_name,
            platform_name  = r.platform_name,
            scored_at      = r.scored_at,
            week_number    = int(r.week_num),   # cast float → int (SQLAlchemy numeric)
            year           = int(r.year_num),
            in_stock       = r.in_stock,
            warehouse_qty  = r.warehouse_qty,
            plan_tt_count  = r.plan_tt_count,   # None when LEFT JOIN found no match
        )
        for r in rows
    ]
```

---

## Service: _build_stock_workbook

```python
def _build_stock_workbook(
    rows: list[StockRow],
    date_from: date,
    date_to: date,
) -> Workbook:

    wb = Workbook()
    ws = wb.active
    ws.title = "Stock"
    num_cols = len(_STOCK_COLUMNS)   # = 10

    # Row 1: merged period header
    ws.merge_cells(f"A1:{get_column_letter(num_cols)}1")
    ws["A1"].value = f"Отчёт по дистрибуции: {date_from} — {date_to}"
    ws["A1"].font = Font(bold=True, name="Calibri", size=12)
    ws["A1"].alignment = Alignment(horizontal="center")

    # Row 2: column headers
    FOR col_idx, (label, width) IN enumerate(_STOCK_COLUMNS, start=1):
        cell = ws.cell(row=2, column=col_idx, value=label)
        cell.fill = _HEADER_FILL           # solid #4472C4
        cell.font = _HEADER_FONT           # Calibri Bold White
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    ws.row_dimensions[2].height = 30
    ws.freeze_panes = "A3"

    # Row 3+: data rows
    FOR row_idx, row IN enumerate(rows, start=3):

        # Build cell values in column order
        values = [
            row.brand_name,
            row.sku_article OR "—",        # None article → dash
            row.sku_name,
            row.platform_name,
            row.scored_at.isoformat(),     # "2026-01-15"
            row.week_number,               # int (e.g. 3)
            row.year,                      # int (e.g. 2026)
            _fmt_bool(row.in_stock),       # "Да" / "Нет"
            _fmt_int(row.warehouse_qty),   # str(n) or "—"
            _fmt_int(row.plan_tt_count),   # str(n) or "—"  ← LEFT JOIN result
        ]

        # Determine row-level fill from in_stock
        fill = _stock_row_fill(row.in_stock)
        #   True  → PatternFill solid #C6EFCE (green)
        #   False → PatternFill solid #FFC7CE (red)
        #   None  → None (no fill)

        FOR col_idx, value IN enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.font = _BODY_FONT
            cell.alignment = Alignment(vertical="center")
            IF fill IS NOT None:
                cell.fill = fill           # apply same fill to ALL 10 columns

    # Auto-filter on header row
    ws.auto_filter.ref = f"A2:{get_column_letter(num_cols)}2"

    RETURN wb
```

---

## Service: build_stock_export (orchestration)

```python
async def build_stock_export(
    db: AsyncSession,
    org_id: UUID,
    date_from: date,
    date_to: date,
    platform_id: Optional[UUID] = None,
) -> bytes:
    """
    Query stock fact data joined with distribution plan, build Excel workbook,
    return raw bytes. Empty result → header-only workbook, not an error.
    """
    # Step 1: fetch data (async DB query)
    rows = await get_stock_data_for_export(
        db=db,
        org_id=org_id,
        date_from=date_from,
        date_to=date_to,
        platform_id=platform_id,
    )
    # rows = [] is valid (no data in range)

    # Step 2: build workbook (synchronous, in-memory)
    wb = _build_stock_workbook(rows, date_from=date_from, date_to=date_to)

    # Step 3: serialise to bytes without disk I/O
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    RETURN buf.read()
```

---

## Router: export_stock_data

```python
@router.get("/stock-export", response_class=Response)
async def export_stock_data(
    date_from: date = Query(...),
    date_to: date = Query(...),
    platform_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:

    # Validate date range (shared with content-export)
    _validate_date_range(date_from, date_to)

    TRY:
        xlsx_bytes = await service.build_stock_export(
            db=db,
            org_id=current_user.org_id,    # tenant isolation from JWT
            date_from=date_from,
            date_to=date_to,
            platform_id=platform_id,
        )
    EXCEPT Exception:
        logger.exception("Unexpected error generating stock export")
        RAISE HTTPException(500, detail="INTERNAL_ERROR")

    filename = f"stock_{date_from}_{date_to}.xlsx"
    RETURN Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(xlsx_bytes)),
        },
    )
```

---

## Router: _validate_date_range (shared helper)

```python
_MAX_DATE_RANGE_DAYS = 366

def _validate_date_range(date_from: date, date_to: date) -> None:
    IF date_to < date_from:
        RAISE HTTPException(400, detail="INVALID_DATE_RANGE: date_to must be >= date_from")
    IF (date_to - date_from).days > _MAX_DATE_RANGE_DAYS:
        RAISE HTTPException(400, detail=f"INVALID_DATE_RANGE: maximum range is {_MAX_DATE_RANGE_DAYS} days")
```
