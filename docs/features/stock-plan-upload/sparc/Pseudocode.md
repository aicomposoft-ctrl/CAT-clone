# Pseudocode: stock-plan-upload

**Feature:** Distribution Plan Upload
**Service:** `services/api/app/stock/`
**Last Updated:** 2026-03-31

---

## 1. POST /api/v1/stock/distribution-plan

### router.py — upload_distribution_plan_endpoint

```
FUNCTION upload_distribution_plan_endpoint(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(["admin", "manager"]))
) -> DistributionPlanUploadResponse:

    # --- File validation ---
    IF file.content_type NOT IN ("text/csv", "application/csv", "application/octet-stream"):
        RAISE HTTP 422 "INVALID_CONTENT_TYPE: expected text/csv"

    raw_bytes = await file.read()

    IF len(raw_bytes) > 5 * 1024 * 1024:   # 5 MB hard limit
        RAISE HTTP 422 "FILE_TOO_LARGE: maximum 5 MB"

    IF len(raw_bytes) == 0:
        RAISE HTTP 422 "EMPTY_FILE"

    # --- Delegate to service ---
    TRY:
        result = await service.upload_distribution_plan(
            db=db,
            raw_bytes=raw_bytes,
            org_id=current_user.org_id,
        )
        RETURN DistributionPlanUploadResponse(
            imported=result.imported,
            errors=result.errors,
        )
    EXCEPT ServiceValidationError AS exc:
        RAISE HTTP 422 detail=str(exc)
    EXCEPT Exception:
        LOG.exception("Unexpected error in distribution plan upload")
        RAISE HTTP 500 "INTERNAL_ERROR"
```

---

### service.py — upload_distribution_plan

```
FUNCTION upload_distribution_plan(
    db: AsyncSession,
    raw_bytes: bytes,
    org_id: UUID,
) -> UploadResult:

    # ── Step 1: Encoding detection ────────────────────────────────────────────
    encoding = detect_encoding(raw_bytes)
    # Attempt UTF-8 first; fall back to cp1251 for Russian Windows exports.
    # chardet.detect() is used; if confidence < 0.7, default to "utf-8-sig".
    TRY:
        text = raw_bytes.decode(encoding)
    EXCEPT UnicodeDecodeError:
        text = raw_bytes.decode("cp1251", errors="replace")

    # ── Step 2: CSV header validation ─────────────────────────────────────────
    reader = csv.DictReader(io.StringIO(text))
    REQUIRED_COLUMNS = {
        "sku_barcode", "platform_name", "group_name",
        "plan_tt_count", "week_number", "year"
    }
    IF NOT REQUIRED_COLUMNS.issubset(set(reader.fieldnames or [])):
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        RAISE ServiceValidationError(f"Missing columns: {missing}")

    # ── Step 3: Row-level parsing and validation ───────────────────────────────
    parsed_rows: list[ParsedRow] = []
    row_errors: list[RowError] = []

    FOR row_index, raw_row IN enumerate(reader, start=2):  # row 1 = header
        errors_in_row = validate_row(row_index, raw_row)
        IF errors_in_row:
            row_errors.extend(errors_in_row)
            CONTINUE  # skip row; do not add to parsed_rows
        parsed_rows.append(
            ParsedRow(
                row_index=row_index,
                sku_barcode=raw_row["sku_barcode"].strip(),
                platform_name=raw_row["platform_name"].strip(),
                group_name=raw_row["group_name"].strip(),
                plan_tt_count=int(raw_row["plan_tt_count"]),
                week_number=int(raw_row["week_number"]),
                year=int(raw_row["year"]),
            )
        )

    IF NOT parsed_rows AND NOT row_errors:
        RAISE ServiceValidationError("CSV file contains no data rows")

    # ── Step 4: Batch lookup — SKU barcodes → sku_id (tenant-scoped) ──────────
    all_barcodes = list({ r.sku_barcode FOR r IN parsed_rows })
    barcode_map: dict[str, UUID] = await repository.lookup_skus_by_barcode(
        db=db,
        barcodes=all_barcodes,
        org_id=org_id,
    )
    # Mark rows where barcode not found as errors; remove from parsed_rows
    valid_rows: list[ParsedRow] = []
    FOR row IN parsed_rows:
        IF row.sku_barcode NOT IN barcode_map:
            row_errors.append(RowError(
                row=row.row_index,
                field="sku_barcode",
                message=f"SKU with barcode '{row.sku_barcode}' not found in your organisation",
            ))
        ELSE:
            row.sku_id = barcode_map[row.sku_barcode]
            valid_rows.append(row)

    # ── Step 5: Batch lookup — platform names → platform_id (global) ──────────
    all_platform_names = list({ r.platform_name FOR r IN valid_rows })
    platform_map: dict[str, UUID] = await repository.lookup_platforms_by_name(
        db=db,
        names=all_platform_names,
    )
    # Mark unresolved platforms; remove from valid_rows
    upsert_rows: list[ParsedRow] = []
    FOR row IN valid_rows:
        key = row.platform_name.lower()
        IF key NOT IN platform_map:
            row_errors.append(RowError(
                row=row.row_index,
                field="platform_name",
                message=f"Platform '{row.platform_name}' not found. "
                        "Check spelling or contact support to add it.",
            ))
        ELSE:
            row.platform_id = platform_map[key]
            upsert_rows.append(row)

    # ── Step 6: UPSERT valid rows ──────────────────────────────────────────────
    imported_count = 0
    IF upsert_rows:
        upsert_dicts = [
            {
                "id":            uuid4(),
                "sku_id":        r.sku_id,
                "platform_id":   r.platform_id,
                "group_name":    r.group_name[:100],  # enforce DB column length
                "plan_tt_count": r.plan_tt_count,
                "week_number":   r.week_number,
                "year":          r.year,
            }
            FOR r IN upsert_rows
        ]
        TRY:
            result_rows = await repository.upsert_plans(db=db, rows=upsert_dicts)
            imported_count = len(result_rows)
        EXCEPT DBIntegrityError AS exc:
            LOG.error("DB integrity error during plan upsert: %s", exc)
            RAISE ServiceValidationError("Database error during import. "
                                         "Verify CSV data and retry.")

    # ── Step 7: Return result ──────────────────────────────────────────────────
    RETURN UploadResult(imported=imported_count, errors=row_errors)
```

---

### service.py — validate_row (helper)

```
FUNCTION validate_row(row_index: int, raw: dict) -> list[RowError]:
    errors = []

    # sku_barcode: non-empty string
    IF NOT raw.get("sku_barcode", "").strip():
        errors.append(RowError(row=row_index, field="sku_barcode", message="Cannot be empty"))

    # platform_name: non-empty string
    IF NOT raw.get("platform_name", "").strip():
        errors.append(RowError(row=row_index, field="platform_name", message="Cannot be empty"))

    # group_name: non-empty string, max 100 chars
    group = raw.get("group_name", "").strip()
    IF NOT group:
        errors.append(RowError(row=row_index, field="group_name", message="Cannot be empty"))
    ELIF len(group) > 100:
        errors.append(RowError(row=row_index, field="group_name",
                               message="Exceeds 100 character limit"))

    # plan_tt_count: integer ≥ 0
    TRY:
        count = int(raw.get("plan_tt_count", ""))
        IF count < 0:
            RAISE ValueError
    EXCEPT (ValueError, TypeError):
        errors.append(RowError(row=row_index, field="plan_tt_count",
                               message="Must be a non-negative integer"))

    # week_number: integer 1–53
    TRY:
        week = int(raw.get("week_number", ""))
        IF NOT (1 <= week <= 53):
            RAISE ValueError
    EXCEPT (ValueError, TypeError):
        errors.append(RowError(row=row_index, field="week_number",
                               message="Must be an integer between 1 and 53"))

    # year: integer 2000–2100
    TRY:
        year = int(raw.get("year", ""))
        IF NOT (2000 <= year <= 2100):
            RAISE ValueError
    EXCEPT (ValueError, TypeError):
        errors.append(RowError(row=row_index, field="year",
                               message="Must be a 4-digit year between 2000 and 2100"))

    RETURN errors
```

---

## 2. GET /api/v1/stock/distribution-plan

### router.py — list_distribution_plans_endpoint

```
FUNCTION list_distribution_plans_endpoint(
    platform_id: UUID | None = Query(None),
    week_number: int | None = Query(None, ge=1, le=53),
    year: int | None = Query(None, ge=2000, le=2100),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DistributionPlanPage:

    filters = PlanFilters(
        platform_id=platform_id,
        week_number=week_number,
        year=year,
    )
    TRY:
        items, total = await service.list_distribution_plans(
            db=db,
            org_id=current_user.org_id,
            filters=filters,
            page=page,
            size=size,
        )
        RETURN DistributionPlanPage(
            items=items,
            total=total,
            page=page,
            size=size,
        )
    EXCEPT Exception:
        LOG.exception("Error listing distribution plans")
        RAISE HTTP 500 "INTERNAL_ERROR"
```

---

### service.py — list_distribution_plans

```
FUNCTION list_distribution_plans(
    db: AsyncSession,
    org_id: UUID,
    filters: PlanFilters,
    page: int,
    size: int,
) -> tuple[list[DistributionPlanRow], int]:

    IF page < 1:  page = 1
    IF size < 1:  size = 50
    IF size > 200: size = 200

    offset = (page - 1) * size

    items, total = await repository.list_plans(
        db=db,
        org_id=org_id,
        platform_id=filters.platform_id,
        week_number=filters.week_number,
        year=filters.year,
        limit=size,
        offset=offset,
    )

    # Map ORM objects to Pydantic response schema
    rows = [
        DistributionPlanRow(
            id=plan.id,
            sku_id=plan.sku_id,
            platform_id=plan.platform_id,
            group_name=plan.group_name,
            plan_tt_count=plan.plan_tt_count,
            week_number=plan.week_number,
            year=plan.year,
        )
        FOR plan IN items
    ]
    RETURN rows, total
```

---

## 3. Repository Layer (async SQLAlchemy)

### repository.py — upsert_plans

```
FUNCTION upsert_plans(
    db: AsyncSession,
    rows: list[dict],  # pre-validated; sku_id ownership already confirmed
) -> list[DistributionPlan]:
    """
    Batch INSERT with ON CONFLICT DO UPDATE.
    Uses PostgreSQL dialect insert() for native UPSERT.
    Org isolation guarantee: sku_id values were resolved via
    lookup_skus_by_barcode(org_id=...) in the service layer.
    """
    IF NOT rows:
        RETURN []

    stmt = pg_insert(DistributionPlan).values(rows)
    upsert_stmt = stmt.on_conflict_do_update(
        index_elements=["sku_id", "platform_id", "week_number", "year"],
        set_={
            "plan_tt_count": stmt.excluded.plan_tt_count,
            "group_name":    stmt.excluded.group_name,
        },
    ).returning(DistributionPlan)

    TRY:
        result = await db.execute(upsert_stmt)
        await db.commit()
        RETURN list(result.scalars().all())
    EXCEPT SQLAlchemyError:
        await db.rollback()
        RAISE  # caller (service) wraps in ServiceValidationError
```

---

### repository.py — list_plans

```
FUNCTION list_plans(
    db: AsyncSession,
    org_id: UUID,
    platform_id: UUID | None,
    week_number: int | None,
    year: int | None,
    limit: int,
    offset: int,
) -> tuple[list[DistributionPlan], int]:
    """
    Returns (items, total_count).
    Tenant isolation enforced by JOIN to skus.org_id — mandatory, never remove.
    """
    base_query = (
        select(DistributionPlan)
        .join(SKU, SKU.id == DistributionPlan.sku_id)
        .where(SKU.org_id == org_id)
    )

    IF platform_id IS NOT None:
        base_query = base_query.where(DistributionPlan.platform_id == platform_id)
    IF week_number IS NOT None:
        base_query = base_query.where(DistributionPlan.week_number == week_number)
    IF year IS NOT None:
        base_query = base_query.where(DistributionPlan.year == year)

    # Total count (same filters, no pagination)
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Paginated data
    data_query = (
        base_query
        .order_by(DistributionPlan.year.desc(), DistributionPlan.week_number.desc())
        .limit(limit)
        .offset(offset)
    )
    data_result = await db.execute(data_query)
    items = list(data_result.scalars().all())

    RETURN items, total
```

---

### repository.py — delete_plan

```
FUNCTION delete_plan(
    db: AsyncSession,
    plan_id: UUID,
    org_id: UUID,
) -> bool:
    """
    Delete only if sku_id belongs to org_id (prevents cross-tenant delete).
    Returns True if a row was deleted, False if not found / not owned.
    """
    # Subquery confirms org ownership without loading the full row
    owned_sku_subq = select(SKU.id).where(SKU.org_id == org_id)

    stmt = (
        delete(DistributionPlan)
        .where(DistributionPlan.id == plan_id)
        .where(DistributionPlan.sku_id.in_(owned_sku_subq))
    )
    result = await db.execute(stmt)
    await db.commit()

    RETURN result.rowcount > 0
```

---

### repository.py — lookup_skus_by_barcode

```
FUNCTION lookup_skus_by_barcode(
    db: AsyncSession,
    barcodes: list[str],
    org_id: UUID,
) -> dict[str, UUID]:
    """
    Batch query. Returns { barcode: sku_id } for all barcodes found.
    Only returns SKUs belonging to the given org_id and is_active=True.
    Barcodes not found in the org will simply be absent from the result dict,
    causing the service layer to emit a RowError.
    """
    IF NOT barcodes:
        RETURN {}

    stmt = (
        select(SKU.barcode, SKU.id)
        .where(SKU.barcode.in_(barcodes))
        .where(SKU.org_id == org_id)
        .where(SKU.is_active == True)
    )
    result = await db.execute(stmt)
    RETURN { row.barcode: row.id FOR row IN result.all() }
```

---

### repository.py — lookup_platforms_by_name

```
FUNCTION lookup_platforms_by_name(
    db: AsyncSession,
    names: list[str],
) -> dict[str, UUID]:
    """
    Batch query. Returns { lower(name): platform_id }.
    Platforms are a global shared catalog — no org_id filter.
    Matching is case-insensitive to handle "wildberries" vs "Wildberries".
    """
    IF NOT names:
        RETURN {}

    lower_names = [n.lower() FOR n IN names]

    stmt = (
        select(Platform.id, Platform.name)
        .where(func.lower(Platform.name).in_(lower_names))
    )
    result = await db.execute(stmt)
    RETURN { row.name.lower(): row.id FOR row IN result.all() }
```

---

## 4. Edge Cases and Error Handling

### CSV encoding

```
FUNCTION detect_encoding(raw_bytes: bytes) -> str:
    # Try explicit UTF-8-sig first (common Excel CSV export)
    TRY:
        raw_bytes.decode("utf-8-sig")
        RETURN "utf-8-sig"
    EXCEPT UnicodeDecodeError:
        PASS

    # Use chardet for probabilistic detection
    detection = chardet.detect(raw_bytes[:4096])  # sample first 4 KB
    IF detection["confidence"] >= 0.70:
        RETURN detection["encoding"]

    # Default fallback: cp1251 covers Cyrillic Windows exports
    RETURN "cp1251"
```

### Duplicate rows within the same CSV

The CSV may contain duplicate `(sku_barcode, platform_name, week_number, year)`
combinations within a single file (e.g., two rows for the same SKU × week).
The UPSERT at the DB level handles this safely — last writer wins within the
batch. No special de-duplication is required in the service layer.

### Maximum row limit

```
IF len(list(reader)) > 10_000:
    RAISE ServiceValidationError(
        "CSV exceeds 10,000 row limit. Split the file and re-upload."
    )
```

This check is performed after header validation but before row-level parsing.
Prevents memory exhaustion on large files that passed the 5 MB size check.

### Partial import semantics

If 95 out of 100 rows are valid, 95 rows are imported and 5 errors are returned.
The response HTTP status is always **200** when the file is syntactically valid
and at least one row was processed — even if all rows failed validation.
HTTP 422 is reserved for file-level failures (wrong type, empty, bad header).

### Concurrent uploads for the same org

Two concurrent uploads for the same `(sku_id, platform_id, week_number, year)`
are handled safely by the PostgreSQL `ON CONFLICT DO UPDATE` constraint.
The last-committed transaction wins. No application-level locking is required.

### Platform name fuzzy matching boundary

The current implementation uses exact case-insensitive matching
(`lower(name) = lower(:name)`). Fuzzy matching (e.g., Levenshtein distance)
is explicitly out of scope for this sprint. Unknown platform names are returned
as `RowError` with a human-readable message suggesting the user check spelling.

### DELETE — not found vs forbidden

`delete_plan` returns `False` in both cases (plan not found, or plan belongs
to a different org). The router maps `False` to HTTP 404 in both cases.
This avoids leaking the existence of other tenants' plan IDs.

```
# router.py
deleted = await service.delete_distribution_plan(db, plan_id, current_user.org_id)
IF NOT deleted:
    RAISE HTTP 404 "PLAN_NOT_FOUND"
RETURN HTTP 204 No Content
```
