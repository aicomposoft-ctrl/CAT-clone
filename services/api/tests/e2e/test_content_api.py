"""
E2E tests for GET /api/v1/content/scores and /drilldown.

Verifies:
  - Authentication required (401 without token)
  - Org-level isolation (org_b cannot see org_a data)
  - Drilldown 404 for unknown sku_platform_id
  - Drilldown 404 when sku_platform belongs to a different org
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


async def _seed(db: AsyncSession):
    """Create two orgs, each with one SKU and one content_score row."""
    for org_id in (ORG_A_ID, ORG_B_ID):
        org = Organization(id=org_id, name=f"Org {org_id}", slug=str(org_id))
        db.add(org)

    await db.flush()

    platform = Platform(id=uuid.uuid4(), name="TestPlatform", type="marketplace")
    db.add(platform)
    await db.flush()

    items = {}
    for org_id in (ORG_A_ID, ORG_B_ID):
        user = User(
            id=uuid.uuid4(),
            org_id=org_id,
            email=f"user-{org_id}@test.com",
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
            content_total=42.5,
            image_score=40.0,
            description_score=45.0,
            composition_score=43.0,
            created_at=datetime.now(timezone.utc),
        )
        db.add_all([user, brand, sku, sp, score])
        items[str(org_id)] = {"user": user, "sp": sp, "score": score}

    await db.flush()
    return items


def _token(user: User) -> str:
    return create_access_token(str(user.id), str(user.org_id))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestContentScoresAuth:
    async def test_no_token_returns_401(self, client):
        resp = await client.get("/api/v1/content/scores")
        assert resp.status_code == 401

    async def test_drilldown_no_token_returns_401(self, client):
        resp = await client.get(f"/api/v1/content/scores/{uuid.uuid4()}/drilldown")
        assert resp.status_code == 401


class TestContentScoresCrossTenantIsolation:
    async def test_org_a_cannot_see_org_b_scores(self, client, db_session):
        items = await _seed(db_session)

        # Login as org_a user
        token_a = _token(items[str(ORG_A_ID)]["user"])
        headers = {"Authorization": f"Bearer {token_a}"}

        resp = await client.get("/api/v1/content/scores", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        # All returned sku_ids must belong to org_a's SKU
        returned_sp_ids = {item["sku_platform_id"] for item in data["items"]}
        org_b_sp_id = str(items[str(ORG_B_ID)]["sp"].id)

        assert org_b_sp_id not in returned_sp_ids, (
            "Cross-tenant data leakage: org_b sku_platform_id visible to org_a"
        )

    async def test_drilldown_returns_404_for_other_org_sku(self, client, db_session):
        items = await _seed(db_session)

        # org_a user tries to drill down into org_b's sku_platform_id
        token_a = _token(items[str(ORG_A_ID)]["user"])
        org_b_sp_id = items[str(ORG_B_ID)]["sp"].id

        resp = await client.get(
            f"/api/v1/content/scores/{org_b_sp_id}/drilldown",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 404, (
            "Should return 404 (not 200) when sku_platform belongs to a different org"
        )

    async def test_drilldown_returns_404_for_unknown_id(self, client, db_session):
        items = await _seed(db_session)
        token_a = _token(items[str(ORG_A_ID)]["user"])

        resp = await client.get(
            f"/api/v1/content/scores/{uuid.uuid4()}/drilldown",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 404
