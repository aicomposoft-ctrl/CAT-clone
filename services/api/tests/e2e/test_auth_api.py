"""
E2E tests for auth endpoints — full HTTP stack via FastAPI TestClient.
Tests run against an in-memory SQLite (async) or real Postgres depending on
TEST_DATABASE_URL env var.

Covers BDD scenarios from Specification.md §3.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.models import Base as AuthBase
from app.core.database import Base
from app.core.deps import get_db
from app.main import app

# In-memory SQLite for tests (no Postgres needed)
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
    """Per-test session with rollback — no data leaks between tests."""
    async with engine.connect() as conn:
        await conn.begin()
        session_factory = async_sessionmaker(
            bind=conn, expire_on_commit=False, class_=AsyncSession
        )
        async with session_factory() as session:
            yield session
        await conn.rollback()


@pytest_asyncio.fixture
async def client(db_session):
    """AsyncClient with get_db overridden to use test session."""

    async def _get_test_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_test_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


# ── helpers ────────────────────────────────────────────────────────────────────

async def create_test_user(
    db_session: AsyncSession,
    email: str = "manager@test.ru",
    password: str = "TestPass1!",
    role: str = "manager",
) -> dict:
    """Insert org + user directly into DB for test setup."""
    from uuid import uuid4
    from app.auth.models import Organization, User
    from app.core.security import hash_password

    org = Organization(
        id=uuid4(), name="Test Org", slug=f"test-{uuid4().hex[:8]}", plan="basic"
    )
    db_session.add(org)
    await db_session.flush()

    user = User(
        id=uuid4(),
        org_id=org.id,
        email=email,
        password_hash=hash_password(password),
        role=role,
    )
    db_session.add(user)
    await db_session.flush()
    return {"user": user, "org": org, "email": email, "password": password}


# ── BDD: Successful login ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_success(client, db_session):
    data = await create_test_user(db_session)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": data["email"], "password": data["password"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "Bearer"
    assert body["user"]["role"] == "manager"
    assert body["expires_in"] == 900


# ── BDD: Invalid credentials ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_wrong_password(client, db_session):
    await create_test_user(db_session)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "manager@test.ru", "password": "WrongPass1!"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_login_nonexistent_email_same_error(client, db_session):
    """Login with unknown email returns same 401 as wrong password (anti-enumeration)."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@fake.com", "password": "anything"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "INVALID_CREDENTIALS"


# ── BDD: Invalid email format (422) ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_invalid_email_format(client, db_session):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "not-an-email", "password": "SomePass1!"},
    )
    assert resp.status_code == 422


# ── BDD: Account lockout ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_lockout_after_5_attempts(client, db_session):
    await create_test_user(db_session, email="lockout@test.ru")
    for i in range(4):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "lockout@test.ru", "password": "WrongPass1!"},
        )
        assert resp.status_code == 401, f"Attempt {i+1} should return 401"

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "lockout@test.ru", "password": "WrongPass1!"},
    )
    assert resp.status_code == 423
    body = resp.json()
    assert body["detail"] == "ACCOUNT_LOCKED"
    assert "X-Lockout-Until" in resp.headers


# ── BDD: Token refresh ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_refresh_token_success(client, db_session):
    data = await create_test_user(db_session, email="refresh@test.ru")
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": data["email"], "password": data["password"]},
    )
    refresh_token = login_resp.json()["refresh_token"]
    old_access = login_resp.json()["access_token"]

    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert resp.status_code == 200
    new_access = resp.json()["access_token"]
    assert new_access != old_access


@pytest.mark.asyncio
async def test_refresh_token_multi_use(client, db_session):
    """Refresh token is NOT rotated — can be used multiple times until expiry."""
    data = await create_test_user(db_session, email="multirefresh@test.ru")
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": data["email"], "password": data["password"]},
    )
    refresh_token = login_resp.json()["refresh_token"]

    resp1 = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )
    resp2 = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert resp1.status_code == 200
    assert resp2.status_code == 200


@pytest.mark.asyncio
async def test_refresh_invalid_token(client, db_session):
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": "invalid.token.here"}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "INVALID_REFRESH_TOKEN"


# ── BDD: Logout ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(client, db_session):
    data = await create_test_user(db_session, email="logout@test.ru")
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": data["email"], "password": data["password"]},
    )
    access_token = login_resp.json()["access_token"]
    refresh_token = login_resp.json()["refresh_token"]

    logout_resp = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"refresh_token": refresh_token},
    )
    assert logout_resp.status_code == 200
    assert logout_resp.json()["message"] == "Logged out successfully"

    # Refresh token must now be rejected
    refresh_resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert refresh_resp.status_code == 401


# ── BDD: GET /me ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_me_authenticated(client, db_session):
    data = await create_test_user(db_session, email="me@test.ru")
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": data["email"], "password": data["password"]},
    )
    access_token = login_resp.json()["access_token"]

    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "me@test.ru"
    assert body["role"] == "manager"
    assert "org_id" in body


@pytest.mark.asyncio
async def test_get_me_unauthenticated(client, db_session):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


# ── BDD: RBAC enforcement ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rbac_viewer_role_in_token(client, db_session):
    """Viewer token is returned correctly — RBAC enforcement tested at endpoint level."""
    data = await create_test_user(
        db_session, email="viewer@test.ru", role="viewer"
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": data["email"], "password": data["password"]},
    )
    assert login_resp.status_code == 200
    assert login_resp.json()["user"]["role"] == "viewer"


# ── BDD: Email case normalization ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_email_case_insensitive(client, db_session):
    await create_test_user(db_session, email="casesensitive@test.ru")
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "CASESENSITIVE@TEST.RU", "password": "TestPass1!"},
    )
    assert resp.status_code == 200
