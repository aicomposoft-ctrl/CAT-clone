"""
Unit tests for WB Celery tasks.

DB and scraper are mocked — no real DB or network calls.
Tests cover:
  - Happy-path DB writes for content / price / stock / reviews tasks
  - NO_NM_ID silent skip
  - NOT_FOUND silent skip (no DB write)
  - Missing sku_platform silent skip
  - Partial-row contract for stock task (content fields stay NULL)
  - Review deduplication (on_conflict_do_nothing)
  - Orchestrator dispatches correct task counts
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

import pytest

from app.core.base_scraper import (
    ContentData,
    PriceData,
    ReviewData,
    ScraperError,
    StockData,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sp(nm_id="12345678", sp_id=None, sku_id=None, org_id=None):
    """Return a minimal SKUPlatform-like mock."""
    sp = MagicMock()
    sp.id = sp_id or uuid.uuid4()
    sp.sku_id = sku_id or uuid.uuid4()
    sp.external_id = nm_id
    sp.sku = MagicMock()
    sp.sku.org_id = org_id or uuid.uuid4()
    return sp


def _make_content():
    return ContentData(
        title="Test Product",
        description="A great product",
        composition="Cotton 100%",
        image_url="https://basket-01.wbbasket.ru/vol123/part12345/12345678/images/big/1.jpg",
    )


def _make_price():
    return PriceData(
        price=Decimal("299.00"),
        original_price=Decimal("399.00"),
        discount_pct=Decimal("25.06"),
        promo_label="Sale!",
    )


def _make_stock(in_stock=True, total_qty=15):
    return StockData(in_stock=in_stock, total_qty=total_qty)


def _make_reviews():
    return [
        ReviewData(
            external_review_id="rev-001",
            review_text="Отлично!",
            rating=5,
            review_date=date(2026, 3, 1),
        ),
        ReviewData(
            external_review_id="rev-002",
            review_text="Нормально",
            rating=3,
            review_date=date(2026, 2, 15),
        ),
    ]


# ---------------------------------------------------------------------------
# collect_wb_content
# ---------------------------------------------------------------------------

class TestCollectWbContent:

    def _run(self, sp=None, content=None, scraper_side_effect=None, existing_score=None):
        sp = sp or _make_sp()

        # Two separate DB sessions: first loads sp, second does the upsert
        db1 = MagicMock()
        db1.query.return_value.join.return_value.filter.return_value.first.return_value = sp

        db2 = MagicMock()
        db2.query.return_value.filter.return_value.first.return_value = existing_score

        call_count = [0]

        def fake_cm():
            call_count[0] += 1
            db = db1 if call_count[0] == 1 else db2
            cm = MagicMock()
            cm.__enter__ = lambda s: db
            cm.__exit__ = MagicMock(return_value=False)
            return cm

        with (
            patch("app.tasks.wb_content_task.get_db_session", side_effect=fake_cm),
            patch("app.tasks.wb_content_task.WildberriesScraper"),
            patch("app.tasks.wb_content_task.asyncio.run") as mock_run,
            patch("app.tasks.wb_content_task._get_minio") as mock_minio,
            patch("app.tasks.wb_content_task.httpx.get") as mock_httpx,
        ):
            if scraper_side_effect:
                mock_run.side_effect = scraper_side_effect
            else:
                mock_run.return_value = content or _make_content()

            mock_minio.return_value.upload = MagicMock()
            mock_httpx.return_value.content = b"\xff\xd8\xff" + b"fake_image_data"

            from app.tasks.wb_content_task import collect_wb_content
            collect_wb_content(str(sp.id))

            return db2  # db2 is the session that does the upsert

    def test_happy_path_adds_content_score(self):
        sp = _make_sp()
        mock_db = self._run(sp=sp)
        mock_db.add.assert_called_once()

    def test_no_nm_id_skips_silently(self):
        sp = _make_sp(nm_id=None)
        mock_db = self._run(sp=sp)
        mock_db.add.assert_not_called()

    def test_not_found_skips_silently(self):
        sp = _make_sp()
        mock_db = self._run(sp=sp, scraper_side_effect=ScraperError("NOT_FOUND"))
        mock_db.add.assert_not_called()

    def test_sp_not_found_in_db_skips(self):
        db1 = MagicMock()
        db1.query.return_value.join.return_value.filter.return_value.first.return_value = None
        cm = MagicMock()
        cm.__enter__ = lambda s: db1
        cm.__exit__ = MagicMock(return_value=False)

        with patch("app.tasks.wb_content_task.get_db_session", return_value=cm):
            from app.tasks.wb_content_task import collect_wb_content
            collect_wb_content(str(uuid.uuid4()))
            db1.add.assert_not_called()

    def test_image_url_fails_allowlist_no_fetch(self):
        content = ContentData(
            title="Product",
            description="Desc",
            composition=None,
            image_url="https://evil.com/img.jpg",
        )
        sp = _make_sp()
        with (
            patch("app.tasks.wb_content_task.get_db_session", side_effect=self._make_fake_cm(sp)),
            patch("app.tasks.wb_content_task.WildberriesScraper"),
            patch("app.tasks.wb_content_task.asyncio.run", return_value=content),
            patch("app.tasks.wb_content_task.httpx.get") as mock_httpx,
            patch("app.tasks.wb_content_task._get_minio"),
        ):
            from app.tasks.wb_content_task import collect_wb_content
            collect_wb_content(str(sp.id))
            # httpx.get must NOT be called — SSRF guard
            mock_httpx.assert_not_called()

    @staticmethod
    def _make_fake_cm(sp, existing_score=None):
        call_count = [0]

        def fake_cm():
            call_count[0] += 1
            if call_count[0] == 1:
                db = MagicMock()
                db.query.return_value.join.return_value.filter.return_value.first.return_value = sp
            else:
                db = MagicMock()
                db.query.return_value.filter.return_value.first.return_value = existing_score
            cm = MagicMock()
            cm.__enter__ = lambda s: db
            cm.__exit__ = MagicMock(return_value=False)
            return cm

        return fake_cm

    def test_upserts_existing_row(self):
        existing = MagicMock()
        db2 = self._run(existing_score=existing)
        # No new row added when existing found — updated in place
        db2.add.assert_not_called()


# ---------------------------------------------------------------------------
# collect_wb_price
# ---------------------------------------------------------------------------

class TestCollectWbPrice:

    def _run(self, sp=None, price=None, scraper_side_effect=None):
        sp = sp or _make_sp()
        mock_db = MagicMock()
        with (
            patch("app.tasks.wb_price_task.get_db_session") as mock_get_db,
            patch("app.tasks.wb_price_task.WildberriesScraper"),
            patch("app.tasks.wb_price_task.asyncio.run") as mock_run,
        ):
            mock_db.query.return_value.join.return_value.filter.return_value.first.return_value = sp
            mock_get_db.return_value.__enter__ = lambda s: mock_db
            mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

            if scraper_side_effect:
                mock_run.side_effect = scraper_side_effect
            else:
                mock_run.return_value = price or _make_price()

            from app.tasks.wb_price_task import collect_wb_price
            collect_wb_price(str(sp.id))

        return mock_db

    def test_happy_path_inserts_snapshot(self):
        mock_db = self._run()
        mock_db.add.assert_called_once()

    def test_no_nm_id_skips(self):
        sp = _make_sp(nm_id=None)
        mock_db = self._run(sp=sp)
        mock_db.add.assert_not_called()

    def test_not_found_skips(self):
        sp = _make_sp()
        mock_db = self._run(sp=sp, scraper_side_effect=ScraperError("NOT_FOUND"))
        mock_db.add.assert_not_called()

    def test_price_fields_set(self):
        price = _make_price()
        mock_db = self._run(price=price)
        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.price == Decimal("299.00")
        assert added_obj.original_price == Decimal("399.00")
        assert added_obj.discount_pct == Decimal("25.06")
        assert added_obj.promo_label == "Sale!"


# ---------------------------------------------------------------------------
# collect_wb_stock
# ---------------------------------------------------------------------------

class TestCollectWbStock:

    def _run(self, sp=None, stock=None, existing_score=None, scraper_side_effect=None):
        sp = sp or _make_sp()
        mock_db = MagicMock()
        call_count = [0]

        def fake_enter(s):
            call_count[0] += 1
            if call_count[0] == 1:
                mock_db.query.return_value.join.return_value.filter.return_value.first.return_value = sp
            else:
                mock_db.query.return_value.filter.return_value.first.return_value = existing_score
            return mock_db

        with (
            patch("app.tasks.wb_stock_task.get_db_session") as mock_get_db,
            patch("app.tasks.wb_stock_task.WildberriesScraper"),
            patch("app.tasks.wb_stock_task.asyncio.run") as mock_run,
        ):
            mock_get_db.return_value.__enter__ = fake_enter
            mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

            if scraper_side_effect:
                mock_run.side_effect = scraper_side_effect
            else:
                mock_run.return_value = stock or _make_stock()

            from app.tasks.wb_stock_task import collect_wb_stock
            collect_wb_stock(str(sp.id))

        return mock_db

    def test_creates_partial_row_when_no_existing(self):
        mock_db = self._run(existing_score=None)
        mock_db.add.assert_called_once()
        added = mock_db.add.call_args[0][0]
        # Content fields must be None in the partial row
        assert added.collected_title is None
        assert added.collected_description is None
        assert added.in_stock is True
        assert added.warehouse_qty == 15

    def test_updates_existing_row_stock_fields_only(self):
        existing = MagicMock()
        existing.collected_description = "Previous description"
        mock_db = self._run(existing_score=existing)
        # Should update in-place, not add
        mock_db.add.assert_not_called()
        assert existing.in_stock is True
        assert existing.warehouse_qty == 15
        # Content field must not be overwritten
        assert existing.collected_description == "Previous description"

    def test_out_of_stock(self):
        mock_db = self._run(stock=_make_stock(in_stock=False, total_qty=0))
        added = mock_db.add.call_args[0][0]
        assert added.in_stock is False
        assert added.warehouse_qty == 0

    def test_no_nm_id_skips(self):
        sp = _make_sp(nm_id=None)
        mock_db = self._run(sp=sp)
        mock_db.add.assert_not_called()


# ---------------------------------------------------------------------------
# collect_wb_reviews
# ---------------------------------------------------------------------------

class TestCollectWbReviews:

    def _run(self, sp=None, reviews=None, scraper_side_effect=None):
        sp = sp or _make_sp()
        mock_db = MagicMock()
        with (
            patch("app.tasks.wb_reviews_task.get_db_session") as mock_get_db,
            patch("app.tasks.wb_reviews_task.WildberriesScraper"),
            patch("app.tasks.wb_reviews_task.asyncio.run") as mock_run,
            patch("app.tasks.wb_reviews_task.pg_insert") as mock_pg_insert,
        ):
            mock_db.query.return_value.join.return_value.filter.return_value.first.return_value = sp
            mock_get_db.return_value.__enter__ = lambda s: mock_db
            mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

            if scraper_side_effect:
                mock_run.side_effect = scraper_side_effect
            else:
                mock_run.return_value = reviews if reviews is not None else _make_reviews()

            # pg_insert mock chain: pg_insert(Review).values(...).on_conflict_do_nothing(...)
            mock_stmt = MagicMock()
            mock_pg_insert.return_value.values.return_value.on_conflict_do_nothing.return_value = mock_stmt

            from app.tasks.wb_reviews_task import collect_wb_reviews
            collect_wb_reviews(str(sp.id))

            return mock_db, mock_pg_insert

    def test_happy_path_executes_insert_per_review(self):
        mock_db, mock_pg_insert = self._run()
        assert mock_db.execute.call_count == 2

    def test_empty_reviews_no_execute(self):
        mock_db, _ = self._run(reviews=[])
        mock_db.execute.assert_not_called()

    def test_no_nm_id_skips(self):
        sp = _make_sp(nm_id=None)
        mock_db, _ = self._run(sp=sp)
        mock_db.execute.assert_not_called()

    def test_not_found_skips(self):
        sp = _make_sp()
        mock_db, _ = self._run(sp=sp, scraper_side_effect=ScraperError("NOT_FOUND"))
        mock_db.execute.assert_not_called()

    def test_uses_on_conflict_do_nothing(self):
        _, mock_pg_insert = self._run()
        # Verify the ON CONFLICT ... DO NOTHING constraint is referenced
        calls = mock_pg_insert.return_value.values.return_value.on_conflict_do_nothing.call_args_list
        assert len(calls) == 2
        for c in calls:
            assert c.kwargs.get("constraint") == "uq_reviews_sp_ext_id"


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class TestWbOrchestrator:

    def _make_sp_list(self, n=3):
        return [_make_sp() for _ in range(n)]

    def test_content_all_dispatches_3x_per_sp(self):
        sps = self._make_sp_list(3)
        mock_db = MagicMock()
        with (
            patch("app.tasks.wb_orchestrator.get_db_session") as mock_get_db,
            patch("app.tasks.wb_orchestrator._load_wb_sku_platforms", return_value=sps),
            patch("app.tasks.wb_orchestrator.collect_wb_content") as mock_content,
            patch("app.tasks.wb_orchestrator.collect_wb_stock") as mock_stock,
            patch("app.tasks.wb_orchestrator.collect_wb_reviews") as mock_reviews,
        ):
            mock_get_db.return_value.__enter__ = lambda s: mock_db
            mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

            from app.tasks.wb_orchestrator import collect_wb_content_all
            collect_wb_content_all()

            assert mock_content.delay.call_count == 3
            assert mock_stock.delay.call_count == 3
            assert mock_reviews.delay.call_count == 3

    def test_prices_all_dispatches_1x_per_sp(self):
        sps = self._make_sp_list(4)
        mock_db = MagicMock()
        with (
            patch("app.tasks.wb_orchestrator.get_db_session") as mock_get_db,
            patch("app.tasks.wb_orchestrator._load_wb_sku_platforms", return_value=sps),
            patch("app.tasks.wb_orchestrator.collect_wb_price") as mock_price,
        ):
            mock_get_db.return_value.__enter__ = lambda s: mock_db
            mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

            from app.tasks.wb_orchestrator import collect_wb_prices_all
            collect_wb_prices_all()

            assert mock_price.delay.call_count == 4

    def test_empty_platform_list_dispatches_nothing(self):
        mock_db = MagicMock()
        with (
            patch("app.tasks.wb_orchestrator.get_db_session") as mock_get_db,
            patch("app.tasks.wb_orchestrator._load_wb_sku_platforms", return_value=[]),
            patch("app.tasks.wb_orchestrator.collect_wb_content") as mock_content,
        ):
            mock_get_db.return_value.__enter__ = lambda s: mock_db
            mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

            from app.tasks.wb_orchestrator import collect_wb_content_all
            collect_wb_content_all()

            mock_content.delay.assert_not_called()
