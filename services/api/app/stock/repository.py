"""
Database access layer for the stock domain.

ALL queries against distribution_plans MUST join through skus.org_id.
The table has no org_id column — tenant isolation is enforced via this JOIN.
Never add a query that reads distribution_plans without verifying org ownership.
"""

import logging
import uuid
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Platform, SKU
from app.stock.models import DistributionPlan

logger = logging.getLogger(__name__)


async def lookup_skus_by_barcode(
    db: AsyncSession,
    barcodes: list[str],
    org_id: UUID,
) -> dict[str, UUID]:
    """
    Batch-resolve barcodes → sku_id for the given org.
    Only active SKUs are returned. Missing barcodes are absent from the result.
    """
    if not barcodes:
        return {}

    stmt = (
        select(SKU.barcode, SKU.id)
        .where(SKU.barcode.in_(barcodes))
        .where(SKU.org_id == org_id)
        .where(SKU.is_active.is_(True))
    )
    result = await db.execute(stmt)
    return {row.barcode: row.id for row in result.all()}


async def lookup_platforms_by_name(
    db: AsyncSession,
    names: list[str],
) -> dict[str, UUID]:
    """
    Batch-resolve platform names → platform_id (case-insensitive).
    Platforms are a global catalog — no org_id filter.
    Returns { lower(name): platform_id }.
    """
    if not names:
        return {}

    lower_names = [n.lower() for n in names]
    stmt = (
        select(Platform.id, Platform.name)
        .where(func.lower(Platform.name).in_(lower_names))
    )
    result = await db.execute(stmt)
    return {row.name.lower(): row.id for row in result.all()}


async def upsert_plans(
    db: AsyncSession,
    rows: list[dict],
) -> list[DistributionPlan]:
    """
    Batch INSERT … ON CONFLICT DO UPDATE for distribution_plans.
    sku_id values must be pre-validated (resolved via lookup_skus_by_barcode)
    to guarantee org ownership — never accept raw sku_id from the client.

    Requires PostgreSQL dialect (uses pg_insert for ON CONFLICT support).
    """
    if not rows:
        return []

    stmt = pg_insert(DistributionPlan).values(rows)
    upsert_stmt = stmt.on_conflict_do_update(
        index_elements=["sku_id", "platform_id", "week_number", "year"],
        set_={
            "plan_tt_count": stmt.excluded.plan_tt_count,
            "group_name": stmt.excluded.group_name,
        },
    ).returning(DistributionPlan)

    try:
        result = await db.execute(upsert_stmt)
        rows = list(result.scalars().all())
        await db.commit()
        return rows
    except SQLAlchemyError:
        await db.rollback()
        raise


async def list_plans(
    db: AsyncSession,
    org_id: UUID,
    platform_id: UUID | None,
    week_number: int | None,
    year: int | None,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    """
    Paginated listing of distribution plans for the given org.
    Tenant isolation enforced by JOIN to skus.org_id — mandatory, never remove.
    Returns (items as dicts, total_count). Dicts include platform_name and sku_barcode
    resolved via JOINs to avoid N+1 lookups in the service layer.
    """
    base_stmt = (
        select(
            DistributionPlan.id,
            DistributionPlan.sku_id,
            DistributionPlan.platform_id,
            Platform.name.label("platform_name"),
            SKU.barcode.label("sku_barcode"),
            DistributionPlan.group_name,
            DistributionPlan.plan_tt_count,
            DistributionPlan.week_number,
            DistributionPlan.year,
        )
        .join(SKU, SKU.id == DistributionPlan.sku_id)
        .join(Platform, Platform.id == DistributionPlan.platform_id)
        .where(SKU.org_id == org_id)
    )

    if platform_id is not None:
        base_stmt = base_stmt.where(DistributionPlan.platform_id == platform_id)
    if week_number is not None:
        base_stmt = base_stmt.where(DistributionPlan.week_number == week_number)
    if year is not None:
        base_stmt = base_stmt.where(DistributionPlan.year == year)

    # Build a lean count query — only SKU JOIN is needed for tenant isolation.
    # The Platform JOIN is not required for counting (only for selecting names).
    count_stmt = (
        select(func.count())
        .select_from(DistributionPlan)
        .join(SKU, SKU.id == DistributionPlan.sku_id)
        .where(SKU.org_id == org_id)
    )
    if platform_id is not None:
        count_stmt = count_stmt.where(DistributionPlan.platform_id == platform_id)
    if week_number is not None:
        count_stmt = count_stmt.where(DistributionPlan.week_number == week_number)
    if year is not None:
        count_stmt = count_stmt.where(DistributionPlan.year == year)
    total = (await db.execute(count_stmt)).scalar_one()

    data_query = (
        base_stmt
        .order_by(DistributionPlan.year.desc(), DistributionPlan.week_number.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(data_query)).mappings().all()
    return [dict(r) for r in rows], total


async def delete_plan(
    db: AsyncSession,
    plan_id: UUID,
    org_id: UUID,
) -> bool:
    """
    Delete a plan row only if its sku_id belongs to org_id.
    Returns True if deleted, False if not found or not owned (caller maps to 404).
    Returning False in both cases avoids leaking tenant plan IDs.
    """
    owned_sku_subq = select(SKU.id).where(SKU.org_id == org_id)

    stmt = (
        delete(DistributionPlan)
        .where(DistributionPlan.id == plan_id)
        .where(DistributionPlan.sku_id.in_(owned_sku_subq))
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount > 0
