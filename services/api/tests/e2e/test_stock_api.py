"""
E2E tests for stock distribution-plan endpoints.

The upsert_plans repository call uses PostgreSQL-specific syntax.
Upload endpoint tests mock service.upload_distribution_plan to avoid SQLite
incompatibility. GET and DELETE tests work directly with SQLite.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.models import Organization, User
from app.catalog.models import Brand, Platform, SKU
from app.core.database import Base
from app.core.deps import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.stock.models import DistributionPlan
from app.stock.schemas import DistributionPlanUploadResponse, RowError

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

ORG_A_ID = uuid.uuid4()
ORG_B_ID = uuid.uuid4()


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


@pytest_asyncio.fixture
async def org_a(db_session):
    org = Organization(id=ORG_A_ID, name="Org A", slug="org-a", plan="pro")
    db_session.add(org)
    await db_session.flush()
    return org


@pytest_asyncio.fixture
async def manager_user(db_session, org_a):
    user = User(
        id=uuid.uuid4(),
        org_id=org_a.id,
        email="manager@org-a.com",
        password_hash=hash_password("pass"),
        role="manager",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def viewer_user(db_session, org_a):
    user = User(
        id=uuid.uuid4(),
        org_id=org_a.id,
        email="viewer@org-a.com",
        password_hash=hash_password("pass"),
        role="viewer",
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _auth_headers(user: User) -> dict:
    token = create_access_token(user.id, user.org_id, user.role)
    return {"Authorization": f"Bearer {token}"}


# ──────────────────────────────────────────────────────────────────────────────
# POST /distribution-plan
# ──────────────────────────────────────────────────────────────────────────────

class TestUploadDistributionPlan:
    async def test_upload_returns_200_with_imported_count(self, client, manager_user):
        mock_result = DistributionPlanUploadResponse(imported=3, errors=[])
        with patch(
            "app.stock.service.upload_distribution_plan",
            new=AsyncMock(return_value=mock_result),
        ):
            csv_content = (
                "sku_barcode,platform_name,group_name,plan_tt_count,week_number,year\n"
                "111,WB,GroupA,100,12,2026\n"
            )
            response = await client.post(
                "/api/v1/stock/distribution-plan",
                files={"file": ("plan.csv", csv_content.encode(), "text/csv")},
                headers=_auth_headers(manager_user),
            )
        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 3
        assert data["errors"] == []

    async def test_upload_returns_partial_errors(self, client, manager_user):
        mock_result = DistributionPlanUploadResponse(
            imported=1,
            errors=[RowError(row=3, field="sku_barcode", message="SKU not found")],
        )
        with patch(
            "app.stock.service.upload_distribution_plan",
            new=AsyncMock(return_value=mock_result),
        ):
            csv_content = (
                "sku_barcode,platform_name,group_name,plan_tt_count,week_number,year\n"
                "111,WB,GroupA,100,12,2026\n"
                "UNKNOWN,WB,GroupA,50,12,2026\n"
            )
            response = await client.post(
                "/api/v1/stock/distribution-plan",
                files={"file": ("plan.csv", csv_content.encode(), "text/csv")},
                headers=_auth_headers(manager_user),
            )
        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 1
        assert len(data["errors"]) == 1

    async def test_upload_rejects_viewer_role(self, client, viewer_user):
        csv_content = (
            "sku_barcode,platform_name,group_name,plan_tt_count,week_number,year\n"
            "111,WB,GroupA,100,12,2026\n"
        )
        response = await client.post(
            "/api/v1/stock/distribution-plan",
            files={"file": ("plan.csv", csv_content.encode(), "text/csv")},
            headers=_auth_headers(viewer_user),
        )
        assert response.status_code == 403

    async def test_upload_rejects_wrong_content_type(self, client, manager_user):
        response = await client.post(
            "/api/v1/stock/distribution-plan",
            files={"file": ("plan.xlsx", b"PK...", "application/vnd.openxmlformats")},
            headers=_auth_headers(manager_user),
        )
        assert response.status_code == 422

    async def test_upload_rejects_empty_file(self, client, manager_user):
        response = await client.post(
            "/api/v1/stock/distribution-plan",
            files={"file": ("plan.csv", b"", "text/csv")},
            headers=_auth_headers(manager_user),
        )
        assert response.status_code == 422

    async def test_upload_requires_auth(self, client):
        csv_content = b"sku_barcode,platform_name,group_name,plan_tt_count,week_number,year\n"
        response = await client.post(
            "/api/v1/stock/distribution-plan",
            files={"file": ("plan.csv", csv_content, "text/csv")},
        )
        assert response.status_code == 401


# ──────────────────────────────────────────────────────────────────────────────
# GET /distribution-plan
# ──────────────────────────────────────────────────────────────────────────────

class TestListDistributionPlans:
    async def test_list_returns_empty_for_new_org(self, client, manager_user):
        response = await client.get(
            "/api/v1/stock/distribution-plan",
            headers=_auth_headers(manager_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_viewer_can_list(self, client, viewer_user):
        response = await client.get(
            "/api/v1/stock/distribution-plan",
            headers=_auth_headers(viewer_user),
        )
        assert response.status_code == 200

    async def test_list_requires_auth(self, client):
        response = await client.get("/api/v1/stock/distribution-plan")
        assert response.status_code == 401

    async def test_list_pagination_params_accepted(self, client, manager_user):
        response = await client.get(
            "/api/v1/stock/distribution-plan?page=2&size=10",
            headers=_auth_headers(manager_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 2
        assert data["size"] == 10


# ──────────────────────────────────────────────────────────────────────────────
# DELETE /distribution-plan/{id}
# ──────────────────────────────────────────────────────────────────────────────

class TestDeleteDistributionPlan:
    async def test_delete_nonexistent_plan_returns_404(self, client, manager_user):
        plan_id = uuid.uuid4()
        response = await client.delete(
            f"/api/v1/stock/distribution-plan/{plan_id}",
            headers=_auth_headers(manager_user),
        )
        assert response.status_code == 404

    async def test_viewer_cannot_delete(self, client, viewer_user):
        plan_id = uuid.uuid4()
        response = await client.delete(
            f"/api/v1/stock/distribution-plan/{plan_id}",
            headers=_auth_headers(viewer_user),
        )
        assert response.status_code == 403

    async def test_delete_requires_auth(self, client):
        plan_id = uuid.uuid4()
        response = await client.delete(f"/api/v1/stock/distribution-plan/{plan_id}")
        assert response.status_code == 401


# ──────────────────────────────────────────────────────────────────────────────
# Cross-tenant isolation
# ──────────────────────────────────────────────────────────────────────────────

class TestCrossTenantIsolation:
    async def test_list_plans_returns_only_own_org_data(self, client, db_session):
        """Org B cannot see Org A's distribution plans via GET listing."""
        from app.catalog.models import Brand, Platform, SKU
        from app.stock.models import DistributionPlan

        # Create Org A and Org B
        org_a = Organization(id=ORG_A_ID, name="Org A", slug="org-a-iso", plan="pro")
        org_b = Organization(id=ORG_B_ID, name="Org B", slug="org-b-iso", plan="pro")
        db_session.add_all([org_a, org_b])
        await db_session.flush()

        # Users for each org
        user_a = User(
            id=uuid.uuid4(),
            org_id=ORG_A_ID,
            email="user-a-iso@test.com",
            password_hash=hash_password("pass"),
            role="manager",
        )
        user_b = User(
            id=uuid.uuid4(),
            org_id=ORG_B_ID,
            email="user-b-iso@test.com",
            password_hash=hash_password("pass"),
            role="manager",
        )
        db_session.add_all([user_a, user_b])
        await db_session.flush()

        # Brand + SKU for Org A
        brand_a = Brand(id=uuid.uuid4(), org_id=ORG_A_ID, name="Brand A", type="client")
        db_session.add(brand_a)
        await db_session.flush()

        sku_a = SKU(
            id=uuid.uuid4(),
            org_id=ORG_A_ID,
            brand_id=brand_a.id,
            name="SKU A",
            barcode="ORG_A_BARCODE_01",
        )
        db_session.add(sku_a)
        await db_session.flush()

        # Platform (global)
        platform = Platform(id=uuid.uuid4(), name="TestPlatform-Iso")
        db_session.add(platform)
        await db_session.flush()

        # Distribution plan belonging to Org A
        plan_a = DistributionPlan(
            id=uuid.uuid4(),
            sku_id=sku_a.id,
            platform_id=platform.id,
            group_name="Group A",
            plan_tt_count=100,
            week_number=10,
            year=2026,
        )
        db_session.add(plan_a)
        await db_session.flush()

        # Org A user lists plans — should see plan_a
        resp_a = await client.get(
            "/api/v1/stock/distribution-plan",
            headers=_auth_headers(user_a),
        )
        assert resp_a.status_code == 200
        data_a = resp_a.json()
        assert data_a["total"] >= 1
        plan_ids_a = [item["id"] for item in data_a["items"]]
        assert str(plan_a.id) in plan_ids_a

        # Org B user lists plans — must NOT see plan_a
        resp_b = await client.get(
            "/api/v1/stock/distribution-plan",
            headers=_auth_headers(user_b),
        )
        assert resp_b.status_code == 200
        data_b = resp_b.json()
        plan_ids_b = [item["id"] for item in data_b["items"]]
        assert str(plan_a.id) not in plan_ids_b, (
            "CROSS-TENANT LEAK: Org B can see Org A's distribution plan!"
        )


# ──────────────────────────────────────────────────────────────────────────────
# File-level validation (no service mock — tests real service logic)
# ──────────────────────────────────────────────────────────────────────────────

class TestFileValidation:
    async def test_upload_rejects_missing_required_column(self, client, manager_user):
        """CSV missing 'year' column → 422 with informative message."""
        csv_content = (
            "sku_barcode,platform_name,group_name,plan_tt_count,week_number\n"
            "111,WB,GroupA,100,12\n"
        )
        response = await client.post(
            "/api/v1/stock/distribution-plan",
            files={"file": ("plan.csv", csv_content.encode(), "text/csv")},
            headers=_auth_headers(manager_user),
        )
        assert response.status_code == 422
        assert "Missing columns" in response.json()["detail"]

    async def test_upload_rejects_headers_only_csv(self, client, manager_user):
        """CSV with only the header row (no data) → 422."""
        csv_content = (
            "sku_barcode,platform_name,group_name,plan_tt_count,week_number,year\n"
        )
        response = await client.post(
            "/api/v1/stock/distribution-plan",
            files={"file": ("plan.csv", csv_content.encode(), "text/csv")},
            headers=_auth_headers(manager_user),
        )
        assert response.status_code == 422
        assert "no data rows" in response.json()["detail"].lower()

    async def test_upload_handles_header_with_trailing_spaces(self, client, manager_user):
        """CSV column names with trailing spaces must be normalised, not rejected."""
        from unittest.mock import AsyncMock, patch
        from app.stock.schemas import DistributionPlanUploadResponse

        mock_result = DistributionPlanUploadResponse(imported=0, errors=[])
        with patch(
            "app.stock.service.repository.lookup_skus_by_barcode",
            new=AsyncMock(return_value={}),
        ), patch(
            "app.stock.service.repository.lookup_platforms_by_name",
            new=AsyncMock(return_value={}),
        ):
            # Columns have trailing spaces
            csv_content = (
                " sku_barcode , platform_name , group_name , plan_tt_count , week_number , year \n"
                "111,WB,GroupA,100,12,2026\n"
            )
            response = await client.post(
                "/api/v1/stock/distribution-plan",
                files={"file": ("plan.csv", csv_content.encode(), "text/csv")},
                headers=_auth_headers(manager_user),
            )
        # Should not get 422 for "Missing columns" — header stripping must work
        assert response.status_code == 200
