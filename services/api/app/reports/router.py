"""
HTTP routes for the reports domain.

Endpoints:
  GET /api/v1/reports/content-export
      Returns Excel (.xlsx) with content scores for the caller's org.
      Query params:
        date_from   — required, ISO date (YYYY-MM-DD)
        date_to     — required, ISO date (YYYY-MM-DD), must be >= date_from
        platform_id — optional UUID, filters to a single platform

  Accessible by all authenticated roles (admin, manager, viewer).
  Max date range: 366 days.
"""

import logging
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.deps import get_current_user, get_db
from app.reports import service

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_DATE_RANGE_DAYS = 366
_EXCEL_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


@router.get(
    "/content-export",
    summary="Export content scores to Excel",
    response_class=Response,
    responses={
        200: {
            "content": {_EXCEL_CONTENT_TYPE: {}},
            "description": "Excel workbook with content scores",
        },
        400: {"description": "Invalid date range"},
    },
)
async def export_content_scores(
    date_from: date = Query(..., description="Start date inclusive (YYYY-MM-DD)"),
    date_to: date = Query(..., description="End date inclusive (YYYY-MM-DD)"),
    platform_id: Optional[UUID] = Query(None, description="Filter by platform UUID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """
    Download a .xlsx report of content scores for the authenticated user's org.

    The response is streamed directly from memory — no temporary files are created.
    Returns an empty workbook (header row only) when no scores match the filters.
    """
    if date_to < date_from:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="INVALID_DATE_RANGE: date_to must be >= date_from",
        )

    if (date_to - date_from).days > _MAX_DATE_RANGE_DAYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"INVALID_DATE_RANGE: maximum range is {_MAX_DATE_RANGE_DAYS} days",
        )

    try:
        xlsx_bytes = await service.build_content_export(
            db=db,
            org_id=current_user.org_id,
            date_from=date_from,
            date_to=date_to,
            platform_id=platform_id,
        )
    except Exception:
        logger.exception("Unexpected error generating content export")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="INTERNAL_ERROR",
        )

    filename = f"content_scores_{date_from}_{date_to}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type=_EXCEL_CONTENT_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(xlsx_bytes)),
        },
    )
