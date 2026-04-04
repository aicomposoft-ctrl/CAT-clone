# Pseudocode: Excel Export — Reviews

**Feature:** `excel-export-reviews`
**Date:** 2026-04-04

---

## 1. Repository: ReviewRow + get_reviews_for_export

```python
# services/api/app/reports/repository.py  (additions)

_ROW_LIMIT = 10_000

@dataclass(slots=True)
class ReviewRow:
    brand_name: str
    sku_article: Optional[str]
    sku_name: str
    platform_name: str
    review_date: date
    rating: Optional[int]
    sentiment: Optional[str]
    sentiment_score: Optional[Decimal]
    review_text: Optional[str]


async def get_reviews_for_export(
    db: AsyncSession,
    org_id: UUID,
    date_from: date,
    date_to: date,
    platform_id: Optional[UUID] = None,
    sentiment: Optional[str] = None,
    sku_id: Optional[UUID] = None,
) -> tuple[list[ReviewRow], bool]:
    """
    Returns (rows, truncated).
    truncated=True when result exceeds _ROW_LIMIT — caller adds warning row.
    """
    from app.reviews.models import Review

    stmt = (
        select(
            Brand.name.label("brand_name"),
            SKU.article.label("sku_article"),
            SKU.name.label("sku_name"),
            Platform.name.label("platform_name"),
            Review.review_date,
            Review.rating,
            Review.sentiment,
            Review.sentiment_score,
            Review.review_text,
        )
        .join(SKUPlatform, Review.sku_platform_id == SKUPlatform.id)
        .join(SKU, SKUPlatform.sku_id == SKU.id)
        .join(Brand, SKU.brand_id == Brand.id)
        .join(Platform, SKUPlatform.platform_id == Platform.id)
        .where(SKU.org_id == org_id)
        .where(Review.review_date >= date_from)
        .where(Review.review_date <= date_to)
        .order_by(
            Brand.name,
            SKU.article.nulls_last(),
            Platform.name,
            Review.review_date.desc(),
        )
        .limit(_ROW_LIMIT + 1)
    )

    if platform_id is not None:
        stmt = stmt.where(SKUPlatform.platform_id == platform_id)
    if sentiment is not None:
        stmt = stmt.where(Review.sentiment == sentiment)
    if sku_id is not None:
        stmt = stmt.where(SKU.id == sku_id)

    result = await db.execute(stmt)
    raw = result.all()

    truncated = len(raw) > _ROW_LIMIT
    rows = raw[:_ROW_LIMIT]

    return (
        [
            ReviewRow(
                brand_name=r.brand_name,
                sku_article=r.sku_article,
                sku_name=r.sku_name,
                platform_name=r.platform_name,
                review_date=r.review_date,
                rating=r.rating,
                sentiment=r.sentiment,
                sentiment_score=r.sentiment_score,
                review_text=r.review_text,
            )
            for r in rows
        ],
        truncated,
    )
```

---

## 2. Service: build_reviews_export + _build_reviews_workbook

```python
# services/api/app/reports/service.py  (additions)

_REVIEWS_COLUMNS: list[tuple[str, str, int]] = [
    ("Бренд", "brand_name", 20),
    ("Артикул", "sku_article", 15),
    ("Название SKU", "sku_name", 40),
    ("Платформа", "platform_name", 20),
    ("Дата отзыва", "review_date", 14),
    ("Рейтинг", "rating", 10),
    ("Тональность", "sentiment", 14),
    ("Оценка тональности", "sentiment_score", 20),
    ("Текст отзыва", "review_text", 60),
]

_SENTIMENT_FILLS = {
    "positive": PatternFill("solid", fgColor="C6EFCE"),
    "neutral":  PatternFill("solid", fgColor="FFEB9C"),
    "negative": PatternFill("solid", fgColor="FFC7CE"),
}

_MAX_TEXT_LEN = 500
_WARN_FILL = PatternFill("solid", fgColor="FFEB9C")


def _fmt_rating(value: Optional[int]) -> str:
    return "—" if value is None else str(value)


def _fmt_score_3dp(value: Optional[Decimal]) -> str:
    return "—" if value is None else f"{value:.3f}"


def _fmt_text(value: Optional[str]) -> str:
    if not value:
        return "—"
    return value if len(value) <= _MAX_TEXT_LEN else value[:_MAX_TEXT_LEN] + "…"


def _build_reviews_workbook(
    rows: list[ReviewRow],
    date_from: date,
    date_to: date,
    truncated: bool,
) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Reviews"

    num_cols = len(_REVIEWS_COLUMNS)
    col_range = get_column_letter(num_cols)

    # Row 1: merged period header
    ws.merge_cells(f"A1:{col_range}1")
    header_cell = ws["A1"]
    header_cell.value = f"Отчёт по отзывам: {date_from} — {date_to}"
    header_cell.font = Font(bold=True, name="Calibri", size=12)
    header_cell.alignment = Alignment(horizontal="center")

    # Row 2: column headers
    for col_idx, (label, _, width) in enumerate(_REVIEWS_COLUMNS, start=1):
        cell = ws.cell(row=2, column=col_idx, value=label)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    ws.row_dimensions[2].height = 30
    ws.freeze_panes = "A3"

    # Data rows starting at row 3
    for row_idx, row in enumerate(rows, start=3):
        values = [
            row.brand_name,
            row.sku_article or "—",
            row.sku_name,
            row.platform_name,
            row.review_date.isoformat(),
            _fmt_rating(row.rating),
            row.sentiment or "—",
            _fmt_score_3dp(row.sentiment_score),
            _fmt_text(row.review_text),
        ]

        for col_idx, value in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.font = _BODY_FONT
            cell.alignment = Alignment(
                vertical="center",
                wrap_text=(col_idx == 9),  # wrap review text column only
            )

        # Sentiment color on columns 7–8 only
        fill = _SENTIMENT_FILLS.get(row.sentiment) if row.sentiment else None
        if fill is not None:
            ws.cell(row=row_idx, column=7).fill = fill
            ws.cell(row=row_idx, column=8).fill = fill

    # Warning row when truncated
    if truncated:
        warn_row = len(rows) + 3
        ws.merge_cells(f"A{warn_row}:{col_range}{warn_row}")
        warn_cell = ws[f"A{warn_row}"]
        warn_cell.value = (
            "⚠ Превышен лимит 10 000 строк. "
            "Используйте фильтры для сужения выборки."
        )
        warn_cell.fill = _WARN_FILL
        warn_cell.font = Font(bold=True, name="Calibri", size=11)
        warn_cell.alignment = Alignment(horizontal="center")

    # Auto-filter
    ws.auto_filter.ref = f"A2:{col_range}2"

    return wb


async def build_reviews_export(
    db: AsyncSession,
    org_id: UUID,
    date_from: date,
    date_to: date,
    platform_id: Optional[UUID] = None,
    sentiment: Optional[str] = None,
    sku_id: Optional[UUID] = None,
) -> bytes:
    """
    Query reviews and return Excel bytes.

    Returns a header-only workbook when no reviews match the filters.
    """
    from app.reports.repository import get_reviews_for_export

    rows, truncated = await get_reviews_for_export(
        db=db,
        org_id=org_id,
        date_from=date_from,
        date_to=date_to,
        platform_id=platform_id,
        sentiment=sentiment,
        sku_id=sku_id,
    )

    wb = _build_reviews_workbook(rows, date_from=date_from, date_to=date_to, truncated=truncated)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
```

---

## 3. Router: GET /reviews-export

```python
# services/api/app/reports/router.py  (addition)

from typing import Literal, Optional
from app.catalog.repository import SKURepository

@router.get(
    "/reviews-export",
    summary="Export reviews with sentiment to Excel",
    response_class=Response,
    responses={
        200: {
            "content": {_EXCEL_CONTENT_TYPE: {}},
            "description": "Excel workbook with reviews and sentiment data",
        },
        400: {"description": "Invalid date range"},
        404: {"description": "SKU not found or not owned by caller"},
    },
)
async def export_reviews(
    date_from: date = Query(..., description="Start date inclusive (YYYY-MM-DD)"),
    date_to: date = Query(..., description="End date inclusive (YYYY-MM-DD)"),
    platform_id: Optional[UUID] = Query(None, description="Filter by platform UUID"),
    sentiment: Optional[Literal["positive", "neutral", "negative"]] = Query(
        None, description="Filter by sentiment label"
    ),
    sku_id: Optional[UUID] = Query(None, description="Filter by SKU UUID (must belong to caller's org)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """
    Download a .xlsx report of reviews (with sentiment) for the authenticated user's org.

    Optional filters: platform_id, sentiment, sku_id.
    When sku_id is provided, verifies the SKU belongs to the caller's org (404 on mismatch).
    Returns an empty workbook (header row only) when no reviews match the filters.
    """
    _validate_date_range(date_from, date_to)

    # Validate sku_id ownership if provided
    if sku_id is not None:
        sku = await SKURepository.get_by_id_and_org(db, sku_id=sku_id, org_id=current_user.org_id)
        if sku is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SKU_NOT_FOUND")

    try:
        xlsx_bytes = await service.build_reviews_export(
            db=db,
            org_id=current_user.org_id,
            date_from=date_from,
            date_to=date_to,
            platform_id=platform_id,
            sentiment=sentiment,
            sku_id=sku_id,
        )
    except Exception:
        logger.exception("Unexpected error generating reviews export")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="INTERNAL_ERROR",
        )

    filename = f"reviews_{date_from}_{date_to}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type=_EXCEL_CONTENT_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(xlsx_bytes)),
        },
    )
```

---

## 4. No Changes Required

- `services/api/app/main.py` — `reports_router` already registered at `/api/v1/reports`
- No DB migration
- `services/api/app/reviews/models.py` — `Review` model already exists

---

## 5. Test Skeleton

```python
# services/api/tests/e2e/test_reviews_export.py

class TestReviewsExport:
    # test_export_returns_xlsx_bytes
    # test_export_empty_range_returns_header_only
    # test_export_sentiment_filter
    # test_export_platform_filter
    # test_export_sku_filter_owned
    # test_export_sku_filter_cross_tenant_returns_404
    # test_export_inverted_date_returns_400
    # test_export_date_range_over_366_days_returns_400
    # test_export_unauthenticated_returns_401
    # test_export_viewer_can_download
    # test_export_invalid_sentiment_returns_422

class TestBuildReviewsWorkbook:
    # test_sentiment_color_positive
    # test_sentiment_color_negative
    # test_sentiment_color_neutral
    # test_null_sentiment_no_fill
    # test_review_text_truncated_at_500
    # test_truncated_flag_adds_warning_row
    # test_rating_null_formatted_as_dash
    # test_header_structure_row1_merged_row2_headers
```
