"""
E2E tests for the api-public-endpoints feature.

Coverage:
  - POST /api/v1/api-keys  — create key (admin OK, viewer → 403)
  - GET  /api/v1/api-keys  — list keys (admin OK)
  - GET  /api/v1/public/skus — missing key → 401, bad key → 401
  - DELETE /api/v1/api-keys/{id} + public endpoint — revoked key → 401

All tests use an in-memory SQLite DB with per-test rollback (same pattern as
test_alerts_api.py and test_content_api.py).
"""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.models import Organization, User
from app.core.database import Base
from app.core.deps import get_db
from app.core.security import create_access_token, hash_password
from app.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

ORG_A_ID = uuid.uuid4()
ORG_B_ID = uuid.uuid4()


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
    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def org_a(db_session):
    org = Organization(id=ORG_A_ID, name="Org A", slug=f"org-a-pub-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()
    return org


@pytest_asyncio.fixture
async def admin_user(db_session, org_a):
    user = User(
        id=uuid.uuid4(),
        org_id=org_a.id,
        email=f"admin-pub-{uuid.uuid4().hex[:6]}@org-a.com",
        password_hash=hash_password("pass"),
        role="admin",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def viewer_user(db_session, org_a):
    user = User(
        id=uuid.uuid4(),
        org_id=org_a.id,
        email=f"viewer-pub-{uuid.uuid4().hex[:6]}@org-a.com",
        password_hash=hash_password("pass"),
        role="viewer",
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _auth(user: User) -> dict:
    """Return Authorization header dict for a user."""
    token = create_access_token(user.id, user.org_id, user.role)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Test: POST /api/v1/api-keys
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_api_key_as_admin(client, admin_user):
    """Admin can create an API key; response includes full key starting with 'cat_live_'."""
    resp = await client.post(
        "/api/v1/api-keys/",
        json={"name": "Integration Key"},
        headers=_auth(admin_user),
    )
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "key" in data, "Response must include 'key' field"
    assert data["key"].startswith("cat_live_"), (
        f"Key must start with 'cat_live_', got: {data['key'][:20]!r}"
    )
    assert "key_prefix" in data, "Response must include 'key_prefix' field"
    assert "id" in data, "Response must include 'id' field"


@pytest.mark.asyncio
async def test_create_api_key_as_viewer_fails(client, viewer_user):
    """Viewer role is not allowed to create API keys — must return 403."""
    resp = await client.post(
        "/api/v1/api-keys/",
        json={"name": "Should Fail"},
        headers=_auth(viewer_user),
    )
    assert resp.status_code == 403, (
        f"Expected 403 for viewer role, got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# Test: GET /api/v1/api-keys
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_api_keys_as_admin(client, admin_user):
    """Admin can list API keys; response is a list (may be empty or contain created keys)."""
    # Create one first so there's something to list
    await client.post(
        "/api/v1/api-keys/",
        json={"name": "Listed Key"},
        headers=_auth(admin_user),
    )

    resp = await client.get("/api/v1/api-keys/", headers=_auth(admin_user))
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "items" in data, "Response must contain 'items' list"
    assert isinstance(data["items"], list)
    assert "total" in data
    # The key we just created must appear (and must NOT include the raw key)
    for item in data["items"]:
        assert "key" not in item, "GET /api-keys must never return the raw key"
        assert "key_prefix" in item


# ---------------------------------------------------------------------------
# Test: GET /api/v1/public/skus — auth failures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_skus_missing_api_key(client):
    """Requests without X-API-Key header must return 401 MISSING_API_KEY."""
    resp = await client.get("/api/v1/public/skus")
    assert resp.status_code == 401, (
        f"Expected 401 for missing API key, got {resp.status_code}: {resp.text}"
    )
    assert resp.json()["detail"] == "MISSING_API_KEY", (
        f"Expected detail='MISSING_API_KEY', got: {resp.json()['detail']!r}"
    )


@pytest.mark.asyncio
async def test_public_skus_invalid_api_key(client):
    """Requests with a syntactically invalid API key must return 401 INVALID_API_KEY."""
    resp = await client.get(
        "/api/v1/public/skus",
        headers={"X-API-Key": "bad_key"},
    )
    assert resp.status_code == 401, (
        f"Expected 401 for invalid API key, got {resp.status_code}: {resp.text}"
    )
    assert resp.json()["detail"] == "INVALID_API_KEY", (
        f"Expected detail='INVALID_API_KEY', got: {resp.json()['detail']!r}"
    )


@pytest.mark.asyncio
async def test_public_skus_unknown_api_key(client):
    """A well-formed but unknown API key must return 401 INVALID_API_KEY."""
    # Generate a realistic-looking key that won't exist in the DB
    import hashlib
    import secrets
    raw = secrets.token_urlsafe(30)
    fake_key = f"cat_live_{raw}"

    resp = await client.get(
        "/api/v1/public/skus",
        headers={"X-API-Key": fake_key},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "INVALID_API_KEY"


# ---------------------------------------------------------------------------
# Test: revoke key → public endpoint returns 401 API_KEY_REVOKED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_api_key(client, admin_user):
    """
    Full revocation lifecycle:
      1. Create key
      2. Verify key works (GET /public/skus returns 200)
      3. Delete (revoke) key
      4. Verify revoked key returns 401 API_KEY_REVOKED
    """
    # Step 1: create key
    create_resp = await client.post(
        "/api/v1/api-keys/",
        json={"name": "To Be Revoked"},
        headers=_auth(admin_user),
    )
    assert create_resp.status_code == 201
    key_id = create_resp.json()["id"]
    full_key = create_resp.json()["key"]

    # Step 2: revoke key
    revoke_resp = await client.delete(
        f"/api/v1/api-keys/{key_id}",
        headers=_auth(admin_user),
    )
    assert revoke_resp.status_code == 204, (
        f"Expected 204 on revoke, got {revoke_resp.status_code}: {revoke_resp.text}"
    )

    # Step 3: revoked key must be rejected
    after_resp = await client.get(
        "/api/v1/public/skus",
        headers={"X-API-Key": full_key},
    )
    assert after_resp.status_code == 401, (
        f"Expected 401 after revocation, got {after_resp.status_code}: {after_resp.text}"
    )
    assert after_resp.json()["detail"] == "API_KEY_REVOKED", (
        f"Expected detail='API_KEY_REVOKED', got: {after_resp.json()['detail']!r}"
    )
