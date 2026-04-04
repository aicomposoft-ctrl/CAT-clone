"""
Excel generation service for the reports domain.

Produces an openpyxl workbook in memory (BytesIO) — no disk I/O.
The caller receives the raw bytes and streams them as an HTTP response.

Color thresholds for content_total:
  >= 80  → green  (#C6EFCE / #375623)
  50-79  → yellow (#FFEB9C / #9C6500)
  < 50   → red    (#FFC7CE / #9C0006)
  NULL   → no fill
"""

import io
from datetime import date
from decimal import Decimal
from typing import Optional

import uuid
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy.ext.asyncio import AsyncSession

from app.reports.repository import (
    ContentScoreRow,
    ReviewRow,
    StockRow,
    get_content_scores_for_export,
    get_reviews_for_export,
    get_stock_data_for_export,
)

# Column definitions: (header label, attribute name, column width)
_COLUMNS: list[tuple[str, str, int]] = [
    ("Бренд", "brand_name", 20),
    ("Артикул", "sku_article", 15),
    ("Название SKU", "sku_name", 40),
    ("Платформа", "platform_name", 20),
    ("Дата оценки", "scored_at", 14),
    ("Оценка изображения", "image_score", 20),
    ("Оценка описания", "description_score", 18),
    ("Оценка состава", "composition_score", 17),
    ("Итого контент", "content_total", 16),
]

_HEADER_FILL = PatternFill("solid", fgColor="4472C4")
_HEADER_FONT = Font(bold=True, color="FFFFFF", name="Calibri")
_BODY_FONT = Font(name="Calibri", size=11)

_SCORE_FILLS = {
    "green": PatternFill("solid", fgColor="C6EFCE"),
    "yellow": PatternFill("solid", fgColor="FFEB9C"),
    "red": PatternFill("solid", fgColor="FFC7CE"),
}


def _score_fill(value: Optional[Decimal]) -> Optional[PatternFill]:
    if value is None:
        return None
    if value >= 80:
        return _SCORE_FILLS["green"]
    if value >= 50:
        return _SCORE_FILLS["yellow"]
    return _SCORE_FILLS["red"]


def _fmt_score(value: Optional[Decimal]) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}"


def _build_workbook(rows: list[ContentScoreRow], date_from: date, date_to: date) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Content Scores"

    # Sub-header with report period
    ws.merge_cells("A1:I1")
    period_cell = ws["A1"]
    period_cell.value = f"Отчёт по контенту: {date_from} — {date_to}"
    period_cell.font = Font(bold=True, name="Calibri", size=12)
    period_cell.alignment = Alignment(horizontal="center")

    # Column headers in row 2
    for col_idx, (label, _, width) in enumerate(_COLUMNS, start=1):
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
            row.scored_at.isoformat(),
            _fmt_score(row.image_score),
            _fmt_score(row.description_score),
            _fmt_score(row.composition_score),
            _fmt_score(row.content_total),
        ]
        for col_idx, value in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.font = _BODY_FONT
            cell.alignment = Alignment(vertical="center")

        # Apply color fill to score columns (6-9) based on content_total
        fill = _score_fill(row.content_total)
        if fill is not None:
            for col_idx in range(6, 10):
                ws.cell(row=row_idx, column=col_idx).fill = fill

    # Auto-filter on headers
    ws.auto_filter.ref = f"A2:{get_column_letter(len(_COLUMNS))}2"

    return wb


_STOCK_COLUMNS: list[tuple[str, int]] = [
    ("Бренд", 20),
    ("Артикул", 15),
    ("Название SKU", 40),
    ("Платформа", 20),
    ("Дата сбора", 14),
    ("Неделя", 9),
    ("Год", 7),
    ("В наличии", 12),
    ("Остаток на складе", 20),
    ("План (ТТ)", 12),
]

_STOCK_FILLS = {
    "in_stock": PatternFill("solid", fgColor="C6EFCE"),
    "out_of_stock": PatternFill("solid", fgColor="FFC7CE"),
}


def _fmt_bool(value: Optional[bool]) -> str:
    if value is None:
        return "—"
    return "Да" if value else "Нет"


def _fmt_int(value: Optional[int]) -> str:
    if value is None:
        return "—"
    return str(value)


def _stock_row_fill(in_stock: Optional[bool]) -> Optional[PatternFill]:
    if in_stock is True:
        return _STOCK_FILLS["in_stock"]
    if in_stock is False:
        return _STOCK_FILLS["out_of_stock"]
    return None


def _build_stock_workbook(rows: list[StockRow], date_from: date, date_to: date) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Stock"

    num_cols = len(_STOCK_COLUMNS)

    ws.merge_cells(f"A1:{get_column_letter(num_cols)}1")
    period_cell = ws["A1"]
    period_cell.value = f"Отчёт по дистрибуции: {date_from} — {date_to}"
    period_cell.font = Font(bold=True, name="Calibri", size=12)
    period_cell.alignment = Alignment(horizontal="center")

    for col_idx, (label, width) in enumerate(_STOCK_COLUMNS, start=1):
        cell = ws.cell(row=2, column=col_idx, value=label)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    ws.row_dimensions[2].height = 30
    ws.freeze_panes = "A3"

    for row_idx, row in enumerate(rows, start=3):
        values = [
            row.brand_name,
            row.sku_article or "—",
            row.sku_name,
            row.platform_name,
            row.scored_at.isoformat(),
            row.week_number,
            row.year,
            _fmt_bool(row.in_stock),
            _fmt_int(row.warehouse_qty),
            _fmt_int(row.plan_tt_count),
        ]
        fill = _stock_row_fill(row.in_stock)
        for col_idx, value in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.font = _BODY_FONT
            cell.alignment = Alignment(vertical="center")
            if fill is not None:
                cell.fill = fill

    ws.auto_filter.ref = f"A2:{get_column_letter(num_cols)}2"
    return wb


async def build_stock_export(
    db: AsyncSession,
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
    platform_id: Optional[uuid.UUID] = None,
) -> bytes:
    """
    Query stock fact data (joined with distribution plan) and return Excel bytes.

    Returns a header-only workbook when no stock data matches the filters.
    """
    rows = await get_stock_data_for_export(
        db=db,
        org_id=org_id,
        date_from=date_from,
        date_to=date_to,
        platform_id=platform_id,
    )

    wb = _build_stock_workbook(rows, date_from=date_from, date_to=date_to)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


async def build_content_export(
    db: AsyncSession,
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
    platform_id: Optional[uuid.UUID] = None,
) -> bytes:
    """
    Query content scores and return Excel file as bytes.

    Returns an empty workbook (header only) when no data matches the filters.
    Never raises on empty result — that is a valid state.
    """
    rows = await get_content_scores_for_export(
        db=db,
        org_id=org_id,
        date_from=date_from,
        date_to=date_to,
        platform_id=platform_id,
    )

    wb = _build_workbook(rows, date_from=date_from, date_to=date_to)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# Reviews export
# ---------------------------------------------------------------------------

_REVIEWS_COLUMNS: list[tuple[str, int]] = [
    ("Бренд", 20),
    ("Артикул", 15),
    ("Название SKU", 40),
    ("Платформа", 20),
    ("Дата отзыва", 14),
    ("Рейтинг", 10),
    ("Тональность", 14),
    ("Оценка тональности", 20),
    ("Текст отзыва", 60),
]

_SENTIMENT_FILLS = {
    "positive": PatternFill("solid", fgColor="C6EFCE"),
    "neutral": PatternFill("solid", fgColor="FFEB9C"),
    "negative": PatternFill("solid", fgColor="FFC7CE"),
}

_WARN_FILL = PatternFill("solid", fgColor="FFEB9C")
_MAX_REVIEW_TEXT_LEN = 500


def _fmt_rating(value: Optional[int]) -> str:
    return "—" if value is None else str(value)


def _fmt_score_3dp(value: Optional[Decimal]) -> str:
    return "—" if value is None else f"{value:.3f}"


def _fmt_review_text(value: Optional[str]) -> str:
    if not value:
        return "—"
    return value if len(value) <= _MAX_REVIEW_TEXT_LEN else value[:_MAX_REVIEW_TEXT_LEN] + "…"


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
    period_cell = ws["A1"]
    period_cell.value = f"Отчёт по отзывам: {date_from} — {date_to}"
    period_cell.font = Font(bold=True, name="Calibri", size=12)
    period_cell.alignment = Alignment(horizontal="center")

    # Row 2: column headers
    for col_idx, (label, width) in enumerate(_REVIEWS_COLUMNS, start=1):
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
            _fmt_review_text(row.review_text),
        ]

        for col_idx, value in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.font = _BODY_FONT
            cell.alignment = Alignment(
                vertical="center",
                wrap_text=(col_idx == 9),
            )

        # Sentiment color on columns 7–8 only
        fill = _SENTIMENT_FILLS.get(row.sentiment) if row.sentiment else None
        if fill is not None:
            ws.cell(row=row_idx, column=7).fill = fill
            ws.cell(row=row_idx, column=8).fill = fill

    # Warning row when result was truncated
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

    ws.auto_filter.ref = f"A2:{col_range}2"
    return wb


async def build_reviews_export(
    db: AsyncSession,
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
    platform_id: Optional[uuid.UUID] = None,
    sentiment: Optional[str] = None,
    sku_id: Optional[uuid.UUID] = None,
) -> bytes:
    """
    Query reviews and return Excel bytes.

    Returns a header-only workbook when no reviews match the filters.
    Never raises on empty result — that is a valid state.
    """
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
