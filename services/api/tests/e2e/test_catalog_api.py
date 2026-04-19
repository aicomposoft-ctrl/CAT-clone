"""
E2E tests for catalog endpoints — full HTTP stack via FastAPI AsyncClient.

Covers BDD scenarios from Specification.md:
  US-S01: Single SKU Creation
  US-S02: SKU Listing and Filtering
  US-S03: SKU Update and Soft Delete
  US-S04: Bulk CSV Upload
  US-S05: Brand Management
  US-S06: Platform Catalog and SKU-Platform Linking
"""

import io
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.models import Organization, User
from app.catalog.models import Brand, Platform, SKU
from app.core.database import Base
from app.core.deps import get_db
from app.core.security import hash_password, create_access_token
from app.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="session")
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
    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _make_org(db: AsyncSession, slug: str | None = None) -> Organization:
    org = Organization(
        id=uuid.uuid4(),
        name="Test Org",
        slug=slug or f"org-{uuid.uuid4().hex[:8]}",
        plan="basic",
    )
    db.add(org)
    await db.flush()
    return org


async def _make_user(
    db: AsyncSession,
    org_id: uuid.UUID,
    role: str = "manager",
    email: str | None = None,
) -> User:
    user = User(
        id=uuid.uuid4(),
        org_id=org_id,
        email=email or f"u-{uuid.uuid4().hex[:6]}@test.ru",
        password_hash=hash_password("TestPass1!"),
        role=role,
    )
    db.add(user)
    await db.flush()
    return user


def _token(user: User) -> dict:
    token = create_access_token(user.id, user.org_id, user.role)
    return {"Authorization": f"Bearer {token}"}


async def _make_brand(
    db: AsyncSession, org_id: uuid.UUID, name: str = "TestBrand", brand_type: str = "client"
) -> Brand:
    brand = Brand(id=uuid.uuid4(), org_id=org_id, name=name, type=brand_type)
    db.add(brand)
    await db.flush()
    return brand


async def _make_platform(db: AsyncSession, name: str = "Wildberries") -> Platform:
    platform = Platform(
        id=uuid.uuid4(),
        name=name,
        type="marketplace",
        schedule_cron="0 2 * * *",
        is_active=True,
    )
    db.add(platform)
    await db.flush()
    return platform


async def _make_sku(
    db: AsyncSession,
    org_id: uuid.UUID,
    brand_id: uuid.UUID,
    name: str = "Test SKU",
    article: str | None = None,
) -> SKU:
    sku = SKU(
        id=uuid.uuid4(),
        org_id=org_id,
        brand_id=brand_id,
        name=name,
        article=article,
        is_active=True,
    )
    db.add(sku)
    await db.flush()
    return sku


# ---------------------------------------------------------------------------
# US-S05: Brand Management
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_brand_manager_201(client, db_session):
    org = await _make_org(db_session)
    user = await _make_user(db_session, org.id)

    resp = await client.post("/api/v1/brands", json={"name": "ИндиЛайт", "type": "client"}, headers=_token(user))
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "ИндиЛайт"
    assert data["type"] == "client"
    assert data["org_id"] == str(org.id)


@pytest.mark.asyncio
async def test_create_brand_viewer_403(client, db_session):
    org = await _make_org(db_session)
    viewer = await _make_user(db_session, org.id, role="viewer")

    resp = await client.post("/api/v1/brands", json={"name": "X", "type": "client"}, headers=_token(viewer))
    assert resp.status_code == 403
    assert resp.json()["detail"] == "INSUFFICIENT_PERMISSIONS"


@pytest.mark.asyncio
async def test_create_brand_duplicate_409(client, db_session):
    org = await _make_org(db_session)
    user = await _make_user(db_session, org.id)
    await _make_brand(db_session, org.id, name="DupBrand")

    resp = await client.post("/api/v1/brands", json={"name": "DupBrand", "type": "client"}, headers=_token(user))
    assert resp.status_code == 409
    assert resp.json()["detail"] == "BRAND_NAME_DUPLICATE"


@pytest.mark.asyncio
async def test_list_brands_org_isolation(client, db_session):
    org_a = await _make_org(db_session)
    org_b = await _make_org(db_session)
    user_a = await _make_user(db_session, org_a.id)

    await _make_brand(db_session, org_a.id, "BrandA1")
    await _make_brand(db_session, org_a.id, "BrandA2")
    await _make_brand(db_session, org_b.id, "BrandB1")

    resp = await client.get("/api/v1/brands", headers=_token(user_a))
    assert resp.status_code == 200
    items = resp.json()["items"]
    names = [i["name"] for i in items]
    assert "BrandA1" in names
    assert "BrandA2" in names
    assert "BrandB1" not in names


# ---------------------------------------------------------------------------
# US-S01: Single SKU Creation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_sku_201(client, db_session):
    org = await _make_org(db_session)
    user = await _make_user(db_session, org.id)
    brand = await _make_brand(db_session, org.id)

    payload = {"brand_id": str(brand.id), "name": "Индейка Индилайт", "article": "3927"}
    resp = await client.post("/api/v1/skus", json=payload, headers=_token(user))
    assert resp.status_code == 201
    data = resp.json()
    assert data["article"] == "3927"
    assert data["is_active"] is True
    assert data["org_id"] == str(org.id)


@pytest.mark.asyncio
async def test_create_sku_viewer_403(client, db_session):
    org = await _make_org(db_session)
    viewer = await _make_user(db_session, org.id, role="viewer")
    brand = await _make_brand(db_session, org.id)

    resp = await client.post("/api/v1/skus", json={"brand_id": str(brand.id), "name": "X"}, headers=_token(viewer))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_sku_duplicate_article_409(client, db_session):
    org = await _make_org(db_session)
    user = await _make_user(db_session, org.id)
    brand = await _make_brand(db_session, org.id)
    await _make_sku(db_session, org.id, brand.id, article="DUP-001")

    resp = await client.post(
        "/api/v1/skus",
        json={"brand_id": str(brand.id), "name": "Another", "article": "DUP-001"},
        headers=_token(user),
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "SKU_ARTICLE_DUPLICATE"


@pytest.mark.asyncio
async def test_create_sku_cross_org_article_allowed(client, db_session):
    org_a = await _make_org(db_session)
    org_b = await _make_org(db_session)
    user_a = await _make_user(db_session, org_a.id)
    brand_a = await _make_brand(db_session, org_a.id)
    brand_b = await _make_brand(db_session, org_b.id)

    await _make_sku(db_session, org_b.id, brand_b.id, article="CROSS-001")

    resp = await client.post(
        "/api/v1/skus",
        json={"brand_id": str(brand_a.id), "name": "OrgA SKU", "article": "CROSS-001"},
        headers=_token(user_a),
    )
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# US-S02: SKU Listing and Filtering
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_skus_cross_tenant_isolation(client, db_session):
    org_a = await _make_org(db_session)
    org_b = await _make_org(db_session)
    user_a = await _make_user(db_session, org_a.id)
    brand_a = await _make_brand(db_session, org_a.id)
    brand_b = await _make_brand(db_session, org_b.id)

    await _make_sku(db_session, org_a.id, brand_a.id, name="OrgA-SKU")
    await _make_sku(db_session, org_b.id, brand_b.id, name="OrgB-SKU")

    resp = await client.get("/api/v1/skus", headers=_token(user_a))
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()["items"]]
    assert "OrgA-SKU" in names
    assert "OrgB-SKU" not in names


@pytest.mark.asyncio
async def test_list_skus_excludes_inactive_by_default(client, db_session):
    org = await _make_org(db_session)
    user = await _make_user(db_session, org.id)
    brand = await _make_brand(db_session, org.id)

    active = await _make_sku(db_session, org.id, brand.id, name="Active")
    inactive = await _make_sku(db_session, org.id, brand.id, name="Inactive")
    inactive.is_active = False
    await db_session.flush()

    resp = await client.get("/api/v1/skus", headers=_token(user))
    names = [s["name"] for s in resp.json()["items"]]
    assert "Active" in names
    assert "Inactive" not in names

    resp2 = await client.get("/api/v1/skus?include_inactive=true", headers=_token(user))
    names2 = [s["name"] for s in resp2.json()["items"]]
    assert "Inactive" in names2


@pytest.mark.asyncio
async def test_get_sku_by_id(client, db_session):
    org = await _make_org(db_session)
    user = await _make_user(db_session, org.id)
    brand = await _make_brand(db_session, org.id)
    sku = await _make_sku(db_session, org.id, brand.id, name="Detail Me")
    sku.reference_description = "Ref desc"
    sku.reference_composition = "Ref comp"
    await db_session.flush()

    resp = await client.get(f"/api/v1/skus/{sku.id}", headers=_token(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(sku.id)
    assert body["name"] == "Detail Me"
    assert body["reference_description"] == "Ref desc"
    assert body["reference_composition"] == "Ref comp"


@pytest.mark.asyncio
async def test_get_sku_other_org_404(client, db_session):
    org_a = await _make_org(db_session)
    org_b = await _make_org(db_session)
    user_a = await _make_user(db_session, org_a.id)
    brand_b = await _make_brand(db_session, org_b.id)
    sku_b = await _make_sku(db_session, org_b.id, brand_b.id)

    resp = await client.get(f"/api/v1/skus/{sku_b.id}", headers=_token(user_a))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# US-S03: SKU Update and Soft Delete
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_sku_name(client, db_session):
    org = await _make_org(db_session)
    user = await _make_user(db_session, org.id)
    brand = await _make_brand(db_session, org.id)
    sku = await _make_sku(db_session, org.id, brand.id, name="Old Name")

    resp = await client.patch(f"/api/v1/skus/{sku.id}", json={"name": "New Name"}, headers=_token(user))
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"
    assert resp.json()["id"] == str(sku.id)


@pytest.mark.asyncio
async def test_delete_sku_soft(client, db_session):
    org = await _make_org(db_session)
    user = await _make_user(db_session, org.id)
    brand = await _make_brand(db_session, org.id)
    sku = await _make_sku(db_session, org.id, brand.id)

    resp = await client.delete(f"/api/v1/skus/{sku.id}", headers=_token(user))
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False
    assert resp.json()["id"] == str(sku.id)


@pytest.mark.asyncio
async def test_update_sku_cross_org_404(client, db_session):
    org_a = await _make_org(db_session)
    org_b = await _make_org(db_session)
    user_a = await _make_user(db_session, org_a.id)
    brand_b = await _make_brand(db_session, org_b.id)
    sku_b = await _make_sku(db_session, org_b.id, brand_b.id)

    resp = await client.patch(f"/api/v1/skus/{sku_b.id}", json={"name": "Hacked"}, headers=_token(user_a))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_viewer_cannot_update_sku(client, db_session):
    org = await _make_org(db_session)
    viewer = await _make_user(db_session, org.id, role="viewer")
    brand = await _make_brand(db_session, org.id)
    sku = await _make_sku(db_session, org.id, brand.id)

    resp = await client.patch(f"/api/v1/skus/{sku.id}", json={"name": "X"}, headers=_token(viewer))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# US-S04: Bulk CSV Upload
# ---------------------------------------------------------------------------

def _csv_file(content: str) -> dict:
    return {"file": ("skus.csv", io.BytesIO(content.encode()), "text/csv")}


@pytest.mark.asyncio
async def test_bulk_upload_all_valid(client, db_session):
    org = await _make_org(db_session)
    user = await _make_user(db_session, org.id)

    csv_content = "brand_name,article,name,barcode,category\n"
    for i in range(5):
        csv_content += f"BulkBrand,ART-{i},SKU Name {i},BC{i},Category\n"

    resp = await client.post(
        "/api/v1/skus/bulk-upload",
        files=_csv_file(csv_content),
        headers=_token(user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 5
    assert data["failed"] == 0


@pytest.mark.asyncio
async def test_bulk_upload_mixed_returns_207(client, db_session):
    org = await _make_org(db_session)
    user = await _make_user(db_session, org.id)

    csv_content = "brand_name,article,name\n"
    csv_content += "TestBrand,ART-OK,Valid SKU\n"  # row 2: valid
    csv_content += "TestBrand,ART-BAD,\n"           # row 3: missing name

    resp = await client.post(
        "/api/v1/skus/bulk-upload",
        files=_csv_file(csv_content),
        headers=_token(user),
    )
    assert resp.status_code == 207
    data = resp.json()
    assert data["imported"] == 1
    assert data["failed"] == 1
    assert data["errors"][0]["field"] == "name"
    assert data["errors"][0]["reason"] == "REQUIRED_FIELD"


@pytest.mark.asyncio
async def test_bulk_upload_too_many_rows_422(client, db_session):
    org = await _make_org(db_session)
    user = await _make_user(db_session, org.id)

    csv_content = "brand_name,name\n"
    for i in range(1001):
        csv_content += f"Brand,SKU {i}\n"

    resp = await client.post(
        "/api/v1/skus/bulk-upload",
        files=_csv_file(csv_content),
        headers=_token(user),
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "CSV_TOO_LARGE"


@pytest.mark.asyncio
async def test_bulk_upload_duplicate_article_reported(client, db_session):
    org = await _make_org(db_session)
    user = await _make_user(db_session, org.id)
    brand = await _make_brand(db_session, org.id, "ExistingBrand")
    await _make_sku(db_session, org.id, brand.id, article="EXIST-001")

    csv_content = "brand_name,article,name\n"
    csv_content += "ExistingBrand,EXIST-001,Duplicate\n"
    csv_content += "ExistingBrand,NEW-001,New SKU\n"

    resp = await client.post(
        "/api/v1/skus/bulk-upload",
        files=_csv_file(csv_content),
        headers=_token(user),
    )
    data = resp.json()
    assert data["imported"] == 1
    assert data["failed"] == 1
    assert data["errors"][0]["reason"] == "SKU_ARTICLE_DUPLICATE"


@pytest.mark.asyncio
async def test_bulk_upload_viewer_403(client, db_session):
    org = await _make_org(db_session)
    viewer = await _make_user(db_session, org.id, role="viewer")

    resp = await client.post(
        "/api/v1/skus/bulk-upload",
        files=_csv_file("brand_name,name\nBrand,SKU\n"),
        headers=_token(viewer),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# US-S06: Platform catalog + SKU-Platform linking
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_platforms_shared(client, db_session):
    org = await _make_org(db_session)
    user = await _make_user(db_session, org.id)
    await _make_platform(db_session, name=f"WB-{uuid.uuid4().hex[:4]}")

    resp = await client.get("/api/v1/platforms", headers=_token(user))
    assert resp.status_code == 200
    assert isinstance(resp.json()["items"], list)


@pytest.mark.asyncio
async def test_create_sku_platform_201(client, db_session):
    org = await _make_org(db_session)
    user = await _make_user(db_session, org.id)
    brand = await _make_brand(db_session, org.id)
    sku = await _make_sku(db_session, org.id, brand.id)
    platform = await _make_platform(db_session, name=f"PF-{uuid.uuid4().hex[:4]}")

    resp = await client.post(
        "/api/v1/sku-platforms",
        json={"sku_id": str(sku.id), "platform_id": str(platform.id)},
        headers=_token(user),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["sku_id"] == str(sku.id)
    assert data["is_monitored"] is True


@pytest.mark.asyncio
async def test_create_sku_platform_duplicate_409(client, db_session):
    org = await _make_org(db_session)
    user = await _make_user(db_session, org.id)
    brand = await _make_brand(db_session, org.id)
    sku = await _make_sku(db_session, org.id, brand.id)
    platform = await _make_platform(db_session, name=f"PF-dup-{uuid.uuid4().hex[:4]}")

    payload = {"sku_id": str(sku.id), "platform_id": str(platform.id)}
    await client.post("/api/v1/sku-platforms", json=payload, headers=_token(user))
    resp = await client.post("/api/v1/sku-platforms", json=payload, headers=_token(user))
    assert resp.status_code == 409
    assert resp.json()["detail"] == "SKU_PLATFORM_DUPLICATE"


@pytest.mark.asyncio
async def test_create_sku_platform_cross_org_404(client, db_session):
    org_a = await _make_org(db_session)
    org_b = await _make_org(db_session)
    user_a = await _make_user(db_session, org_a.id)
    brand_b = await _make_brand(db_session, org_b.id)
    sku_b = await _make_sku(db_session, org_b.id, brand_b.id)
    platform = await _make_platform(db_session, name=f"PF-xorg-{uuid.uuid4().hex[:4]}")

    resp = await client.post(
        "/api/v1/sku-platforms",
        json={"sku_id": str(sku_b.id), "platform_id": str(platform.id)},
        headers=_token(user_a),
    )
    assert resp.status_code == 404
