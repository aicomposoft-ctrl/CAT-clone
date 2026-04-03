# Pseudocode: Excel Export — Content Scores

**Feature:** `excel-export-content`
**Date:** 2026-04-02

---

## Repository: get_content_scores_for_export

```python
async def get_content_scores_for_export(
    db: AsyncSession,
    org_id: UUID,
    date_from: date,
    date_to: date,
    platform_id: UUID | None = None,
) -> list[ContentScoreRow]:
    """
    Build a flat projection of content score rows for Excel export.
    Tenant isolation: WHERE skus.org_id = :org_id (mandatory, never omitted).
    """

    stmt = (
        SELECT
            brands.name          AS brand_name,
            skus.article         AS sku_article,
            skus.name            AS sku_name,
            platforms.name       AS platform_name,
            content_scores.scored_at,
            content_scores.image_score,
            content_scores.description_score,
            content_scores.composition_score,
            content_scores.content_total
        FROM content_scores
        INNER JOIN sku_platforms ON content_scores.sku_platform_id = sku_platforms.id
        INNER JOIN skus          ON sku_platforms.sku_id = skus.id
        INNER JOIN brands        ON skus.brand_id = brands.id
        INNER JOIN platforms     ON sku_platforms.platform_id = platforms.id
        WHERE
            skus.org_id = :org_id                       -- tenant isolation
            AND content_scores.scored_at >= :date_from
            AND content_scores.scored_at <= :date_to
        ORDER BY
            brands.name ASC,
            skus.article ASC NULLS LAST,
            platforms.name ASC,
            content_scores.scored_at ASC
    )

    IF platform_id IS NOT NULL:
        stmt = stmt.AND(sku_platforms.platform_id == platform_id)

    rows = EXECUTE(stmt)

    RETURN [
        ContentScoreRow(
            brand_name=r.brand_name,
            sku_article=r.sku_article,
            sku_name=r.sku_name,
            platform_name=r.platform_name,
            scored_at=r.scored_at,
            image_score=r.image_score,
            description_score=r.description_score,
            composition_score=r.composition_score,
            content_total=r.content_total,
        )
        FOR r IN rows
    ]
```

---

## Service: _score_fill (helper)

```python
def _score_fill(value: Decimal | None) -> PatternFill | None:
    IF value IS None:
        RETURN None                           # no fill for unscored rows

    IF value >= 80:
        RETURN PatternFill(fgColor="C6EFCE")  # green
    IF value >= 50:
        RETURN PatternFill(fgColor="FFEB9C")  # yellow
    RETURN PatternFill(fgColor="FFC7CE")      # red
```

---

## Service: _fmt_score (helper)

```python
def _fmt_score(value: Decimal | None) -> str:
    IF value IS None:
        RETURN "—"
    RETURN f"{value:.1f}"
```

---

## Service: _build_workbook

```python
def _build_workbook(rows: list[ContentScoreRow], date_from: date, date_to: date) -> Workbook:
    wb = CREATE Workbook()
    ws = wb.active
    ws.title = "Content Scores"

    # --- Row 1: period sub-header ---
    MERGE CELLS A1:I1
    ws["A1"].value = f"Отчёт по контенту: {date_from} — {date_to}"
    ws["A1"].font = Font(bold=True, name="Calibri", size=12)
    ws["A1"].alignment = Alignment(horizontal="center")

    # --- Row 2: column headers ---
    FOR col_idx, (label, attr_name, width) IN ENUMERATE(_COLUMNS, start=1):
        cell = ws.cell(row=2, column=col_idx, value=label)
        cell.fill = HEADER_FILL        # solid #4472C4
        cell.font = HEADER_FONT        # bold white Calibri
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[col_letter(col_idx)].width = width    # explicit width — openpyxl has no auto-size

    ws.row_dimensions[2].height = 30
    ws.freeze_panes = "A3"             # freeze rows 1-2

    # --- Auto-filter ---
    ws.auto_filter.ref = "A2:I2"

    # --- Data rows (start at row 3) ---
    FOR row_idx, row IN ENUMERATE(rows, start=3):

        values = [
            row.brand_name,
            row.sku_article OR "—",    # NULL article → em-dash
            row.sku_name,
            row.platform_name,
            row.scored_at.isoformat(), # "YYYY-MM-DD" string
            _fmt_score(row.image_score),
            _fmt_score(row.description_score),
            _fmt_score(row.composition_score),
            _fmt_score(row.content_total),
        ]

        FOR col_idx, value IN ENUMERATE(values, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.font = BODY_FONT
            cell.alignment = Alignment(vertical="center")

        # Apply color fill to score columns 6-9 based on content_total
        fill = _score_fill(row.content_total)
        IF fill IS NOT None:
            FOR col_idx IN range(6, 10):   # columns 6, 7, 8, 9
                ws.cell(row=row_idx, column=col_idx).fill = fill

    RETURN wb
```

---

## Service: build_content_export (orchestrator)

```python
async def build_content_export(
    db: AsyncSession,
    org_id: UUID,
    date_from: date,
    date_to: date,
    platform_id: UUID | None = None,
) -> bytes:
    """
    Orchestrate query → build → serialise.
    Always returns bytes (never raises on empty result).
    """

    # Step 1: Query
    rows = AWAIT get_content_scores_for_export(
        db=db,
        org_id=org_id,
        date_from=date_from,
        date_to=date_to,
        platform_id=platform_id,
    )
    # rows may be empty list — that is valid (header-only workbook)

    # Step 2: Build workbook
    wb = _build_workbook(rows, date_from=date_from, date_to=date_to)

    # Step 3: Serialise to bytes (no disk I/O)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    RETURN buf.read()
```

---

## Router: export_content_scores

```python
GET /api/v1/reports/content-export

INPUTS:
  date_from: date  (Query, required)
  date_to:   date  (Query, required)
  platform_id: UUID | None  (Query, optional)
  db: AsyncSession  (Depends)
  current_user: User  (Depends get_current_user)

ALGORITHM:
  1. _validate_date_range(date_from, date_to)
         IF date_to < date_from:
             RAISE HTTP 400 "INVALID_DATE_RANGE: date_to must be >= date_from"
         IF (date_to - date_from).days > 366:
             RAISE HTTP 400 "INVALID_DATE_RANGE: maximum range is 366 days"

  2. TRY:
         xlsx_bytes = AWAIT service.build_content_export(
             db=db,
             org_id=current_user.org_id,    # tenant isolation — from JWT, not query param
             date_from=date_from,
             date_to=date_to,
             platform_id=platform_id,
         )
     EXCEPT any exception:
         LOG exception (server-side only)
         RAISE HTTP 500 "INTERNAL_ERROR"

  3. filename = f"content_scores_{date_from}_{date_to}.xlsx"

  4. RETURN Response(
         content=xlsx_bytes,
         media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         headers={
             "Content-Disposition": f'attachment; filename="{filename}"',
             "Content-Length": str(len(xlsx_bytes)),
         },
     )
```
