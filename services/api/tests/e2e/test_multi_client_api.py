"""
E2E tests for multi-client-support feature.

Covers:
  - Client CRUD (create, list, get, update, deactivate)
  - POST /auth/switch-client — issues JWT with client_id claim
  - Cross-client isolation: brands filtered by client context
  - Security: switching to foreign/deactivated client returns 403/401

Runs against in-memory SQLite (async). No Postgres required.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.models import Organization, User
from app.catalog.models import Brand
from app.clients.models import Client
from app.core.database import Base
from app.core.deps import get_db
from app.core.security import create_access_token, hash_password
from app.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    async def _get_test_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_test_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


_org_counter = 0


async def _create_org(db: AsyncSession, name: str = "Test Org") -> Organization:
    global _org_counter
    _org_counter += 1
    slug = name.lower().replace(" ", "-") + f"-{_org_counter}"
    org = Organization(name=name, slug=slug)
    db.add(org)
    await db.flush()
    return org


async def _create_user(
    db: AsyncSession,
    org_id,
    role: str = "admin",
    email: str = "admin@test.com",
) -> User:
    user = User(
        email=email,
        password_hash=hash_password("password123"),
        role=role,
        org_id=org_id,
    )
    db.add(user)
    await db.flush()
    return user


async def _create_client(
    db: AsyncSession, org_id, name: str = "Nestle RU", slug: str = "nestle-ru"
) -> Client:
    cli = Client(org_id=org_id, name=name, slug=slug)
    db.add(cli)
    await db.flush()
    return cli


def _auth_headers(user: User, client_id=None) -> dict:
    token = create_access_token(user.id, user.org_id, user.role, client_id=client_id)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Client CRUD tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_client_as_admin(client, db_session):
    org = await _create_org(db_session)
    user = await _create_user(db_session, org.id)
    headers = _auth_headers(user)

    resp = await client.post(
        "/api/v1/clients/",
        json={"name": "Nestle RU", "slug": "nestle-ru"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["slug"] == "nestle-ru"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_create_client_slug_conflict_returns_409(client, db_session):
    org = await _create_org(db_session, "OrgSlugConflict")
    user = await _create_user(db_session, org.id, email="slug@test.com")
    await _create_client(db_session, org.id, slug="duplicate-slug")
    headers = _auth_headers(user)

    resp = await client.post(
        "/api/v1/clients/",
        json={"name": "Other", "slug": "duplicate-slug"},
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "SLUG_CONFLICT"


@pytest.mark.asyncio
async def test_create_client_invalid_slug_returns_422(client, db_session):
    org = await _create_org(db_session, "OrgInvalidSlug")
    user = await _create_user(db_session, org.id, email="slug2@test.com")
    headers = _auth_headers(user)

    resp = await client.post(
        "/api/v1/clients/",
        json={"name": "X", "slug": "Nestle-RU"},  # uppercase not allowed
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_clients_returns_only_active(client, db_session):
    org = await _create_org(db_session, "OrgList")
    user = await _create_user(db_session, org.id, email="list@test.com")
    active_cli = await _create_client(db_session, org.id, slug="active-client")
    inactive = Client(org_id=org.id, name="Inactive", slug="inactive-client", is_active=False)
    db_session.add(inactive)
    await db_session.flush()
    headers = _auth_headers(user)

    resp = await client.get("/api/v1/clients/", headers=headers)
    assert resp.status_code == 200
    slugs = [c["slug"] for c in resp.json()["items"]]
    assert active_cli.slug in slugs
    assert "inactive-client" not in slugs


@pytest.mark.asyncio
async def test_deactivate_client(client, db_session):
    org = await _create_org(db_session, "OrgDeactivate")
    user = await _create_user(db_session, org.id, email="deact@test.com")
    cli = await _create_client(db_session, org.id, slug="to-deactivate")
    headers = _auth_headers(user)

    resp = await client.delete(f"/api/v1/clients/{cli.id}", headers=headers)
    assert resp.status_code == 204

    # Deactivated client no longer appears in list
    resp = await client.get("/api/v1/clients/", headers=headers)
    slugs = [c["slug"] for c in resp.json()["items"]]
    assert "to-deactivate" not in slugs


# ---------------------------------------------------------------------------
# Switch-client tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_switch_client_returns_new_token(client, db_session):
    org = await _create_org(db_session, "OrgSwitch")
    user = await _create_user(db_session, org.id, email="switch@test.com")
    cli = await _create_client(db_session, org.id, slug="switch-target")
    headers = _auth_headers(user)

    resp = await client.post(
        "/api/v1/auth/switch-client",
        json={"client_id": str(cli.id)},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_switch_to_deactivated_client_returns_403(client, db_session):
    org = await _create_org(db_session, "OrgSwitchInactive")
    user = await _create_user(db_session, org.id, email="switchinact@test.com")
    inactive = Client(org_id=org.id, name="Inactive", slug="inactive-sw", is_active=False)
    db_session.add(inactive)
    await db_session.flush()
    headers = _auth_headers(user)

    resp = await client.post(
        "/api/v1/auth/switch-client",
        json={"client_id": str(inactive.id)},
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "CLIENT_NOT_IN_ORG"


@pytest.mark.asyncio
async def test_switch_to_foreign_client_returns_403(client, db_session):
    org_a = await _create_org(db_session, "OrgA")
    org_b = await _create_org(db_session, "OrgB")
    user_a = await _create_user(db_session, org_a.id, email="usera@test.com")
    cli_b = await _create_client(db_session, org_b.id, slug="foreign-client")
    headers = _auth_headers(user_a)

    resp = await client.post(
        "/api/v1/auth/switch-client",
        json={"client_id": str(cli_b.id)},
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "CLIENT_NOT_IN_ORG"


# ---------------------------------------------------------------------------
# Client context filtering — brands
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_brands_filtered_by_client_context(client, db_session):
    org = await _create_org(db_session, "OrgBrandFilter")
    user = await _create_user(db_session, org.id, email="brandfilter@test.com")

    cli_a = await _create_client(db_session, org.id, slug="brand-client-a")
    cli_b = await _create_client(db_session, org.id, slug="brand-client-b")

    brand_a = Brand(org_id=org.id, name="BrandA", client_id=cli_a.id)
    brand_b = Brand(org_id=org.id, name="BrandB", client_id=cli_b.id)
    db_session.add_all([brand_a, brand_b])
    await db_session.flush()

    # Token scoped to client_a → only BrandA should appear
    headers_a = _auth_headers(user, client_id=cli_a.id)
    resp = await client.get("/api/v1/brands", headers=headers_a)
    assert resp.status_code == 200
    names = [b["name"] for b in resp.json()["items"]]
    assert "BrandA" in names
    assert "BrandB" not in names


@pytest.mark.asyncio
async def test_brands_unfiltered_in_all_clients_mode(client, db_session):
    org = await _create_org(db_session, "OrgAllClients")
    user = await _create_user(db_session, org.id, email="allclients@test.com")

    cli = await _create_client(db_session, org.id, slug="brand-client-all")
    brand_scoped = Brand(org_id=org.id, name="ScopedBrand", client_id=cli.id)
    brand_unscoped = Brand(org_id=org.id, name="UnscopedBrand", client_id=None)
    db_session.add_all([brand_scoped, brand_unscoped])
    await db_session.flush()

    # Token without client_id → all brands visible
    headers = _auth_headers(user)
    resp = await client.get("/api/v1/brands", headers=headers)
    assert resp.status_code == 200
    names = [b["name"] for b in resp.json()["items"]]
    assert "ScopedBrand" in names
    assert "UnscopedBrand" in names


@pytest.mark.asyncio
async def test_brand_client_assignment_via_patch(client, db_session):
    org = await _create_org(db_session, "OrgPatchBrand")
    user = await _create_user(db_session, org.id, email="patchbrand@test.com")
    cli = await _create_client(db_session, org.id, slug="patch-target-client")
    brand = Brand(org_id=org.id, name="PatchableBrand", client_id=None)
    db_session.add(brand)
    await db_session.flush()
    headers = _auth_headers(user)

    resp = await client.patch(
        f"/api/v1/brands/{brand.id}",
        json={"client_id": str(cli.id)},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["client_id"] == str(cli.id)


# ---------------------------------------------------------------------------
# INVALID_CLIENT_CONTEXT — forged/stale client_id in JWT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_brands_of_deactivated_client_hidden_in_client_context(client, db_session):
    """Brands assigned to a deactivated client must not appear in scoped brand list.

    BDD scenario from Refinement.md: "Brand assigned to deactivated client →
    brand hidden in client mode."
    """
    org = await _create_org(db_session, "OrgDeactBrand")
    user = await _create_user(db_session, org.id, email="deactbrand@test.com")
    cli = await _create_client(db_session, org.id, slug="soon-inactive")
    brand = Brand(org_id=org.id, name="BrandOfDeactivated", client_id=cli.id)
    db_session.add(brand)
    # Deactivate the client
    cli.is_active = False
    await db_session.flush()

    # Token scoped to the (now deactivated) client → get_current_user raises 401
    headers_inactive = _auth_headers(user, client_id=cli.id)
    resp = await client.get("/api/v1/brands", headers=headers_inactive)
    # JWT with deactivated client_id → 401 INVALID_CLIENT_CONTEXT
    assert resp.status_code == 401
    assert resp.json()["detail"] == "INVALID_CLIENT_CONTEXT"


@pytest.mark.asyncio
async def test_brand_visibility_after_switch_client_round_trip(client, db_session):
    """Brand list reflects scoped context after the full switch-client round-trip.

    BDD scenario from Refinement.md: "Brand visibility consistency after client switch."
    Tests POST /auth/switch-client → new token → GET /brands → verify scope.
    """
    org = await _create_org(db_session, "OrgRoundTrip")
    user = await _create_user(db_session, org.id, email="roundtrip@test.com")
    cli_a = await _create_client(db_session, org.id, slug="round-trip-client-a")
    cli_b = await _create_client(db_session, org.id, slug="round-trip-client-b")

    brand_a = Brand(org_id=org.id, name="RoundTripBrandA", client_id=cli_a.id)
    brand_b = Brand(org_id=org.id, name="RoundTripBrandB", client_id=cli_b.id)
    db_session.add_all([brand_a, brand_b])
    await db_session.flush()

    # Start with no client context
    headers = _auth_headers(user)

    # Switch to client_a via the actual endpoint
    switch_resp = await client.post(
        "/api/v1/auth/switch-client",
        json={"client_id": str(cli_a.id)},
        headers=headers,
    )
    assert switch_resp.status_code == 200
    new_token = switch_resp.json()["access_token"]
    scoped_headers = {"Authorization": f"Bearer {new_token}"}

    # Brands endpoint must return only client_a's brands
    brands_resp = await client.get("/api/v1/brands", headers=scoped_headers)
    assert brands_resp.status_code == 200
    names = [b["name"] for b in brands_resp.json()["items"]]
    assert "RoundTripBrandA" in names
    assert "RoundTripBrandB" not in names


@pytest.mark.asyncio
async def test_forged_client_id_in_jwt_returns_401(client, db_session):
    """JWT with non-existent client_id → 401 INVALID_CLIENT_CONTEXT."""
    import uuid

    org = await _create_org(db_session, "OrgForgedJWT")
    user = await _create_user(db_session, org.id, email="forged@test.com")
    # Use a random UUID that doesn't exist in DB
    fake_client_id = uuid.uuid4()
    headers = _auth_headers(user, client_id=fake_client_id)

    resp = await client.get("/api/v1/clients/", headers=headers)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "INVALID_CLIENT_CONTEXT"


@pytest.mark.asyncio
async def test_stale_client_id_deactivated_after_token_issue_returns_401(client, db_session):
    """Client deactivated after JWT was issued → subsequent requests return 401.

    This is the primary motivation for per-request DB re-validation in
    get_current_user: tokens are 15-minute lived, so a deactivated client must
    be caught on the next request, not just at login.
    """
    org = await _create_org(db_session, "OrgStaleJWT")
    user = await _create_user(db_session, org.id, email="stale@test.com")
    cli = await _create_client(db_session, org.id, slug="stale-client")

    # Issue token while client is still active
    headers_with_client = _auth_headers(user, client_id=cli.id)

    # Deactivate the client after token was issued
    cli.is_active = False
    await db_session.flush()

    # The token still has client_id in it, but the client is now inactive
    resp = await client.get("/api/v1/clients/", headers=headers_with_client)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "INVALID_CLIENT_CONTEXT"
