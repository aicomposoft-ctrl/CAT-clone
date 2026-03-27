# Snippet: Excel Report Streaming via BytesIO
# Category: Snippet | Language: Python
# Maturity: 🔴 Alpha | Extracted: 2026-03-27 from CAT project
#
# When to Use:
#   Generating Excel files in a web API (FastAPI, Django, Flask) and returning
#   them as a download without writing to disk.
#
# When NOT to Use:
#   - Files >50MB (stream to S3 instead and return presigned URL)
#   - Repeated identical reports (cache the bytes in Redis/S3)
#   - When CSV is sufficient (simpler, faster, no openpyxl dependency)
#
# Prerequisites: openpyxl>=3.0
# Dependencies: openpyxl, fastapi (for response example)

import io
from typing import Any
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter


def build_excel_report(
    title: str,
    headers: list[str],
    rows: list[list[Any]],
    freeze_header: bool = True,
) -> bytes:
    """
    Build an Excel workbook and return it as bytes (no disk I/O).

    Args:
        title:          Sheet name (max 31 chars for Excel compatibility)
        headers:        Column header labels
        rows:           Data rows — each row is a list matching header count
        freeze_header:  Freeze the first row (default: True)

    Returns:
        Raw .xlsx bytes suitable for HTTP response or S3 upload.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title[:31]  # Excel limit

    # Header row with styling
    header_fill = PatternFill("solid", fgColor="4472C4")
    header_font = Font(bold=True, color="FFFFFF")
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    # Data rows
    for row_idx, row in enumerate(rows, start=2):
        for col_idx, value in enumerate(row, start=1):
            ws.cell(row=row_idx, column=col_idx, value=value)

    # Auto column widths (openpyxl has no auto-size — must set explicitly)
    for col_idx, header in enumerate(headers, start=1):
        col_letter = get_column_letter(col_idx)
        max_length = max(
            len(str(header)),
            *(len(str(row[col_idx - 1])) for row in rows if row) if rows else [0],
        )
        ws.column_dimensions[col_letter].width = min(max_length + 4, 60)

    if freeze_header:
        ws.freeze_panes = "A2"  # freeze row 1

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# --- FastAPI streaming response ---
#
# from fastapi.responses import Response
#
# @router.get("/reports/export")
# async def export_report(org_id: UUID = Depends(get_org)):
#     data = await report_service.get_data(org_id)
#     excel_bytes = build_excel_report(
#         title="Monthly Report",
#         headers=["SKU", "Platform", "Score", "Date"],
#         rows=[[r.sku, r.platform, r.score, r.date] for r in data],
#     )
#     return Response(
#         content=excel_bytes,
#         media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
#         headers={"Content-Disposition": "attachment; filename=report.xlsx"},
#     )
