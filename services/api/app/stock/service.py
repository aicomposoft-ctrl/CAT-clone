"""
Business logic for the stock domain.

No SQLAlchemy sessions are imported here — db: AsyncSession arrives via
dependency injection and is forwarded to repository functions.
"""

import csv
import io
import logging
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.stock import repository
from app.stock.schemas import DistributionPlanRow, DistributionPlanUploadResponse, RowError

logger = logging.getLogger(__name__)

_MAX_ROWS = 10_000
_MAX_ERRORS = 100  # cap error list to prevent DoS via response bloat

REQUIRED_COLUMNS = frozenset(
    {"sku_barcode", "platform_name", "group_name", "plan_tt_count", "week_number", "year"}
)


class ServiceValidationError(Exception):
    """Raised for file-level validation failures (bad header, empty file, etc.)."""


@dataclass
class _ParsedRow:
    row_index: int
    sku_barcode: str
    platform_name: str
    group_name: str
    plan_tt_count: int
    week_number: int
    year: int
    sku_id: UUID = field(default=None)      # filled after barcode lookup
    platform_id: UUID = field(default=None)  # filled after platform lookup


def _detect_encoding(raw_bytes: bytes) -> str:
    """
    Detect CSV encoding. Tries UTF-8-sig (Excel BOM) then plain UTF-8.
    Falls back to cp1251 for Russian Windows exports.
    """
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        raw_bytes.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    return "cp1251"


def _validate_row(row_index: int, raw: dict) -> list[RowError]:
    """Validate a single CSV row. Returns list of RowError (empty = valid)."""
    errors: list[RowError] = []

    if not raw.get("sku_barcode", "").strip():
        errors.append(RowError(row=row_index, field="sku_barcode", message="Cannot be empty"))

    if not raw.get("platform_name", "").strip():
        errors.append(RowError(row=row_index, field="platform_name", message="Cannot be empty"))

    group = raw.get("group_name", "").strip()
    if not group:
        errors.append(RowError(row=row_index, field="group_name", message="Cannot be empty"))
    elif len(group) > 100:
        errors.append(
            RowError(row=row_index, field="group_name", message="Exceeds 100 character limit")
        )

    try:
        count = int(raw.get("plan_tt_count", ""))
        if count < 0:
            raise ValueError
    except (ValueError, TypeError):
        errors.append(
            RowError(
                row=row_index,
                field="plan_tt_count",
                message="Must be a non-negative integer",
            )
        )

    try:
        week = int(raw.get("week_number", ""))
        if not (1 <= week <= 53):
            raise ValueError
    except (ValueError, TypeError):
        errors.append(
            RowError(
                row=row_index,
                field="week_number",
                message="Must be an integer between 1 and 53",
            )
        )

    try:
        year = int(raw.get("year", ""))
        if not (2000 <= year <= 2100):
            raise ValueError
    except (ValueError, TypeError):
        errors.append(
            RowError(
                row=row_index,
                field="year",
                message="Must be a 4-digit year between 2000 and 2100",
            )
        )

    return errors


async def upload_distribution_plan(
    db: AsyncSession,
    raw_bytes: bytes,
    org_id: UUID,
) -> DistributionPlanUploadResponse:
    """
    Parse and import a distribution plan CSV.

    Row-level errors do NOT abort the import — valid rows are always imported
    and errors are returned alongside the imported count.
    File-level failures raise ServiceValidationError.
    """
    # Step 1: Encoding detection
    encoding = _detect_encoding(raw_bytes)
    try:
        text = raw_bytes.decode(encoding)
    except UnicodeDecodeError as exc:
        raise ServiceValidationError(
            f"File encoding error: unable to decode as {encoding}. "
            "Please save the file in UTF-8 encoding and re-upload."
        ) from exc

    # Step 2: CSV header validation (strip column names to handle trailing spaces)
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames:
        reader.fieldnames = [f.strip() for f in reader.fieldnames]
    actual_columns = set(reader.fieldnames or [])
    missing = REQUIRED_COLUMNS - actual_columns
    if missing:
        raise ServiceValidationError(f"Missing columns: {sorted(missing)}")

    # Step 3: Row-level parsing (with row limit guard)
    all_rows = list(reader)
    if len(all_rows) > _MAX_ROWS:
        raise ServiceValidationError(
            f"CSV exceeds {_MAX_ROWS:,} row limit. Split the file and re-upload."
        )
    if not all_rows:
        raise ServiceValidationError("CSV file contains no data rows")

    parsed_rows: list[_ParsedRow] = []
    row_errors: list[RowError] = []

    for row_index, raw_row in enumerate(all_rows, start=2):  # row 1 = header
        errors_in_row = _validate_row(row_index, raw_row)
        if errors_in_row:
            row_errors.extend(errors_in_row)
            continue
        parsed_rows.append(
            _ParsedRow(
                row_index=row_index,
                sku_barcode=raw_row["sku_barcode"].strip(),
                platform_name=raw_row["platform_name"].strip(),
                group_name=raw_row["group_name"].strip(),
                plan_tt_count=int(raw_row["plan_tt_count"]),
                week_number=int(raw_row["week_number"]),
                year=int(raw_row["year"]),
            )
        )

    # Step 4: Batch SKU barcode lookup (tenant-scoped)
    all_barcodes = list({r.sku_barcode for r in parsed_rows})
    barcode_map = await repository.lookup_skus_by_barcode(db, all_barcodes, org_id)

    valid_rows: list[_ParsedRow] = []
    for row in parsed_rows:
        if row.sku_barcode not in barcode_map:
            row_errors.append(
                RowError(
                    row=row.row_index,
                    field="sku_barcode",
                    message="SKU barcode not found in your organisation",
                )
            )
        else:
            row.sku_id = barcode_map[row.sku_barcode]
            valid_rows.append(row)

    # Step 5: Batch platform name lookup (global catalog)
    all_platform_names = list({r.platform_name for r in valid_rows})
    platform_map = await repository.lookup_platforms_by_name(db, all_platform_names)

    upsert_rows: list[_ParsedRow] = []
    for row in valid_rows:
        key = row.platform_name.lower()
        if key not in platform_map:
            row_errors.append(
                RowError(
                    row=row.row_index,
                    field="platform_name",
                    message=(
                        f"Platform '{row.platform_name}' not found. "
                        "Check spelling or contact support to add it."
                    ),
                )
            )
        else:
            row.platform_id = platform_map[key]
            upsert_rows.append(row)

    # Step 6: UPSERT valid rows
    imported_count = 0
    if upsert_rows:
        upsert_dicts = [
            {
                "id": uuid4(),
                "sku_id": r.sku_id,
                "platform_id": r.platform_id,
                "group_name": r.group_name[:100],
                "plan_tt_count": r.plan_tt_count,
                "week_number": r.week_number,
                "year": r.year,
            }
            for r in upsert_rows
        ]
        try:
            result_rows = await repository.upsert_plans(db, upsert_dicts)
            imported_count = len(result_rows)
        except SQLAlchemyError as exc:
            logger.error("DB error during plan upsert: %s", exc)
            raise ServiceValidationError(
                "Database error during import. Verify CSV data and retry."
            ) from exc

    # Cap error list to prevent response bloat on malformed files
    return DistributionPlanUploadResponse(
        imported=imported_count,
        errors=row_errors[:_MAX_ERRORS],
    )


async def list_distribution_plans(
    db: AsyncSession,
    org_id: UUID,
    platform_id: UUID | None,
    week_number: int | None,
    year: int | None,
    page: int,
    size: int,
) -> tuple[list[DistributionPlanRow], int]:
    """Return a paginated page of distribution plans for the org."""
    page = max(1, page)
    size = max(1, min(200, size))
    offset = (page - 1) * size

    items, total = await repository.list_plans(
        db=db,
        org_id=org_id,
        platform_id=platform_id,
        week_number=week_number,
        year=year,
        limit=size,
        offset=offset,
    )
    rows = [DistributionPlanRow(**item) for item in items]
    return rows, total


async def delete_distribution_plan(
    db: AsyncSession,
    plan_id: UUID,
    org_id: UUID,
) -> bool:
    """Delete a plan. Returns False if not found or not owned by org."""
    return await repository.delete_plan(db, plan_id, org_id)
