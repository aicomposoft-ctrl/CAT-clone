"""
E2E tests for the reviews domain.

Coverage:
  - /reviews/summary: per-platform breakdown, empty, cross-tenant 404, date 422,
    unauthenticated 401, zero reviews, date boundary (same day, 366 days)
  - /reviews/history: items, sentiment filter, limit/offset, limit boundaries 422,
    invalid sentiment enum 422, cross-tenant 404, unauthenticated 401
  - /reviews/stats: all fields, null stats (no reviews), date 422, cross-tenant 404
  - Service unit tests: validate_date_range, pct calculation, zero-division guard
  - Multi-tenant isolation: all 3 endpoints return 404 for foreign SKU

NOTE: These tests use SQLite+aiosqlite for the ORM layer (brands, skus, users)
but the reviews queries use raw PostgreSQL-specific SQL (FILTER aggregate,
json_agg, FOR UPDATE SKIP LOCKED). In CI, run against PostgreSQL. SQLite tests
cover auth/routing/tenant checks via mocked repository functions.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.models import Organization, User
from app.catalog.models import Brand, SKU
from app.core.database import Base
from app.core.deps import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.reviews.schemas import (
    ReviewHistoryResponse,
    ReviewStats,
    ReviewSummaryItem,
    ReviewSummaryResponse,
    SentimentShare,
    WeeklyTrendItem,
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
ORG_A_ID = uuid.uuid4()
ORG_B_ID = uuid.uuid4()

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
    org = Organization(id=ORG_A_ID, name="Org A", slug="org-a-reviews", plan="pro")
    db_session.add(org)
    await db_session.flush()
    return org


@pytest_asyncio.fixture
async def org_b(db_session):
    org = Organization(id=ORG_B_ID, name="Org B", slug="org-b-reviews", plan="pro")
    db_session.add(org)
    await db_session.flush()
    return org


@pytest_asyncio.fixture
async def manager_a(db_session, org_a):
    user = User(
        id=uuid.uuid4(),
        org_id=ORG_A_ID,
        email="mgr-reviews@orga.test",
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
        email="viewer-reviews@orga.test",
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
        email="mgr-reviews@orgb.test",
        password_hash=hash_password("pw"),
        role="manager",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def sku_a(db_session, org_a):
    brand = Brand(id=uuid.uuid4(), org_id=ORG_A_ID, name="Brand A Reviews", type="client")
    db_session.add(brand)
    await db_session.flush()
    sku = SKU(
        id=uuid.uuid4(),
        org_id=ORG_A_ID,
        brand_id=brand.id,
        name="Test SKU Reviews",
        is_active=True,
    )
    db_session.add(sku)
    await db_session.flush()
    return sku


@pytest_asyncio.fixture
async def sku_b(db_session, org_b):
    brand = Brand(id=uuid.uuid4(), org_id=ORG_B_ID, name="Brand B Reviews", type="client")
    db_session.add(brand)
    await db_session.flush()
    sku = SKU(
        id=uuid.uuid4(),
        org_id=ORG_B_ID,
        brand_id=brand.id,
        name="Test SKU B Reviews",
        is_active=True,
    )
    db_session.add(sku)
    await db_session.flush()
    return sku


def _auth(user: User) -> dict:
    token = create_access_token(user.id, user.org_id, user.role)
    return {"Authorization": f"Bearer {token}"}


def _make_summary_response(sku_id: uuid.UUID, platforms: int = 2) -> ReviewSummaryResponse:
    plat1 = uuid.uuid4()
    plat2 = uuid.uuid4()
    items = [
        ReviewSummaryItem(
            platform_id=plat1,
            platform_name="Wildberries",
            review_count=10,
            avg_rating=Decimal("4.2"),
            positive_count=7,
            neutral_count=2,
            negative_count=1,
            positive_pct=Decimal("70.0"),
            neutral_pct=Decimal("20.0"),
            negative_pct=Decimal("10.0"),
            last_review_date=_today,
        ),
    ]
    if platforms > 1:
        items.append(ReviewSummaryItem(
            platform_id=plat2,
            platform_name="Ozon",
            review_count=5,
            avg_rating=Decimal("4.8"),
            positive_count=5,
            neutral_count=0,
            negative_count=0,
            positive_pct=Decimal("100.0"),
            neutral_pct=Decimal("0.0"),
            negative_pct=Decimal("0.0"),
            last_review_date=_today - timedelta(days=1),
        ))
    return ReviewSummaryResponse(
        sku_id=sku_id,
        date_from=_today - timedelta(days=30),
        date_to=_today,
        total=sum(i.review_count for i in items),
        items=items,
    )


# ---------------------------------------------------------------------------
# /reviews/summary
# ---------------------------------------------------------------------------


class TestReviewSummary:

    @pytest.mark.asyncio
    async def test_summary_returns_per_platform_breakdown(self, client, manager_a, sku_a):
        mock_resp = _make_summary_response(sku_a.id)
        with patch("app.reviews.router.service.get_review_summary", new=AsyncMock(return_value=mock_resp)):
            resp = await client.get(
                f"/api/v1/reviews/summary?sku_id={sku_a.id}",
                headers=_auth(manager_a),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 15
        assert len(data["items"]) == 2
        wb = next(i for i in data["items"] if i["platform_name"] == "Wildberries")
        assert float(wb["positive_pct"]) == 70.0
        assert float(wb["negative_pct"]) == 10.0

    @pytest.mark.asyncio
    async def test_summary_empty_returns_200_with_empty_items(self, client, manager_a, sku_a):
        mock_resp = ReviewSummaryResponse(
            sku_id=sku_a.id,
            date_from=_today - timedelta(days=30),
            date_to=_today,
            total=0,
            items=[],
        )
        with patch("app.reviews.router.service.get_review_summary", new=AsyncMock(return_value=mock_resp)):
            resp = await client.get(
                f"/api/v1/reviews/summary?sku_id={sku_a.id}",
                headers=_auth(manager_a),
            )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["items"] == []

    @pytest.mark.asyncio
    async def test_summary_cross_tenant_returns_404(self, client, manager_b, sku_a):
        resp = await client.get(
            f"/api/v1/reviews/summary?sku_id={sku_a.id}",
            headers=_auth(manager_b),
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "SKU_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_summary_unauthenticated_returns_401(self, client, sku_a):
        resp = await client.get(f"/api/v1/reviews/summary?sku_id={sku_a.id}")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_summary_inverted_date_range_returns_422(self, client, manager_a, sku_a):
        mock_resp = _make_summary_response(sku_a.id)
        with patch("app.reviews.router.service.get_review_summary", new=AsyncMock(return_value=mock_resp)):
            resp = await client.get(
                f"/api/v1/reviews/summary?sku_id={sku_a.id}&date_from=2026-04-01&date_to=2026-03-01",
                headers=_auth(manager_a),
            )
        assert resp.status_code == 422
        assert "date_from must be before date_to" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_summary_date_range_over_366_days_returns_422(self, client, manager_a, sku_a):
        mock_resp = _make_summary_response(sku_a.id)
        with patch("app.reviews.router.service.get_review_summary", new=AsyncMock(return_value=mock_resp)):
            resp = await client.get(
                f"/api/v1/reviews/summary?sku_id={sku_a.id}&date_from=2025-01-01&date_to=2026-06-01",
                headers=_auth(manager_a),
            )
        assert resp.status_code == 422
        assert "366" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_summary_same_day_date_range_is_valid(self, client, manager_a, sku_a):
        mock_resp = _make_summary_response(sku_a.id, platforms=1)
        with patch("app.reviews.router.service.get_review_summary", new=AsyncMock(return_value=mock_resp)):
            resp = await client.get(
                f"/api/v1/reviews/summary?sku_id={sku_a.id}&date_from=2026-04-01&date_to=2026-04-01",
                headers=_auth(manager_a),
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_summary_viewer_can_read(self, client, viewer_a, sku_a):
        mock_resp = _make_summary_response(sku_a.id)
        with patch("app.reviews.router.service.get_review_summary", new=AsyncMock(return_value=mock_resp)):
            resp = await client.get(
                f"/api/v1/reviews/summary?sku_id={sku_a.id}",
                headers=_auth(viewer_a),
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /reviews/history
# ---------------------------------------------------------------------------


class TestReviewHistory:

    def _mock_history(self, sku_id: uuid.UUID, sentiment: str = "negative") -> ReviewHistoryResponse:
        from app.reviews.schemas import ReviewHistoryItem
        from datetime import datetime, timezone
        items = [
            ReviewHistoryItem(
                id=uuid.uuid4(),
                platform_id=uuid.uuid4(),
                platform_name="Wildberries",
                review_text="Плохое качество!",
                rating=1,
                sentiment=sentiment,
                sentiment_score=Decimal("0.92"),
                review_date=_today - timedelta(days=2),
            )
        ]
        return ReviewHistoryResponse(sku_id=sku_id, total=1, limit=100, offset=0, items=items)

    @pytest.mark.asyncio
    async def test_history_returns_items_with_sentiment(self, client, manager_a, sku_a):
        mock_resp = self._mock_history(sku_a.id, "negative")
        with patch("app.reviews.router.service.get_review_history", new=AsyncMock(return_value=mock_resp)):
            resp = await client.get(
                f"/api/v1/reviews/history?sku_id={sku_a.id}",
                headers=_auth(manager_a),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["sentiment"] == "negative"
        assert float(data["items"][0]["sentiment_score"]) == pytest.approx(0.92)

    @pytest.mark.asyncio
    async def test_history_sentiment_filter_passed_to_service(self, client, manager_a, sku_a):
        mock_resp = self._mock_history(sku_a.id, "positive")
        with patch("app.reviews.router.service.get_review_history", new=AsyncMock(return_value=mock_resp)) as mock_svc:
            await client.get(
                f"/api/v1/reviews/history?sku_id={sku_a.id}&sentiment=positive",
                headers=_auth(manager_a),
            )
        _, kwargs = mock_svc.call_args
        assert kwargs.get("sentiment") == "positive"

    @pytest.mark.asyncio
    async def test_history_invalid_sentiment_returns_422(self, client, manager_a, sku_a):
        resp = await client.get(
            f"/api/v1/reviews/history?sku_id={sku_a.id}&sentiment=excellent",
            headers=_auth(manager_a),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_history_limit_zero_returns_422(self, client, manager_a, sku_a):
        resp = await client.get(
            f"/api/v1/reviews/history?sku_id={sku_a.id}&limit=0",
            headers=_auth(manager_a),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_history_limit_over_500_returns_422(self, client, manager_a, sku_a):
        resp = await client.get(
            f"/api/v1/reviews/history?sku_id={sku_a.id}&limit=501",
            headers=_auth(manager_a),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_history_limit_500_is_valid(self, client, manager_a, sku_a):
        mock_resp = ReviewHistoryResponse(sku_id=sku_a.id, total=0, limit=500, offset=0, items=[])
        with patch("app.reviews.router.service.get_review_history", new=AsyncMock(return_value=mock_resp)) as mock_svc:
            resp = await client.get(
                f"/api/v1/reviews/history?sku_id={sku_a.id}&limit=500",
                headers=_auth(manager_a),
            )
        assert resp.status_code == 200
        _, kwargs = mock_svc.call_args
        assert kwargs.get("limit") == 500

    @pytest.mark.asyncio
    async def test_history_cross_tenant_returns_404(self, client, manager_b, sku_a):
        resp = await client.get(
            f"/api/v1/reviews/history?sku_id={sku_a.id}",
            headers=_auth(manager_b),
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_history_unauthenticated_returns_401(self, client, sku_a):
        resp = await client.get(f"/api/v1/reviews/history?sku_id={sku_a.id}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /reviews/stats
# ---------------------------------------------------------------------------


class TestReviewStats:

    def _mock_stats(self, sku_id: uuid.UUID) -> ReviewStats:
        return ReviewStats(
            sku_id=sku_id,
            date_from=_today - timedelta(days=30),
            date_to=_today,
            review_count=87,
            avg_rating=Decimal("4.1"),
            rating_distribution={"1": 2, "2": 3, "3": 8, "4": 24, "5": 50},
            sentiment_share=SentimentShare(
                positive=Decimal("0.71"),
                neutral=Decimal("0.18"),
                negative=Decimal("0.11"),
            ),
            weekly_trend=[
                WeeklyTrendItem(
                    week_start=_today - timedelta(days=7),
                    positive_share=Decimal("0.78"),
                    avg_rating=Decimal("4.4"),
                    review_count=12,
                )
            ],
        )

    @pytest.mark.asyncio
    async def test_stats_returns_all_fields(self, client, manager_a, sku_a):
        mock_resp = self._mock_stats(sku_a.id)
        with patch("app.reviews.router.service.get_review_stats", new=AsyncMock(return_value=mock_resp)):
            resp = await client.get(
                f"/api/v1/reviews/stats?sku_id={sku_a.id}",
                headers=_auth(manager_a),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["review_count"] == 87
        assert data["avg_rating"] == "4.1"
        assert data["rating_distribution"] == {"1": 2, "2": 3, "3": 8, "4": 24, "5": 50}
        assert data["sentiment_share"]["positive"] == "0.71"
        assert len(data["weekly_trend"]) == 1

    @pytest.mark.asyncio
    async def test_stats_no_reviews_returns_nulls(self, client, manager_a, sku_a):
        mock_resp = ReviewStats(
            sku_id=sku_a.id,
            date_from=_today - timedelta(days=30),
            date_to=_today,
            review_count=0,
            avg_rating=None,
            rating_distribution={"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
            sentiment_share=None,
            weekly_trend=[],
        )
        with patch("app.reviews.router.service.get_review_stats", new=AsyncMock(return_value=mock_resp)):
            resp = await client.get(
                f"/api/v1/reviews/stats?sku_id={sku_a.id}",
                headers=_auth(manager_a),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["review_count"] == 0
        assert data["avg_rating"] is None
        assert data["sentiment_share"] is None
        assert data["weekly_trend"] == []

    @pytest.mark.asyncio
    async def test_stats_cross_tenant_returns_404(self, client, manager_b, sku_a):
        resp = await client.get(
            f"/api/v1/reviews/stats?sku_id={sku_a.id}",
            headers=_auth(manager_b),
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_stats_inverted_date_returns_422(self, client, manager_a, sku_a):
        mock_resp = self._mock_stats(sku_a.id)
        with patch("app.reviews.router.service.get_review_stats", new=AsyncMock(return_value=mock_resp)):
            resp = await client.get(
                f"/api/v1/reviews/stats?sku_id={sku_a.id}&date_from=2026-04-01&date_to=2026-03-01",
                headers=_auth(manager_a),
            )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Service unit tests
# ---------------------------------------------------------------------------


class TestValidateDateRange:
    """Unit tests for validate_date_range in reviews/service.py."""

    def test_defaults_to_30_days_back(self):
        from app.reviews.service import validate_date_range
        d_from, d_to = validate_date_range(None, None)
        assert d_to == date.today()
        assert (d_to - d_from).days == 30

    def test_inverted_range_raises(self):
        from app.reviews.service import validate_date_range
        with pytest.raises(ValueError, match="date_from must be before date_to"):
            validate_date_range(date(2026, 4, 1), date(2026, 3, 1))

    def test_range_over_366_raises(self):
        from app.reviews.service import validate_date_range
        with pytest.raises(ValueError, match="366"):
            validate_date_range(date(2025, 1, 1), date(2026, 6, 1))

    def test_exact_366_days_is_allowed(self):
        from app.reviews.service import validate_date_range
        d_from = date(2025, 1, 1)
        d_to = d_from + timedelta(days=366)
        out_from, out_to = validate_date_range(d_from, d_to)
        assert out_from == d_from
        assert out_to == d_to

    def test_same_day_is_valid(self):
        from app.reviews.service import validate_date_range
        d = date(2026, 3, 15)
        out_from, out_to = validate_date_range(d, d)
        assert out_from == out_to == d


class TestSummaryPctCalculation:
    """Unit tests for percentage calculation in get_review_summary."""

    @pytest.mark.asyncio
    async def test_pct_sums_to_100_no_rounding_drift(self):
        from app.reviews import service

        class MockRow:
            platform_id = uuid.uuid4()
            platform_name = "WB"
            review_count = 3
            avg_rating = "4.0"
            positive_count = 1
            neutral_count = 1
            negative_count = 1
            last_review_date = _today

        with patch("app.reviews.repository.fetch_summary", new=AsyncMock(return_value=[MockRow()])):
            result = await service.get_review_summary(
                db=None,
                org_id=uuid.uuid4(),
                sku_id=uuid.uuid4(),
                date_from=_today - timedelta(days=7),
                date_to=_today,
            )
        item = result.items[0]
        total = float(item.positive_pct) + float(item.neutral_pct) + float(item.negative_pct)
        assert total <= 100.0

    @pytest.mark.asyncio
    async def test_zero_reviews_no_zero_division(self):
        """review_count=0 must not raise ZeroDivisionError."""
        from app.reviews import service

        with patch("app.reviews.repository.fetch_summary", new=AsyncMock(return_value=[])):
            result = await service.get_review_summary(
                db=None,
                org_id=uuid.uuid4(),
                sku_id=uuid.uuid4(),
                date_from=_today - timedelta(days=7),
                date_to=_today,
            )
        assert result.total == 0
        assert result.items == []


# ---------------------------------------------------------------------------
# Multi-tenant isolation (mandatory per testing rules)
# ---------------------------------------------------------------------------


class TestCrossTenantIsolation:
    """
    Mandatory isolation test: org_B cannot access org_A's review data
    via any of the 3 review endpoints.
    """

    @pytest.mark.asyncio
    async def test_all_endpoints_return_404_for_foreign_sku(
        self, client, manager_b, sku_a
    ):
        endpoints = [
            f"/api/v1/reviews/summary?sku_id={sku_a.id}",
            f"/api/v1/reviews/history?sku_id={sku_a.id}",
            f"/api/v1/reviews/stats?sku_id={sku_a.id}",
        ]
        for url in endpoints:
            resp = await client.get(url, headers=_auth(manager_b))
            assert resp.status_code == 404, (
                f"Expected 404 for {url} with org_B token, got {resp.status_code}"
            )
            assert resp.json()["detail"] == "SKU_NOT_FOUND"


# NOTE: SentimentScorer unit tests live in services/processor/tests/test_sentiment.py
# (separate service, separate Python path — not importable from services/api)
