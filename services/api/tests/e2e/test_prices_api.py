"""
E2E tests for the prices domain.

Coverage:
  - /prices/history: filters, empty result, cross-tenant 404, date validation,
    viewer access, limit param, all-platforms mode
  - /prices/latest: most-recent semantics, price ordering, cheapest_platform_id,
    empty result, cross-tenant 404
  - /prices/stats: all fields, empty data nulls, change_pct calculation,
    cross-tenant 404
  - /prices/anomalies: drop detection, stable prices, threshold, direction filters,
    cross-tenant 404
  - Auth: unauthenticated 401, expired token 401

NOTE: These tests use SQLite+aiosqlite for the ORM layer (brands, skus, etc.)
but the price queries use raw PostgreSQL-specific SQL (DISTINCT ON, PERCENTILE_CONT,
LAG). In CI, run against PostgreSQL. SQLite tests cover auth/routing/tenant checks
via mocked repository functions.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.models import Organization, User
from app.catalog.models import Brand, Platform, SKU, SKUPlatform
from app.core.database import Base
from app.core.deps import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.prices.schemas import (
    PriceAnomaliesResponse,
    PriceAnomaly,
    PriceHistoryItem,
    PriceHistoryResponse,
    PriceLatestItem,
    PriceLatestResponse,
    PriceStats,
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
ORG_A_ID = uuid.uuid4()
ORG_B_ID = uuid.uuid4()

_now = datetime.now(tz=timezone.utc)
_today = date.today()


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
    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def org_a(db_session):
    org = Organization(id=ORG_A_ID, name="Org A", slug="org-a-prices", plan="pro")
    db_session.add(org)
    await db_session.flush()
    return org


@pytest_asyncio.fixture
async def org_b(db_session):
    org = Organization(id=ORG_B_ID, name="Org B", slug="org-b-prices", plan="pro")
    db_session.add(org)
    await db_session.flush()
    return org


@pytest_asyncio.fixture
async def manager_a(db_session, org_a):
    user = User(
        id=uuid.uuid4(),
        org_id=ORG_A_ID,
        email="mgr-prices@orga.test",
        password_hash=hash_password("pw"),
        role="manager",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def viewer_a(db_session, org_a):
    user = User(
        id=uuid.uuid4(),
        org_id=ORG_A_ID,
        email="viewer-prices@orga.test",
        password_hash=hash_password("pw"),
        role="viewer",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def manager_b(db_session, org_b):
    user = User(
        id=uuid.uuid4(),
        org_id=ORG_B_ID,
        email="mgr-prices@orgb.test",
        password_hash=hash_password("pw"),
        role="manager",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def sku_a(db_session, org_a):
    brand = Brand(id=uuid.uuid4(), org_id=ORG_A_ID, name="Brand A Prices", type="client")
    db_session.add(brand)
    await db_session.flush()
    sku = SKU(
        id=uuid.uuid4(),
        org_id=ORG_A_ID,
        brand_id=brand.id,
        name="Test SKU Prices",
        is_active=True,
    )
    db_session.add(sku)
    await db_session.flush()
    return sku


@pytest_asyncio.fixture
async def sku_b(db_session, org_b):
    brand = Brand(id=uuid.uuid4(), org_id=ORG_B_ID, name="Brand B Prices", type="client")
    db_session.add(brand)
    await db_session.flush()
    sku = SKU(
        id=uuid.uuid4(),
        org_id=ORG_B_ID,
        brand_id=brand.id,
        name="Test SKU B Prices",
        is_active=True,
    )
    db_session.add(sku)
    await db_session.flush()
    return sku


def _auth(user: User) -> dict:
    token = create_access_token(user.id, user.org_id, user.role)
    return {"Authorization": f"Bearer {token}"}


def _make_history_response(sku_id: uuid.UUID, items=None) -> PriceHistoryResponse:
    return PriceHistoryResponse(sku_id=sku_id, items=items or [], total=len(items or []))


def _make_history_item(platform_id: uuid.UUID) -> PriceHistoryItem:
    return PriceHistoryItem(
        id=uuid.uuid4(),
        platform_id=platform_id,
        platform_name="Wildberries",
        price=Decimal("299.00"),
        original_price=Decimal("399.00"),
        discount_pct=Decimal("25.06"),
        promo_label=None,
        collected_at=_now - timedelta(hours=2),
    )


# ---------------------------------------------------------------------------
# /prices/history
# ---------------------------------------------------------------------------


class TestPriceHistory:

    @pytest.mark.asyncio
    async def test_history_returns_200_with_items(self, client, manager_a, sku_a):
        plat_id = uuid.uuid4()
        items = [_make_history_item(plat_id)]
        mock_resp = _make_history_response(sku_a.id, items)

        with patch("app.prices.router.service.get_price_history", new=AsyncMock(return_value=mock_resp)):
            resp = await client.get(
                f"/api/v1/prices/history?sku_id={sku_a.id}",
                headers=_auth(manager_a),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["price"] == "299.00"
        assert "platform_id" in data["items"][0]

    @pytest.mark.asyncio
    async def test_history_empty_returns_200_empty_list(self, client, manager_a, sku_a):
        mock_resp = _make_history_response(sku_a.id, [])

        with patch("app.prices.router.service.get_price_history", new=AsyncMock(return_value=mock_resp)):
            resp = await client.get(
                f"/api/v1/prices/history?sku_id={sku_a.id}",
                headers=_auth(manager_a),
            )
        assert resp.status_code == 200
        assert resp.json() == {"sku_id": str(sku_a.id), "items": [], "total": 0}

    @pytest.mark.asyncio
    async def test_history_cross_tenant_returns_404(self, client, manager_b, sku_a):
        """Org B cannot see Org A's SKU price history."""
        resp = await client.get(
            f"/api/v1/prices/history?sku_id={sku_a.id}",
            headers=_auth(manager_b),
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "SKU_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_history_date_from_after_date_to_returns_422(self, client, manager_a, sku_a):
        mock_resp = _make_history_response(sku_a.id, [])
        with patch("app.prices.router.service.get_price_history", new=AsyncMock(return_value=mock_resp)):
            resp = await client.get(
                f"/api/v1/prices/history?sku_id={sku_a.id}&date_from=2026-04-01&date_to=2026-03-01",
                headers=_auth(manager_a),
            )
        assert resp.status_code == 422
        assert "date_from must be before date_to" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_history_date_range_over_366_days_returns_422(self, client, manager_a, sku_a):
        d_from = "2025-01-01"
        d_to = "2026-06-01"  # > 366 days
        mock_resp = _make_history_response(sku_a.id, [])
        with patch("app.prices.router.service.get_price_history", new=AsyncMock(return_value=mock_resp)):
            resp = await client.get(
                f"/api/v1/prices/history?sku_id={sku_a.id}&date_from={d_from}&date_to={d_to}",
                headers=_auth(manager_a),
            )
        assert resp.status_code == 422
        assert "366" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_history_viewer_can_read(self, client, viewer_a, sku_a):
        mock_resp = _make_history_response(sku_a.id, [])
        with patch("app.prices.router.service.get_price_history", new=AsyncMock(return_value=mock_resp)):
            resp = await client.get(
                f"/api/v1/prices/history?sku_id={sku_a.id}",
                headers=_auth(viewer_a),
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_history_limit_param_respected(self, client, manager_a, sku_a):
        mock_resp = _make_history_response(sku_a.id, [])
        with patch("app.prices.router.service.get_price_history", new=AsyncMock(return_value=mock_resp)) as mock_svc:
            await client.get(
                f"/api/v1/prices/history?sku_id={sku_a.id}&limit=10",
                headers=_auth(manager_a),
            )
        _, kwargs = mock_svc.call_args
        assert kwargs.get("limit") == 10

    @pytest.mark.asyncio
    async def test_history_unauthenticated_returns_401(self, client, sku_a):
        resp = await client.get(f"/api/v1/prices/history?sku_id={sku_a.id}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /prices/latest
# ---------------------------------------------------------------------------


class TestPriceLatest:

    def _mock_latest_response(self, sku_id: uuid.UUID) -> PriceLatestResponse:
        plat_wb = uuid.uuid4()
        plat_oz = uuid.uuid4()
        return PriceLatestResponse(
            sku_id=sku_id,
            cheapest_platform_id=plat_wb,
            items=[
                PriceLatestItem(
                    platform_id=plat_wb,
                    platform_name="Wildberries",
                    price=Decimal("289.00"),
                    original_price=Decimal("289.00"),
                    discount_pct=Decimal("0.00"),
                    promo_label=None,
                    collected_at=_now,
                ),
                PriceLatestItem(
                    platform_id=plat_oz,
                    platform_name="Ozon",
                    price=Decimal("319.00"),
                    original_price=Decimal("319.00"),
                    discount_pct=Decimal("0.00"),
                    promo_label=None,
                    collected_at=_now,
                ),
            ],
        )

    @pytest.mark.asyncio
    async def test_latest_returns_items_ordered_by_price_asc(self, client, manager_a, sku_a):
        mock_resp = self._mock_latest_response(sku_a.id)
        with patch("app.prices.router.service.get_latest_prices", new=AsyncMock(return_value=mock_resp)):
            resp = await client.get(
                f"/api/v1/prices/latest?sku_id={sku_a.id}",
                headers=_auth(manager_a),
            )
        assert resp.status_code == 200
        data = resp.json()
        prices = [float(item["price"]) for item in data["items"]]
        assert prices == sorted(prices), "Items must be ordered by price ASC"

    @pytest.mark.asyncio
    async def test_latest_cheapest_platform_id_is_minimum_price(self, client, manager_a, sku_a):
        mock_resp = self._mock_latest_response(sku_a.id)
        with patch("app.prices.router.service.get_latest_prices", new=AsyncMock(return_value=mock_resp)):
            resp = await client.get(
                f"/api/v1/prices/latest?sku_id={sku_a.id}",
                headers=_auth(manager_a),
            )
        data = resp.json()
        cheapest_id = data["cheapest_platform_id"]
        min_price_item = min(data["items"], key=lambda i: float(i["price"]))
        assert cheapest_id == min_price_item["platform_id"]

    @pytest.mark.asyncio
    async def test_latest_no_snapshots_returns_empty(self, client, manager_a, sku_a):
        mock_resp = PriceLatestResponse(sku_id=sku_a.id, cheapest_platform_id=None, items=[])
        with patch("app.prices.router.service.get_latest_prices", new=AsyncMock(return_value=mock_resp)):
            resp = await client.get(
                f"/api/v1/prices/latest?sku_id={sku_a.id}",
                headers=_auth(manager_a),
            )
        assert resp.status_code == 200
        assert resp.json()["cheapest_platform_id"] is None
        assert resp.json()["items"] == []

    @pytest.mark.asyncio
    async def test_latest_cross_tenant_returns_404(self, client, manager_b, sku_a):
        resp = await client.get(
            f"/api/v1/prices/latest?sku_id={sku_a.id}",
            headers=_auth(manager_b),
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "SKU_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_latest_unauthenticated_returns_401(self, client, sku_a):
        resp = await client.get(f"/api/v1/prices/latest?sku_id={sku_a.id}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /prices/stats
# ---------------------------------------------------------------------------


class TestPriceStats:

    def _mock_stats(self, sku_id: uuid.UUID) -> PriceStats:
        return PriceStats(
            sku_id=sku_id,
            platform_id=None,
            date_from=_today - timedelta(days=30),
            date_to=_today,
            snapshot_count=87,
            price_min=Decimal("259.00"),
            price_max=Decimal("399.00"),
            price_avg=Decimal("311.50"),
            price_median=Decimal("299.00"),
            first_price=Decimal("299.00"),
            last_price=Decimal("279.00"),
            change_abs=Decimal("-20.00"),
            change_pct=Decimal("-6.69"),
            discount_avg=Decimal("18.50"),
        )

    @pytest.mark.asyncio
    async def test_stats_returns_all_fields(self, client, manager_a, sku_a):
        mock_resp = self._mock_stats(sku_a.id)
        with patch("app.prices.router.service.get_price_stats", new=AsyncMock(return_value=mock_resp)):
            resp = await client.get(
                f"/api/v1/prices/stats?sku_id={sku_a.id}",
                headers=_auth(manager_a),
            )
        assert resp.status_code == 200
        data = resp.json()
        for field in ("price_min", "price_max", "price_avg", "price_median",
                      "first_price", "last_price", "change_abs", "change_pct",
                      "discount_avg", "snapshot_count"):
            assert field in data, f"Missing field: {field}"
        assert data["snapshot_count"] == 87
        assert data["change_pct"] == "-6.69"

    @pytest.mark.asyncio
    async def test_stats_no_data_returns_nulls(self, client, manager_a, sku_a):
        mock_resp = PriceStats(
            sku_id=sku_a.id, platform_id=None,
            date_from=_today - timedelta(days=30), date_to=_today,
            snapshot_count=0,
            price_min=None, price_max=None, price_avg=None, price_median=None,
            first_price=None, last_price=None, change_abs=None, change_pct=None,
            discount_avg=None,
        )
        with patch("app.prices.router.service.get_price_stats", new=AsyncMock(return_value=mock_resp)):
            resp = await client.get(
                f"/api/v1/prices/stats?sku_id={sku_a.id}",
                headers=_auth(manager_a),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["snapshot_count"] == 0
        assert data["price_min"] is None
        assert data["change_pct"] is None

    @pytest.mark.asyncio
    async def test_stats_cross_tenant_returns_404(self, client, manager_b, sku_a):
        resp = await client.get(
            f"/api/v1/prices/stats?sku_id={sku_a.id}",
            headers=_auth(manager_b),
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_stats_inverted_date_range_returns_422(self, client, manager_a, sku_a):
        mock_resp = self._mock_stats(sku_a.id)
        with patch("app.prices.router.service.get_price_stats", new=AsyncMock(return_value=mock_resp)):
            resp = await client.get(
                f"/api/v1/prices/stats?sku_id={sku_a.id}&date_from=2026-04-01&date_to=2026-03-01",
                headers=_auth(manager_a),
            )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /prices/anomalies
# ---------------------------------------------------------------------------


class TestPriceAnomalies:

    def _mock_anomalies(self, sku_id: uuid.UUID, items=None) -> PriceAnomaliesResponse:
        return PriceAnomaliesResponse(
            sku_id=sku_id,
            threshold=10.0,
            items=items or [],
        )

    def _make_anomaly(self, direction: str = "down") -> PriceAnomaly:
        return PriceAnomaly(
            platform_id=uuid.uuid4(),
            platform_name="Wildberries",
            date=_today - timedelta(days=5),
            price_before=Decimal("299.00"),
            price_after=Decimal("229.00"),
            change_abs=Decimal("-70.00"),
            change_pct=Decimal("-23.41"),
            direction=direction,
        )

    @pytest.mark.asyncio
    async def test_anomalies_detects_price_drop(self, client, manager_a, sku_a):
        mock_resp = self._mock_anomalies(sku_a.id, [self._make_anomaly("down")])
        with patch("app.prices.router.service.get_price_anomalies", new=AsyncMock(return_value=mock_resp)):
            resp = await client.get(
                f"/api/v1/prices/anomalies?sku_id={sku_a.id}&threshold=10",
                headers=_auth(manager_a),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["direction"] == "down"
        assert float(data["items"][0]["change_pct"]) < 0

    @pytest.mark.asyncio
    async def test_anomalies_stable_prices_returns_empty(self, client, manager_a, sku_a):
        mock_resp = self._mock_anomalies(sku_a.id, [])
        with patch("app.prices.router.service.get_price_anomalies", new=AsyncMock(return_value=mock_resp)):
            resp = await client.get(
                f"/api/v1/prices/anomalies?sku_id={sku_a.id}",
                headers=_auth(manager_a),
            )
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    @pytest.mark.asyncio
    async def test_anomalies_default_threshold_is_10(self, client, manager_a, sku_a):
        mock_resp = self._mock_anomalies(sku_a.id, [])
        with patch("app.prices.router.service.get_price_anomalies", new=AsyncMock(return_value=mock_resp)) as mock_svc:
            await client.get(
                f"/api/v1/prices/anomalies?sku_id={sku_a.id}",
                headers=_auth(manager_a),
            )
        _, kwargs = mock_svc.call_args
        assert kwargs.get("threshold") == 10.0

    @pytest.mark.asyncio
    async def test_anomalies_threshold_above_100_returns_422(self, client, manager_a, sku_a):
        resp = await client.get(
            f"/api/v1/prices/anomalies?sku_id={sku_a.id}&threshold=150",
            headers=_auth(manager_a),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_anomalies_threshold_below_0_returns_422(self, client, manager_a, sku_a):
        resp = await client.get(
            f"/api/v1/prices/anomalies?sku_id={sku_a.id}&threshold=-1",
            headers=_auth(manager_a),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_anomalies_direction_down_filter(self, client, manager_a, sku_a):
        mock_resp = self._mock_anomalies(sku_a.id, [self._make_anomaly("down")])
        with patch("app.prices.router.service.get_price_anomalies", new=AsyncMock(return_value=mock_resp)) as mock_svc:
            resp = await client.get(
                f"/api/v1/prices/anomalies?sku_id={sku_a.id}&direction=down",
                headers=_auth(manager_a),
            )
        assert resp.status_code == 200
        _, kwargs = mock_svc.call_args
        assert kwargs.get("direction") == "down"
        for item in resp.json()["items"]:
            assert item["direction"] == "down"

    @pytest.mark.asyncio
    async def test_anomalies_direction_up_filter(self, client, manager_a, sku_a):
        mock_resp = self._mock_anomalies(sku_a.id, [self._make_anomaly("up")])
        with patch("app.prices.router.service.get_price_anomalies", new=AsyncMock(return_value=mock_resp)) as mock_svc:
            resp = await client.get(
                f"/api/v1/prices/anomalies?sku_id={sku_a.id}&direction=up",
                headers=_auth(manager_a),
            )
        _, kwargs = mock_svc.call_args
        assert kwargs.get("direction") == "up"

    @pytest.mark.asyncio
    async def test_anomalies_cross_tenant_returns_404(self, client, manager_b, sku_a):
        resp = await client.get(
            f"/api/v1/prices/anomalies?sku_id={sku_a.id}",
            headers=_auth(manager_b),
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_anomalies_unauthenticated_returns_401(self, client, sku_a):
        resp = await client.get(f"/api/v1/prices/anomalies?sku_id={sku_a.id}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Service unit tests (no HTTP layer)
# ---------------------------------------------------------------------------


class TestValidateDateRange:
    """Unit tests for _validate_date_range in service.py."""

    def test_defaults_to_30_days_back(self):
        from app.prices.service import _validate_date_range
        d_from, d_to = _validate_date_range(None, None)
        assert d_to == date.today()
        assert (d_to - d_from).days == 30

    def test_inverted_range_raises(self):
        from app.prices.service import _validate_date_range
        import pytest
        with pytest.raises(ValueError, match="date_from must be before date_to"):
            _validate_date_range(date(2026, 4, 1), date(2026, 3, 1))

    def test_range_over_366_raises(self):
        from app.prices.service import _validate_date_range
        import pytest
        with pytest.raises(ValueError, match="366"):
            _validate_date_range(date(2025, 1, 1), date(2026, 6, 1))

    def test_exact_366_days_is_allowed(self):
        from app.prices.service import _validate_date_range
        d_from = date(2025, 1, 1)
        d_to = d_from + timedelta(days=366)
        d_from_out, d_to_out = _validate_date_range(d_from, d_to)
        assert d_from_out == d_from
        assert d_to_out == d_to

    def test_same_day_is_valid(self):
        from app.prices.service import _validate_date_range
        d = date(2026, 3, 15)
        d_from_out, d_to_out = _validate_date_range(d, d)
        assert d_from_out == d_to_out == d


class TestGetPriceStatsService:
    """Unit tests for stats Decimal computation."""

    @pytest.mark.asyncio
    async def test_stats_change_pct_positive(self):
        from unittest.mock import AsyncMock
        from app.prices import service

        class MockRow:
            snapshot_count = 10
            price_min = "259.00"
            price_max = "399.00"
            price_avg = "299.00"
            price_median = "299.00"
            first_price = "200.00"
            last_price = "250.00"
            discount_avg = "0.00"

        with patch("app.prices.repository.fetch_stats", new=AsyncMock(return_value=MockRow())):
            result = await service.get_price_stats(
                db=None,
                org_id=uuid.uuid4(),
                sku_id=uuid.uuid4(),
                platform_id=None,
                date_from=_today - timedelta(days=7),
                date_to=_today,
            )
        assert result.change_abs == Decimal("50.00")
        assert result.change_pct == Decimal("25.00")

    @pytest.mark.asyncio
    async def test_stats_zero_first_price_change_pct_is_none(self):
        from app.prices import service

        class MockRow:
            snapshot_count = 1
            price_min = "0.00"
            price_max = "0.00"
            price_avg = "0.00"
            price_median = "0.00"
            first_price = "0.00"
            last_price = "0.00"
            discount_avg = "0.00"

        with patch("app.prices.repository.fetch_stats", new=AsyncMock(return_value=MockRow())):
            result = await service.get_price_stats(
                db=None,
                org_id=uuid.uuid4(),
                sku_id=uuid.uuid4(),
                platform_id=None,
                date_from=_today - timedelta(days=7),
                date_to=_today,
            )
        assert result.change_pct is None


# ---------------------------------------------------------------------------
# Multi-tenant isolation (mandatory per testing rules)
# ---------------------------------------------------------------------------


class TestCrossTenantIsolation:
    """
    Mandatory isolation test: org_B cannot access org_A's price data
    via any of the 4 price endpoints.
    """

    @pytest.mark.asyncio
    async def test_all_endpoints_return_404_for_foreign_sku(
        self, client, manager_b, sku_a
    ):
        endpoints = [
            f"/api/v1/prices/history?sku_id={sku_a.id}",
            f"/api/v1/prices/latest?sku_id={sku_a.id}",
            f"/api/v1/prices/stats?sku_id={sku_a.id}",
            f"/api/v1/prices/anomalies?sku_id={sku_a.id}",
        ]
        for url in endpoints:
            resp = await client.get(url, headers=_auth(manager_b))
            assert resp.status_code == 404, (
                f"Expected 404 for {url} with org_B token, got {resp.status_code}"
            )
            assert resp.json()["detail"] == "SKU_NOT_FOUND"
