"""
Unit tests for stock repository — focuses on list_plans JOIN query behaviour.

Uses SQLite in-memory via aiosqlite. The upsert_plans function is NOT tested
here (requires PostgreSQL dialect). See test_stock_api.py for E2E coverage.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.models import Organization
from app.catalog.models import Brand, Platform, SKU
from app.core.database import Base
from app.stock.models import DistributionPlan
from app.stock import repository

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="module")
async def engine():
    e = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield e
    await e.dispose()


@pytest_asyncio.fixture
async def db(engine):
    async with engine.connect() as conn:
        await conn.begin()
        factory = async_sessionmaker(bind=conn, expire_on_commit=False, class_=AsyncSession)
        async with factory() as session:
            yield session
        await conn.rollback()


async def _create_org(db: AsyncSession) -> Organization:
    """Create a fresh org with a unique slug."""
    suffix = uuid.uuid4().hex[:10]
    org = Organization(
        id=uuid.uuid4(), name=f"Org-{suffix}", slug=f"org-{suffix}", plan="pro"
    )
    db.add(org)
    await db.flush()
    return org


async def _seed_plan(
    db: AsyncSession,
    org: Organization,
    barcode: str,
    platform_name: str,
    week: int,
    year: int,
    plan_qty: int = 50,
) -> tuple[DistributionPlan, SKU, Platform]:
    """
    Seed one plan row (brand → sku → platform → plan) under an existing org.
    Returns (plan, sku, platform).
    """
    suffix = uuid.uuid4().hex[:8]
    brand = Brand(id=uuid.uuid4(), org_id=org.id, name=f"Brand-{suffix}", type="client")
    db.add(brand)
    await db.flush()

    sku = SKU(
        id=uuid.uuid4(),
        org_id=org.id,
        brand_id=brand.id,
        name=f"SKU-{barcode}",
        barcode=barcode,
    )
    db.add(sku)
    await db.flush()

    platform = Platform(id=uuid.uuid4(), name=f"{platform_name}-{suffix}")
    db.add(platform)
    await db.flush()

    plan = DistributionPlan(
        id=uuid.uuid4(),
        sku_id=sku.id,
        platform_id=platform.id,
        group_name="Test Group",
        plan_tt_count=plan_qty,
        week_number=week,
        year=year,
    )
    db.add(plan)
    await db.flush()
    return plan, sku, platform


@pytest.mark.asyncio
class TestListPlansWithJoin:
    async def test_returns_platform_name_and_sku_barcode(self, db: AsyncSession):
        """JOIN must surface platform_name and sku_barcode in result dicts."""
        org = await _create_org(db)
        plan, sku, platform = await _seed_plan(db, org, "REPO-BC-001", "WB-Repo", week=10, year=2026)
        items, total = await repository.list_plans(
            db, org_id=org.id, platform_id=None, week_number=None, year=None,
            limit=50, offset=0,
        )
        assert total == 1
        row = items[0]
        assert row["platform_name"] == platform.name
        assert row["sku_barcode"] == "REPO-BC-001"
        assert row["plan_tt_count"] == 50

    async def test_platform_filter_narrows_results(self, db: AsyncSession):
        """platform_id filter returns only plans for that platform."""
        org = await _create_org(db)
        plan_a, _, platform_a = await _seed_plan(db, org, "REPO-PA-001", "Platform-Alpha", week=11, year=2026)
        plan_b, _, platform_b = await _seed_plan(db, org, "REPO-PB-001", "Platform-Beta", week=11, year=2026)

        items, _ = await repository.list_plans(
            db, org_id=org.id, platform_id=platform_a.id,
            week_number=None, year=None, limit=50, offset=0,
        )
        ids = [r["id"] for r in items]
        assert plan_a.id in ids
        assert plan_b.id not in ids

    async def test_week_filter_narrows_results(self, db: AsyncSession):
        """week_number filter returns only plans for that week."""
        org = await _create_org(db)
        plan_w5, _, _ = await _seed_plan(db, org, "REPO-W5-001", "WB-W5", week=5, year=2026)
        plan_w6, _, _ = await _seed_plan(db, org, "REPO-W6-001", "WB-W6", week=6, year=2026)

        items, _ = await repository.list_plans(
            db, org_id=org.id, platform_id=None,
            week_number=5, year=2026, limit=50, offset=0,
        )
        ids = [r["id"] for r in items]
        assert plan_w5.id in ids
        assert plan_w6.id not in ids

    async def test_pagination_offset_correct(self, db: AsyncSession):
        """page 2 with size=1 returns the second row, not the first."""
        org = await _create_org(db)
        plan_1, _, _ = await _seed_plan(db, org, "REPO-PG-001", "WB-PG1", week=20, year=2025)
        plan_2, _, _ = await _seed_plan(db, org, "REPO-PG-002", "WB-PG2", week=21, year=2025)

        page1, total = await repository.list_plans(
            db, org_id=org.id, platform_id=None,
            week_number=None, year=2025, limit=1, offset=0,
        )
        assert total == 2
        assert len(page1) == 1

        page2, _ = await repository.list_plans(
            db, org_id=org.id, platform_id=None,
            week_number=None, year=2025, limit=1, offset=1,
        )
        assert len(page2) == 1
        assert page1[0]["id"] != page2[0]["id"]

    async def test_cross_tenant_isolation_via_join(self, db: AsyncSession):
        """Org B must not see Org A plans at repository level."""
        org_a = await _create_org(db)
        plan_a, _, _ = await _seed_plan(db, org_a, "REPO-ISO-001", "WB-Iso", week=30, year=2026)

        org_b = await _create_org(db)
        items_b, _ = await repository.list_plans(
            db, org_id=org_b.id, platform_id=None,
            week_number=None, year=None, limit=50, offset=0,
        )
        b_ids = {r["id"] for r in items_b}
        assert plan_a.id not in b_ids, (
            f"CROSS-TENANT LEAK: plan {plan_a.id} visible to Org B!"
        )

    async def test_sku_with_null_barcode_returns_none(self, db: AsyncSession):
        """SKU.barcode is nullable — result must have sku_barcode=None, not error."""
        org = await _create_org(db)
        suffix = uuid.uuid4().hex[:8]

        brand = Brand(id=uuid.uuid4(), org_id=org.id, name=f"Brand-nb-{suffix}", type="client")
        db.add(brand)
        await db.flush()

        sku = SKU(
            id=uuid.uuid4(), org_id=org.id, brand_id=brand.id,
            name="SKU no barcode", barcode=None,
        )
        db.add(sku)
        await db.flush()

        platform = Platform(id=uuid.uuid4(), name=f"Platform-nb-{suffix}")
        db.add(platform)
        await db.flush()

        plan = DistributionPlan(
            id=uuid.uuid4(), sku_id=sku.id, platform_id=platform.id,
            group_name="Group", plan_tt_count=10, week_number=1, year=2026,
        )
        db.add(plan)
        await db.flush()

        items, _ = await repository.list_plans(
            db, org_id=org.id, platform_id=None,
            week_number=None, year=None, limit=50, offset=0,
        )
        row = next((r for r in items if r["id"] == plan.id), None)
        assert row is not None
        assert row["sku_barcode"] is None
