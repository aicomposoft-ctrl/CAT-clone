"""
E2E tests for GET /api/v1/dashboard/summary.

Verifies:
  - Authentication required (401 without token)
  - Org-level isolation (summary reflects only the requesting org's data)
  - Empty-state for new org (no content scores, no alerts) returns valid response
"""

import uuid
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.models import Organization, User
from app.catalog.models import Brand, Platform, SKU, SKUPlatform
from app.content.models import ContentScore
from app.core.database import Base
from app.core.deps import get_db
from app.core.security import create_access_token, hash_password
from app.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

ORG_A_ID = uuid.uuid4()
ORG_B_ID = uuid.uuid4()


@pytest_asyncio.fixture(scope="module")
async def engine():
    e = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield e
    await e.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    async with engine.connect() as conn:
        await conn.begin()
        factory = async_sessionmaker(bind=conn, expire_on_commit=False, class_=AsyncSession)
        async with factory() as session:
            yield session
        await conn.rollback()


@pytest_asyncio.fixture
async def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def _seed_two_orgs(db: AsyncSession):
    """Seed two orgs with content scores so we can verify isolation."""
    for org_id in (ORG_A_ID, ORG_B_ID):
        org = Organization(id=org_id, name=f"Org {org_id}", slug=str(org_id))
        db.add(org)

    await db.flush()

    platform = Platform(id=uuid.uuid4(), name="TestPlatform", type="marketplace")
    db.add(platform)
    await db.flush()

    users = {}
    for org_id in (ORG_A_ID, ORG_B_ID):
        user = User(
            id=uuid.uuid4(),
            org_id=org_id,
            email=f"dash-user-{org_id}@test.com",
            password_hash=hash_password("pass"),
            role="manager",
        )
        brand = Brand(id=uuid.uuid4(), org_id=org_id, name=f"Brand {org_id}", type="client")
        sku = SKU(
            id=uuid.uuid4(),
            org_id=org_id,
            brand_id=brand.id,
            name=f"SKU {org_id}",
            article=f"ART-{org_id}",
        )
        sp = SKUPlatform(
            id=uuid.uuid4(),
            sku_id=sku.id,
            platform_id=platform.id,
            is_monitored=True,
        )
        score = ContentScore(
            id=uuid.uuid4(),
            sku_platform_id=sp.id,
            scored_at=date.today(),
            content_total=55.0,
            image_score=50.0,
            description_score=60.0,
            composition_score=55.0,
            created_at=datetime.now(timezone.utc),
        )
        db.add_all([user, brand, sku, sp, score])
        users[str(org_id)] = user

    await db.flush()
    return users


async def _seed_empty_org(db: AsyncSession):
    """Seed a single org with no SKUs or scores — tests empty-state response."""
    org_id = uuid.uuid4()
    org = Organization(id=org_id, name="Empty Org", slug=str(org_id))
    user = User(
        id=uuid.uuid4(),
        org_id=org_id,
        email=f"empty-{org_id}@test.com",
        password_hash=hash_password("pass"),
        role="viewer",
    )
    db.add_all([org, user])
    await db.flush()
    return user


def _token(user: User) -> str:
    return create_access_token(str(user.id), str(user.org_id))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDashboardAuth:
    async def test_no_token_returns_401(self, client):
        resp = await client.get("/api/v1/dashboard/summary")
        assert resp.status_code == 401


class TestDashboardSummaryIsolation:
    async def test_summary_returns_200_for_authenticated_user(self, client, db_session):
        users = await _seed_two_orgs(db_session)
        token_a = _token(users[str(ORG_A_ID)])

        resp = await client.get(
            "/api/v1/dashboard/summary",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 200

    async def test_summary_contains_required_fields(self, client, db_session):
        users = await _seed_two_orgs(db_session)
        token_a = _token(users[str(ORG_A_ID)])

        resp = await client.get(
            "/api/v1/dashboard/summary",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        body = resp.json()

        assert "avg_content_score" in body
        assert "active_alerts_count" in body
        assert "distribution_coverage_pct" in body
        assert "monitored_sku_count" in body
        assert "red_zone" in body
        assert "recent_alerts" in body
        assert isinstance(body["red_zone"], list)
        assert isinstance(body["recent_alerts"], list)

    async def test_org_a_monitored_sku_count_excludes_org_b(self, client, db_session):
        users = await _seed_two_orgs(db_session)

        token_a = _token(users[str(ORG_A_ID)])
        resp_a = await client.get(
            "/api/v1/dashboard/summary",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        body_a = resp_a.json()

        token_b = _token(users[str(ORG_B_ID)])
        resp_b = await client.get(
            "/api/v1/dashboard/summary",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        body_b = resp_b.json()

        # Each org has exactly 1 monitored SKU. Counts must be equal (1) and not doubled (2).
        assert body_a["monitored_sku_count"] == body_b["monitored_sku_count"], (
            "Both orgs seeded with 1 monitored SKU each — counts should be equal"
        )
        assert body_a["monitored_sku_count"] <= 1, (
            "Cross-tenant leakage: org_a sees org_b's monitored SKUs"
        )

    async def test_empty_org_returns_valid_zero_state(self, client, db_session):
        user = await _seed_empty_org(db_session)
        token = _token(user)

        resp = await client.get(
            "/api/v1/dashboard/summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()

        # Empty org must return nulls/zeros, not errors
        assert body["avg_content_score"] is None or isinstance(body["avg_content_score"], float)
        assert body["active_alerts_count"] == 0
        assert body["monitored_sku_count"] == 0
        assert body["red_zone"] == []
        assert body["recent_alerts"] == []
