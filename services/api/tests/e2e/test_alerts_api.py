"""
E2E and unit tests for the alerts domain.

Coverage:
  - CRUD endpoints: auth, RBAC, create/list/update/delete configs
  - Alert events listing
  - check_and_send_alerts() logic: content_drop, oos, dedup, email mock
  - Tenant isolation: events from org_b invisible to org_a
"""

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.alerts.models import AlertConfig, AlertEvent
from app.auth.models import Organization, User
from app.catalog.models import Brand, Platform, SKU, SKUPlatform
from app.core.database import Base
from app.core.deps import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.reports.models import ContentScoreRead

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
    org = Organization(id=ORG_A_ID, name="Org A", slug="org-a-alrt", plan="pro")
    db_session.add(org)
    await db_session.flush()
    return org


@pytest_asyncio.fixture
async def org_b(db_session):
    org = Organization(id=ORG_B_ID, name="Org B", slug="org-b-alrt", plan="basic")
    db_session.add(org)
    await db_session.flush()
    return org


@pytest_asyncio.fixture
async def admin_user(db_session, org_a):
    user = User(
        id=uuid.uuid4(),
        org_id=org_a.id,
        email="admin-alrt@org-a.com",
        password_hash=hash_password("pass"),
        role="admin",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def manager_user(db_session, org_a):
    user = User(
        id=uuid.uuid4(),
        org_id=org_a.id,
        email="manager-alrt@org-a.com",
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
        email="viewer-alrt@org-a.com",
        password_hash=hash_password("pass"),
        role="viewer",
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _auth(user: User) -> dict:
    token = create_access_token(user.id, user.org_id, user.role)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Config CRUD tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_config_requires_auth(client):
    resp = await client.post("/api/v1/alerts/configs", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_viewer_cannot_create_config(client, viewer_user):
    body = {
        "alert_type": "oos",
        "email_recipients": ["a@b.com"],
    }
    resp = await client.post(
        "/api/v1/alerts/configs", json=body, headers=_auth(viewer_user)
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_content_drop_config_success(client, manager_user):
    body = {
        "alert_type": "content_drop",
        "threshold": 70,
        "email_recipients": ["notify@example.com"],
    }
    resp = await client.post(
        "/api/v1/alerts/configs", json=body, headers=_auth(manager_user)
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["alert_type"] == "content_drop"
    assert data["threshold"] == "70.00"
    assert data["email_recipients"] == ["notify@example.com"]
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_create_oos_config_no_threshold_ok(client, manager_user):
    body = {
        "alert_type": "oos",
        "email_recipients": ["ops@example.com"],
    }
    resp = await client.post(
        "/api/v1/alerts/configs", json=body, headers=_auth(manager_user)
    )
    assert resp.status_code == 201
    assert resp.json()["alert_type"] == "oos"


@pytest.mark.asyncio
async def test_create_content_drop_without_threshold_fails(client, manager_user):
    body = {
        "alert_type": "content_drop",
        "email_recipients": ["a@b.com"],
    }
    resp = await client.post(
        "/api/v1/alerts/configs", json=body, headers=_auth(manager_user)
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_configs_returns_own_org_only(client, manager_user):
    # Create a config first
    body = {"alert_type": "oos", "email_recipients": ["x@y.com"]}
    await client.post("/api/v1/alerts/configs", json=body, headers=_auth(manager_user))

    resp = await client.get("/api/v1/alerts/configs", headers=_auth(manager_user))
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["items"], list)
    for item in data["items"]:
        assert item["org_id"] == str(manager_user.org_id)


@pytest.mark.asyncio
async def test_update_config_toggles_active(client, manager_user):
    body = {"alert_type": "oos", "email_recipients": ["x@y.com"]}
    create_resp = await client.post(
        "/api/v1/alerts/configs", json=body, headers=_auth(manager_user)
    )
    config_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/api/v1/alerts/configs/{config_id}",
        json={"is_active": False},
        headers=_auth(manager_user),
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_delete_config_success(client, manager_user):
    body = {"alert_type": "oos", "email_recipients": ["d@e.com"]}
    create_resp = await client.post(
        "/api/v1/alerts/configs", json=body, headers=_auth(manager_user)
    )
    config_id = create_resp.json()["id"]

    del_resp = await client.delete(
        f"/api/v1/alerts/configs/{config_id}", headers=_auth(manager_user)
    )
    assert del_resp.status_code == 204

    # Fetching the list should not contain the deleted config
    list_resp = await client.get("/api/v1/alerts/configs", headers=_auth(manager_user))
    ids = [item["id"] for item in list_resp.json()["items"]]
    assert config_id not in ids


@pytest.mark.asyncio
async def test_delete_config_cross_tenant_returns_404(client, manager_user, org_b, db_session):
    # Create a config for org_b directly in DB
    other_config = AlertConfig(
        id=uuid.uuid4(),
        org_id=org_b.id,
        alert_type="oos",
        email_recipients='["x@y.com"]',
        is_active=True,
        created_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(other_config)
    await db_session.flush()

    resp = await client.delete(
        f"/api/v1/alerts/configs/{other_config.id}",
        headers=_auth(manager_user),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Events listing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_events_requires_auth(client):
    resp = await client.get("/api/v1/alerts/events")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_events_empty_for_fresh_org(client, viewer_user):
    resp = await client.get("/api/v1/alerts/events", headers=_auth(viewer_user))
    assert resp.status_code == 200
    assert resp.json()["items"] == []


# ---------------------------------------------------------------------------
# POST /check (admin-only)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_requires_admin_role(client, manager_user):
    resp = await client.post("/api/v1/alerts/check", headers=_auth(manager_user))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_check_returns_zero_when_no_configs(client, admin_user):
    with patch(
        "app.alerts.router.service.check_and_send_alerts",
        new_callable=AsyncMock,
    ) as mock_check:
        from app.alerts.schemas import AlertCheckResponse
        mock_check.return_value = AlertCheckResponse(
            events_created=0, emails_sent=0, errors=[]
        )
        resp = await client.post("/api/v1/alerts/check", headers=_auth(admin_user))
    assert resp.status_code == 200
    assert resp.json()["events_created"] == 0


# ---------------------------------------------------------------------------
# Unit tests: check_and_send_alerts logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_content_drop_creates_event(db_session, org_a):
    """content_drop config fires when content_total < threshold."""
    from app.alerts import service as alert_service

    platform = Platform(id=uuid.uuid4(), name="WB-test", type="marketplace")
    db_session.add(platform)

    brand = Brand(id=uuid.uuid4(), org_id=org_a.id, name="Brand X")
    db_session.add(brand)

    sku = SKU(id=uuid.uuid4(), org_id=org_a.id, brand_id=brand.id, name="SKU X", article="X-001")
    db_session.add(sku)

    sp = SKUPlatform(id=uuid.uuid4(), sku_id=sku.id, platform_id=platform.id)
    db_session.add(sp)

    check_date = date(2026, 1, 20)
    score = ContentScoreRead(
        id=uuid.uuid4(),
        sku_platform_id=sp.id,
        scored_at=check_date,
        content_total=Decimal("45.00"),
        in_stock=True,
        created_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(score)

    config = AlertConfig(
        id=uuid.uuid4(),
        org_id=org_a.id,
        alert_type="content_drop",
        threshold=Decimal("70.00"),
        email_recipients='["alert@example.com"]',
        is_active=True,
        created_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(config)
    await db_session.flush()

    with patch("app.alerts.service.send_alert_email", new_callable=AsyncMock) as mock_send:
        result = await alert_service.check_and_send_alerts(
            db=db_session, org_id=org_a.id, org_name="Org A", check_date=check_date
        )

    assert result.events_created == 1
    assert result.emails_sent == 1
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_content_drop_skips_above_threshold(db_session, org_a):
    """No event when content_total is above threshold."""
    from app.alerts import service as alert_service

    platform = Platform(id=uuid.uuid4(), name="Ozon-test", type="marketplace")
    db_session.add(platform)

    brand = Brand(id=uuid.uuid4(), org_id=org_a.id, name="Brand Good")
    db_session.add(brand)

    sku = SKU(id=uuid.uuid4(), org_id=org_a.id, brand_id=brand.id, name="Good SKU", article="G-001")
    db_session.add(sku)

    sp = SKUPlatform(id=uuid.uuid4(), sku_id=sku.id, platform_id=platform.id)
    db_session.add(sp)

    check_date = date(2026, 1, 21)
    score = ContentScoreRead(
        id=uuid.uuid4(),
        sku_platform_id=sp.id,
        scored_at=check_date,
        content_total=Decimal("85.00"),  # above threshold
        created_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(score)

    config = AlertConfig(
        id=uuid.uuid4(),
        org_id=org_a.id,
        alert_type="content_drop",
        threshold=Decimal("70.00"),
        email_recipients='["alert@example.com"]',
        is_active=True,
        created_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(config)
    await db_session.flush()

    result = await alert_service.check_and_send_alerts(
        db=db_session, org_id=org_a.id, org_name="Org A", check_date=check_date
    )
    assert result.events_created == 0
    assert result.emails_sent == 0


@pytest.mark.asyncio
async def test_check_oos_creates_event(db_session, org_a):
    """oos config fires when in_stock = False."""
    from app.alerts import service as alert_service

    platform = Platform(id=uuid.uuid4(), name="Lenta-test", type="retailer")
    db_session.add(platform)

    brand = Brand(id=uuid.uuid4(), org_id=org_a.id, name="Brand OOS")
    db_session.add(brand)

    sku = SKU(id=uuid.uuid4(), org_id=org_a.id, brand_id=brand.id, name="OOS SKU", article="OOS-1")
    db_session.add(sku)

    sp = SKUPlatform(id=uuid.uuid4(), sku_id=sku.id, platform_id=platform.id)
    db_session.add(sp)

    check_date = date(2026, 1, 22)
    score = ContentScoreRead(
        id=uuid.uuid4(),
        sku_platform_id=sp.id,
        scored_at=check_date,
        in_stock=False,
        created_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(score)

    config = AlertConfig(
        id=uuid.uuid4(),
        org_id=org_a.id,
        alert_type="oos",
        threshold=None,
        email_recipients='["oos@example.com"]',
        is_active=True,
        created_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(config)
    await db_session.flush()

    with patch("app.alerts.service.send_alert_email", new_callable=AsyncMock) as mock_send:
        result = await alert_service.check_and_send_alerts(
            db=db_session, org_id=org_a.id, org_name="Org A", check_date=check_date
        )

    assert result.events_created == 1
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_deduplication_no_double_event(db_session, org_a):
    """Running check twice on the same day must not create duplicate events."""
    from app.alerts import service as alert_service

    platform = Platform(id=uuid.uuid4(), name="WB-dedup", type="marketplace")
    db_session.add(platform)

    brand = Brand(id=uuid.uuid4(), org_id=org_a.id, name="Brand Dedup")
    db_session.add(brand)

    sku = SKU(id=uuid.uuid4(), org_id=org_a.id, brand_id=brand.id, name="Dedup SKU", article="D-001")
    db_session.add(sku)

    sp = SKUPlatform(id=uuid.uuid4(), sku_id=sku.id, platform_id=platform.id)
    db_session.add(sp)

    check_date = date(2026, 1, 23)
    score = ContentScoreRead(
        id=uuid.uuid4(),
        sku_platform_id=sp.id,
        scored_at=check_date,
        content_total=Decimal("30.00"),
        created_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(score)

    config = AlertConfig(
        id=uuid.uuid4(),
        org_id=org_a.id,
        alert_type="content_drop",
        threshold=Decimal("70.00"),
        email_recipients='["d@e.com"]',
        is_active=True,
        created_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(config)
    await db_session.flush()

    with patch("app.alerts.service.send_alert_email", new_callable=AsyncMock):
        r1 = await alert_service.check_and_send_alerts(
            db=db_session, org_id=org_a.id, org_name="Org A", check_date=check_date
        )
        r2 = await alert_service.check_and_send_alerts(
            db=db_session, org_id=org_a.id, org_name="Org A", check_date=check_date
        )

    assert r1.events_created == 1
    assert r2.events_created == 0  # dedup: already alerted


@pytest.mark.asyncio
async def test_check_inactive_config_skipped(db_session, org_a):
    """Inactive configs must not trigger any events."""
    from app.alerts import service as alert_service

    platform = Platform(id=uuid.uuid4(), name="WB-inactive", type="marketplace")
    db_session.add(platform)

    brand = Brand(id=uuid.uuid4(), org_id=org_a.id, name="Brand Inactive")
    db_session.add(brand)

    sku = SKU(id=uuid.uuid4(), org_id=org_a.id, brand_id=brand.id, name="Inactive SKU", article="I-001")
    db_session.add(sku)

    sp = SKUPlatform(id=uuid.uuid4(), sku_id=sku.id, platform_id=platform.id)
    db_session.add(sp)

    check_date = date(2026, 1, 24)
    score = ContentScoreRead(
        id=uuid.uuid4(),
        sku_platform_id=sp.id,
        scored_at=check_date,
        content_total=Decimal("20.00"),
        created_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(score)

    config = AlertConfig(
        id=uuid.uuid4(),
        org_id=org_a.id,
        alert_type="content_drop",
        threshold=Decimal("70.00"),
        email_recipients='["x@y.com"]',
        is_active=False,  # INACTIVE
        created_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(config)
    await db_session.flush()

    result = await alert_service.check_and_send_alerts(
        db=db_session, org_id=org_a.id, org_name="Org A", check_date=check_date
    )
    assert result.events_created == 0


# ---------------------------------------------------------------------------
# Unit tests: email rendering
# ---------------------------------------------------------------------------


def test_render_html_contains_sku_name():
    from app.alerts.email import AlertEmailContext, _render_html

    ctx = AlertEmailContext(
        alert_type="content_drop",
        org_name="Test Org",
        check_date=date(2026, 1, 1),
        recipients=["a@b.com"],
        rows=[{"sku_name": "Майонез Провансаль", "sku_article": "ART-1", "platform_name": "WB", "value_after": Decimal("45.5")}],
    )
    html = _render_html(ctx)
    assert "Майонез Провансаль" in html
    assert "ART-1" in html
    assert "45.5" in html
    assert "WB" in html


@pytest.mark.asyncio
async def test_check_email_failure_event_persists(db_session, org_a):
    """When send_alert_email raises, the event must persist with is_sent=False."""
    from app.alerts import repository, service as alert_service

    platform = Platform(id=uuid.uuid4(), name="WB-fail", type="marketplace")
    db_session.add(platform)

    brand = Brand(id=uuid.uuid4(), org_id=org_a.id, name="Brand Fail")
    db_session.add(brand)

    sku = SKU(id=uuid.uuid4(), org_id=org_a.id, brand_id=brand.id, name="Fail SKU", article="F-001")
    db_session.add(sku)

    sp = SKUPlatform(id=uuid.uuid4(), sku_id=sku.id, platform_id=platform.id)
    db_session.add(sp)

    check_date = date(2026, 2, 1)
    score = ContentScoreRead(
        id=uuid.uuid4(),
        sku_platform_id=sp.id,
        scored_at=check_date,
        content_total=Decimal("30.00"),
        in_stock=True,
        created_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(score)

    config = AlertConfig(
        id=uuid.uuid4(),
        org_id=org_a.id,
        alert_type="content_drop",
        threshold=Decimal("70.00"),
        email_recipients='["fail@example.com"]',
        is_active=True,
        created_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(config)
    await db_session.flush()

    with patch(
        "app.alerts.service.send_alert_email",
        new_callable=AsyncMock,
        side_effect=Exception("SMTP timeout"),
    ):
        result = await alert_service.check_and_send_alerts(
            db=db_session, org_id=org_a.id, org_name="Org A", check_date=check_date
        )

    assert result.events_created == 1
    assert result.emails_sent == 0
    assert len(result.errors) == 1
    assert "SMTP timeout" in result.errors[0]

    # The event must be persisted with is_sent=False
    events, _ = await repository.list_events(db_session, org_id=org_a.id, limit=50, offset=0)
    fail_events = [e for e in events if e.scored_at == check_date and not e.is_sent]
    assert len(fail_events) == 1
    assert fail_events[0].sent_at is None


@pytest.mark.asyncio
async def test_list_events_cross_tenant_isolation(client, viewer_user, org_b, db_session):
    """Events belonging to org_b must not appear in org_a's event list."""
    # Create a config + event directly for org_b
    config_b = AlertConfig(
        id=uuid.uuid4(),
        org_id=org_b.id,
        alert_type="oos",
        email_recipients='["x@y.com"]',
        is_active=True,
        created_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(config_b)

    platform_b = Platform(id=uuid.uuid4(), name="WB-orgb", type="marketplace")
    db_session.add(platform_b)

    brand_b = Brand(id=uuid.uuid4(), org_id=org_b.id, name="Brand B")
    db_session.add(brand_b)

    sku_b = SKU(id=uuid.uuid4(), org_id=org_b.id, brand_id=brand_b.id, name="SKU B", article="B-001")
    db_session.add(sku_b)

    sp_b = SKUPlatform(id=uuid.uuid4(), sku_id=sku_b.id, platform_id=platform_b.id)
    db_session.add(sp_b)

    await db_session.flush()

    event_b = AlertEvent(
        id=uuid.uuid4(),
        org_id=org_b.id,
        config_id=config_b.id,
        sku_platform_id=sp_b.id,
        scored_at=date(2026, 2, 10),
        alert_type="oos",
        is_sent=False,
        triggered_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(event_b)
    await db_session.flush()

    resp = await client.get("/api/v1/alerts/events", headers=_auth(viewer_user))
    assert resp.status_code == 200
    event_ids = [e["id"] for e in resp.json()["items"]]
    assert str(event_b.id) not in event_ids, "Cross-tenant event leakage detected!"


def test_render_html_oos_type():
    from app.alerts.email import AlertEmailContext, _render_html

    ctx = AlertEmailContext(
        alert_type="oos",
        org_name="Test Org",
        check_date=date(2026, 1, 1),
        recipients=["a@b.com"],
        rows=[{"sku_name": "SKU", "sku_article": None, "platform_name": "Лента", "value_after": None}],
    )
    html = _render_html(ctx)
    assert "Out of Stock" in html
    assert "—" in html  # NULL article and value both render as —
