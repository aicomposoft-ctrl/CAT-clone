"""
Business logic for the catalog domain: Brand, SKU, Platform, SKUPlatform, bulk upload.

Rules:
  - All methods raise ValueError (→ 409) or LookupError (→ 404) for domain errors.
  - Router translates these to HTTPException. Service never imports from fastapi.
  - Multi-tenant: every write/read is scoped to org_id.
"""

import csv
import io
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import SKU, Brand, Platform, SKUPlatform
from app.catalog.repository import (
    BrandRepository,
    PlatformRepository,
    SKUPlatformRepository,
    SKURepository,
)
from app.catalog.schemas import (
    BrandCreateRequest,
    BrandListResponse,
    BrandResponse,
    BulkUploadResponse,
    BulkUploadRowError,
    PlatformListResponse,
    PlatformResponse,
    SKUCreateRequest,
    SKUListFilters,
    SKUListResponse,
    SKUPlatformCreateRequest,
    SKUPlatformResponse,
    SKUResponse,
    SKUUpdateRequest,
)

logger = logging.getLogger(__name__)

_MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB
_MAX_CSV_ROWS = 1000
_BULK_CHUNK_SIZE = 100


# ---------------------------------------------------------------------------
# Brand
# ---------------------------------------------------------------------------

async def create_brand(
    db: AsyncSession, org_id: UUID, data: BrandCreateRequest
) -> BrandResponse:
    existing = await BrandRepository.get_by_name(db, org_id, data.name)
    if existing is not None:
        raise ValueError("BRAND_NAME_DUPLICATE")

    brand = await BrandRepository.create(db, org_id, data.name, data.type)
    return BrandResponse.model_validate(brand)


async def list_brands(db: AsyncSession, org_id: UUID) -> BrandListResponse:
    brands = await BrandRepository.list_by_org(db, org_id)
    return BrandListResponse(
        items=[BrandResponse.model_validate(b) for b in brands],
        total=len(brands),
    )


# ---------------------------------------------------------------------------
# SKU
# ---------------------------------------------------------------------------

async def create_sku(
    db: AsyncSession, org_id: UUID, data: SKUCreateRequest
) -> SKUResponse:
    if data.article is not None:
        existing = await SKURepository.get_by_org_article(db, org_id, data.article)
        if existing is not None:
            raise ValueError("SKU_ARTICLE_DUPLICATE")

    brand = await BrandRepository.get_by_id(db, data.brand_id, org_id)
    if brand is None:
        raise LookupError("BRAND_NOT_FOUND")

    fields = data.model_dump(exclude={"brand_id"})
    sku = await SKURepository.create(db, org_id, data.brand_id, **fields)
    await db.refresh(sku, ["brand"])
    return SKUResponse.model_validate(sku)


async def list_skus(
    db: AsyncSession,
    org_id: UUID,
    filters: SKUListFilters,
    limit: int,
    cursor: Optional[str],
) -> SKUListResponse:
    items, total, next_cursor = await SKURepository.list(
        db,
        org_id=org_id,
        include_inactive=filters.include_inactive,
        brand_id=filters.brand_id,
        limit=limit,
        cursor=cursor,
    )
    # eager-load brand for each sku
    for sku in items:
        await db.refresh(sku, ["brand"])

    return SKUListResponse(
        items=[SKUResponse.model_validate(s) for s in items],
        total=total,
        next_cursor=next_cursor,
    )


async def update_sku(
    db: AsyncSession, org_id: UUID, sku_id: UUID, data: SKUUpdateRequest
) -> SKUResponse:
    sku = await SKURepository.get_by_id_and_org(db, sku_id, org_id)
    if sku is None:
        raise LookupError("SKU_NOT_FOUND")

    updates = data.model_dump(exclude_none=True)

    if "article" in updates and updates["article"] != sku.article:
        existing = await SKURepository.get_by_org_article(db, org_id, updates["article"])
        if existing is not None:
            raise ValueError("SKU_ARTICLE_DUPLICATE")

    if "brand_id" in updates:
        brand = await BrandRepository.get_by_id(db, updates["brand_id"], org_id)
        if brand is None:
            raise LookupError("BRAND_NOT_FOUND")

    sku = await SKURepository.update(db, sku, **updates)
    await db.refresh(sku, ["brand"])
    return SKUResponse.model_validate(sku)


async def delete_sku(db: AsyncSession, org_id: UUID, sku_id: UUID) -> SKUResponse:
    sku = await SKURepository.get_by_id_and_org(db, sku_id, org_id)
    if sku is None:
        raise LookupError("SKU_NOT_FOUND")

    sku = await SKURepository.update(db, sku, is_active=False)
    await db.refresh(sku, ["brand"])
    return SKUResponse.model_validate(sku)


# ---------------------------------------------------------------------------
# Bulk upload
# ---------------------------------------------------------------------------

def _detect_delimiter(text: str) -> str:
    first_line = text.split("\n")[0]
    return ";" if first_line.count(";") > first_line.count(",") else ","


def _validate_row(row: dict, row_num: int) -> list[BulkUploadRowError]:
    errors: list[BulkUploadRowError] = []
    name = row.get("name", "").strip()
    if not name:
        errors.append(BulkUploadRowError(row=row_num, field="name", reason="REQUIRED_FIELD"))
    elif len(name) > 500:
        errors.append(BulkUploadRowError(row=row_num, field="name", reason="MAX_LENGTH_EXCEEDED"))
    article = row.get("article", "").strip()
    if article and len(article) > 100:
        errors.append(BulkUploadRowError(row=row_num, field="article", reason="MAX_LENGTH_EXCEEDED"))
    return errors


async def bulk_upload_skus(
    db: AsyncSession,
    org_id: UUID,
    content: bytes,
    filename: str,
    content_type: str,
) -> BulkUploadResponse:
    # File size check
    if len(content) > _MAX_FILE_BYTES:
        raise ValueError("FILE_TOO_LARGE")

    # File type check
    if content_type not in ("text/csv", "application/octet-stream", "text/plain"):
        if not filename.lower().endswith(".csv"):
            raise ValueError("INVALID_FILE_TYPE")

    text = content.decode("utf-8-sig")
    delimiter = _detect_delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)

    headers = {(h.strip().lower()) for h in (reader.fieldnames or [])}
    if "name" not in headers:
        raise ValueError("MISSING_REQUIRED_COLUMN: name")

    rows = list(reader)
    if len(rows) > _MAX_CSV_ROWS:
        raise ValueError("CSV_TOO_LARGE")

    errors: list[BulkUploadRowError] = []
    valid_rows: list[dict] = []
    brand_cache: dict[str, UUID] = {}

    for i, row in enumerate(rows, start=2):
        # Normalize keys
        norm = {k.strip().lower(): (v or "").strip() for k, v in row.items()}

        row_errors = _validate_row(norm, i)
        if row_errors:
            errors.extend(row_errors)
            continue

        brand_name = norm.get("brand_name", "").strip()
        if not brand_name:
            brand_name = "Default"

        if brand_name not in brand_cache:
            brand = await BrandRepository.get_or_create_by_name(db, org_id, brand_name)
            brand_cache[brand_name] = brand.id
        brand_id = brand_cache[brand_name]

        article = norm.get("article", "").strip() or None
        if article is not None:
            existing = await SKURepository.get_by_org_article(db, org_id, article)
            if existing:
                errors.append(BulkUploadRowError(row=i, field="article", reason="SKU_ARTICLE_DUPLICATE"))
                continue

        valid_rows.append({
            "org_id": org_id,
            "brand_id": brand_id,
            "article": article,
            "rpc": norm.get("rpc") or None,
            "name": norm["name"],
            "barcode": norm.get("barcode") or None,
            "category": norm.get("category") or None,
            "sub_category": norm.get("sub_category") or None,
            "_row_num": i,
        })

    # Batch insert in chunks
    imported = 0
    for chunk_start in range(0, len(valid_rows), _BULK_CHUNK_SIZE):
        chunk = valid_rows[chunk_start: chunk_start + _BULK_CHUNK_SIZE]
        db_rows = [{k: v for k, v in r.items() if k != "_row_num"} for r in chunk]
        try:
            await SKURepository.bulk_create(db, db_rows)
            imported += len(chunk)
        except IntegrityError:
            await db.rollback()
            for row in chunk:
                single = [{k: v for k, v in row.items() if k != "_row_num"}]
                try:
                    await SKURepository.bulk_create(db, single)
                    imported += 1
                except IntegrityError:
                    await db.rollback()
                    errors.append(BulkUploadRowError(
                        row=row["_row_num"], field="article", reason="SKU_ARTICLE_DUPLICATE"
                    ))

    return BulkUploadResponse(
        imported=imported,
        failed=len(errors),
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Platform
# ---------------------------------------------------------------------------

async def list_platforms(db: AsyncSession) -> PlatformListResponse:
    platforms = await PlatformRepository.list_active(db)
    return PlatformListResponse(
        items=[PlatformResponse.model_validate(p) for p in platforms],
    )


# ---------------------------------------------------------------------------
# SKUPlatform
# ---------------------------------------------------------------------------

async def create_sku_platform(
    db: AsyncSession, org_id: UUID, data: SKUPlatformCreateRequest
) -> SKUPlatformResponse:
    sku = await SKURepository.get_by_id_and_org(db, data.sku_id, org_id)
    if sku is None:
        raise LookupError("SKU_NOT_FOUND")

    platform = await PlatformRepository.get_by_id(db, data.platform_id)
    if platform is None or not platform.is_active:
        raise LookupError("PLATFORM_NOT_FOUND")

    existing = await SKUPlatformRepository.get_by_sku_platform(db, data.sku_id, data.platform_id)
    if existing is not None:
        raise ValueError("SKU_PLATFORM_DUPLICATE")

    sp = await SKUPlatformRepository.create(
        db, data.sku_id, data.platform_id, data.external_id, data.url
    )
    return SKUPlatformResponse.model_validate(sp)


async def delete_sku_platform(
    db: AsyncSession, org_id: UUID, sp_id: UUID
) -> None:
    sp = await SKUPlatformRepository.get_by_id_and_org(db, sp_id, org_id)
    if sp is None:
        raise LookupError("SKU_PLATFORM_NOT_FOUND")
    await SKUPlatformRepository.delete(db, sp)
