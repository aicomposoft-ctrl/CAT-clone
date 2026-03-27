from __future__ import annotations

"""
Database query layer for the catalog domain.

SECURITY: Every method that operates on tenant-scoped data MUST accept org_id
and filter by it. Never return data belonging to another org.

ISOLATION MAP:
  BrandRepository    — always filter WHERE org_id = org_id
  SKURepository      — always filter WHERE org_id = org_id
  PlatformRepository — global catalog, no org_id filter
  SKUPlatformRepository — no org_id column; must JOIN through skus.org_id
"""

import base64
import json
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import delete, func, insert, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Brand, Platform, SKU, SKUPlatform


# ---------------------------------------------------------------------------
# Brand
# ---------------------------------------------------------------------------

class BrandRepository:

    @staticmethod
    async def get_by_id(db: AsyncSession, brand_id: UUID, org_id: UUID) -> Optional[Brand]:
        result = await db.execute(
            select(Brand).where(Brand.id == brand_id, Brand.org_id == org_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_name(db: AsyncSession, org_id: UUID, name: str) -> Optional[Brand]:
        result = await db.execute(
            select(Brand).where(Brand.org_id == org_id, Brand.name == name)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_or_create_by_name(
        db: AsyncSession, org_id: UUID, name: str, brand_type: str = "client"
    ) -> Brand:
        """
        Get existing brand or create one.
        Race-safe: catches IntegrityError on concurrent inserts and falls back to SELECT.
        """
        from sqlalchemy.exc import IntegrityError

        existing = await BrandRepository.get_by_name(db, org_id, name)
        if existing is not None:
            return existing
        try:
            brand = Brand(org_id=org_id, name=name, type=brand_type)
            db.add(brand)
            await db.flush()
            return brand
        except IntegrityError:
            await db.rollback()
            brand = await BrandRepository.get_by_name(db, org_id, name)
            return brand  # type: ignore[return-value]

    @staticmethod
    async def create(db: AsyncSession, org_id: UUID, name: str, brand_type: str) -> Brand:
        brand = Brand(org_id=org_id, name=name, type=brand_type)
        db.add(brand)
        await db.commit()
        await db.refresh(brand)
        return brand

    @staticmethod
    async def list_by_org(db: AsyncSession, org_id: UUID) -> list[Brand]:
        result = await db.execute(
            select(Brand).where(Brand.org_id == org_id).order_by(Brand.name)
        )
        return list(result.scalars().all())

    @staticmethod
    async def count_by_org(db: AsyncSession, org_id: UUID) -> int:
        result = await db.execute(
            select(func.count()).where(Brand.org_id == org_id)
        )
        return result.scalar_one()


# ---------------------------------------------------------------------------
# SKU
# ---------------------------------------------------------------------------

def _encode_cursor(created_at: datetime, sku_id: UUID) -> str:
    payload = json.dumps({"t": created_at.isoformat(), "id": str(sku_id)})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    dt = datetime.fromisoformat(payload["t"])
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt, UUID(payload["id"])


class SKURepository:

    @staticmethod
    async def get_by_id_and_org(
        db: AsyncSession, sku_id: UUID, org_id: UUID
    ) -> Optional[SKU]:
        result = await db.execute(
            select(SKU).where(SKU.id == sku_id, SKU.org_id == org_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_org_article(
        db: AsyncSession, org_id: UUID, article: str
    ) -> Optional[SKU]:
        result = await db.execute(
            select(SKU).where(SKU.org_id == org_id, SKU.article == article)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, org_id: UUID, brand_id: UUID, **fields) -> SKU:
        sku = SKU(org_id=org_id, brand_id=brand_id, **fields)
        db.add(sku)
        await db.commit()
        await db.refresh(sku)
        return sku

    @staticmethod
    async def update(db: AsyncSession, sku: SKU, **fields) -> SKU:
        for key, value in fields.items():
            setattr(sku, key, value)
        sku.updated_at = datetime.now(tz=timezone.utc)
        await db.commit()
        await db.refresh(sku)
        return sku

    @staticmethod
    async def list(
        db: AsyncSession,
        org_id: UUID,
        include_inactive: bool = False,
        brand_id: Optional[UUID] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> tuple[list[SKU], int, Optional[str]]:
        """
        Cursor-based paginated list. Returns (items, total, next_cursor).

        Cursor encodes (created_at, id) as base64 JSON.
        Uses SQLAlchemy tuple_() for correct row-value comparison at page boundaries.
        """
        base_q = select(SKU).where(SKU.org_id == org_id)
        count_q = select(func.count()).select_from(SKU).where(SKU.org_id == org_id)

        if not include_inactive:
            base_q = base_q.where(SKU.is_active.is_(True))
            count_q = count_q.where(SKU.is_active.is_(True))

        if brand_id is not None:
            base_q = base_q.where(SKU.brand_id == brand_id)
            count_q = count_q.where(SKU.brand_id == brand_id)

        total = (await db.execute(count_q)).scalar_one()

        if cursor is not None:
            cursor_dt, cursor_id = _decode_cursor(cursor)
            base_q = base_q.where(
                tuple_(SKU.created_at, SKU.id) < tuple_(cursor_dt, cursor_id)
            )

        base_q = base_q.order_by(SKU.created_at.desc(), SKU.id.desc()).limit(limit + 1)
        rows = list((await db.execute(base_q)).scalars().all())

        next_cursor: Optional[str] = None
        if len(rows) > limit:
            next_cursor = _encode_cursor(rows[limit - 1].created_at, rows[limit - 1].id)
            rows = rows[:limit]

        return rows, total, next_cursor

    @staticmethod
    async def bulk_create(db: AsyncSession, rows: list[dict]) -> int:
        """
        Batch insert using Core INSERT for performance.
        Returns the number of rows inserted.
        Caller is responsible for catching IntegrityError.
        """
        if not rows:
            return 0
        await db.execute(insert(SKU), rows)
        await db.flush()
        return len(rows)


# ---------------------------------------------------------------------------
# Platform
# ---------------------------------------------------------------------------

class PlatformRepository:

    @staticmethod
    async def get_by_id(db: AsyncSession, platform_id: UUID) -> Optional[Platform]:
        result = await db.execute(
            select(Platform).where(Platform.id == platform_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_active(db: AsyncSession) -> list[Platform]:
        result = await db.execute(
            select(Platform).where(Platform.is_active.is_(True)).order_by(Platform.name)
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# SKUPlatform
# ---------------------------------------------------------------------------

class SKUPlatformRepository:

    @staticmethod
    async def get_by_id_and_org(
        db: AsyncSession, sp_id: UUID, org_id: UUID
    ) -> Optional[SKUPlatform]:
        """
        Look up sku_platform by id, verifying org ownership via JOIN through skus.
        Returns None if id not found OR belongs to a different org.
        """
        result = await db.execute(
            select(SKUPlatform)
            .join(SKU, SKUPlatform.sku_id == SKU.id)
            .where(SKUPlatform.id == sp_id, SKU.org_id == org_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_sku_platform(
        db: AsyncSession, sku_id: UUID, platform_id: UUID
    ) -> Optional[SKUPlatform]:
        result = await db.execute(
            select(SKUPlatform).where(
                SKUPlatform.sku_id == sku_id,
                SKUPlatform.platform_id == platform_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        db: AsyncSession,
        sku_id: UUID,
        platform_id: UUID,
        external_id: Optional[str],
        url: Optional[str],
    ) -> SKUPlatform:
        sp = SKUPlatform(
            sku_id=sku_id,
            platform_id=platform_id,
            external_id=external_id,
            url=url,
        )
        db.add(sp)
        await db.commit()
        await db.refresh(sp)
        return sp

    @staticmethod
    async def delete(db: AsyncSession, sp: SKUPlatform) -> None:
        await db.execute(delete(SKUPlatform).where(SKUPlatform.id == sp.id))
        await db.commit()
