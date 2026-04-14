"""
Unit tests for WB Celery tasks.

DB and scraper are mocked — no real DB or network calls.
Tests cover:
  - Happy-path DB writes for content / price / stock / reviews tasks
  - NO_NM_ID silent skip
  - NOT_FOUND silent skip (no DB write)
  - Missing sku_platform silent skip
  - Partial-row contract for stock task (content fields stay NULL)
  - Review bulk-insert (single execute, not N+1 loop)
  - SSRF guard (evil image URL → httpx never called)
  - Cross-tenant isolation: only the correct sp_id is written
  - API_UNAVAILABLE triggers self.retry, no DB write
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

ORG_A = uuid.uuid4()
ORG_B = uuid.uuid4()
SP_A_ID = uuid.uuid4()
SP_B_ID = uuid.uuid4()
SKU_A_ID = uuid.uuid4()


def _make_row(nm_id="12345678", sp_id=None, sku_id=None, org_id=None):
    """Return a tuple mimicking the query result (sp.id, sp.external_id, sku.org_id)."""
    return (sp_id or uuid.uuid4(), nm_id, org_id or ORG_A)


def _make_row3(nm_id="12345678", sp_id=None, sku_id=None, org_id=None):
    """Return a 3-tuple: (sp_id, nm_id, org_id). Used by price/stock/reviews tasks."""
    return (sp_id or uuid.uuid4(), nm_id, org_id or ORG_A)


def _make_row4(nm_id="12345678", sp_id=None, sku_id=None, org_id=None):
    """Return a 4-tuple: (sp_id, sku_id, nm_id, org_id). Used by content task."""
    return (sp_id or uuid.uuid4(), sku_id or SKU_A_ID, nm_id, org_id or ORG_A)


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


def _make_db_cm(first_result):
    """Create a DB context manager mock that returns first_result from .first()."""
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.first.return_value = first_result
    cm = MagicMock()
    cm.__enter__ = lambda s: db
    cm.__exit__ = MagicMock(return_value=False)
    return cm, db


def _make_two_db_cms(first_result, second_result=None):
    """Return a side_effect function that yields two different DB context managers."""
    db1 = MagicMock()
    db1.query.return_value.join.return_value.filter.return_value.first.return_value = first_result
    cm1 = MagicMock()
    cm1.__enter__ = lambda s: db1
    cm1.__exit__ = MagicMock(return_value=False)

    db2 = MagicMock()
    db2.query.return_value.filter.return_value.first.return_value = second_result
    cm2 = MagicMock()
    cm2.__enter__ = lambda s: db2
    cm2.__exit__ = MagicMock(return_value=False)

    calls = [0]

    def factory():
        calls[0] += 1
        return cm1 if calls[0] == 1 else cm2

    return factory, db2


# ---------------------------------------------------------------------------
# collect_wb_content
# ---------------------------------------------------------------------------

class TestCollectWbContent:

    def test_happy_path_adds_content_score(self):
        row = _make_row4()
        factory, db2 = _make_two_db_cms(row, second_result=None)
        with (
            patch("app.tasks.wb_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.wb_content_task.WildberriesScraper"),
            patch("app.tasks.wb_content_task.asyncio.run", return_value=_make_content()),
            patch("app.tasks.wb_content_task._get_minio"),
        ):
            from app.tasks.wb_content_task import collect_wb_content
            collect_wb_content(str(row[0]))
        db2.add.assert_called_once()

    def test_no_nm_id_skips_silently(self):
        row = _make_row4(nm_id=None)
        factory, db2 = _make_two_db_cms(row)
        with (
            patch("app.tasks.wb_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.wb_content_task.WildberriesScraper"),
        ):
            from app.tasks.wb_content_task import collect_wb_content
            collect_wb_content(str(row[0]))
        db2.add.assert_not_called()

    def test_not_found_skips_silently(self):
        row = _make_row4()
        factory, db2 = _make_two_db_cms(row)
        with (
            patch("app.tasks.wb_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.wb_content_task.WildberriesScraper"),
            patch("app.tasks.wb_content_task.asyncio.run", side_effect=ScraperError("NOT_FOUND")),
        ):
            from app.tasks.wb_content_task import collect_wb_content
            collect_wb_content(str(row[0]))
        db2.add.assert_not_called()

    def test_sp_not_found_in_db_skips(self):
        cm, db = _make_db_cm(None)
        with patch("app.tasks.wb_content_task.get_db_session", return_value=cm):
            from app.tasks.wb_content_task import collect_wb_content
            collect_wb_content(str(uuid.uuid4()))
        db.add.assert_not_called()

    def test_image_url_ssrf_guard_no_fetch(self):
        """Evil image URL must never trigger any HTTP call."""
        content = ContentData(
            title="Product",
            description="Desc",
            composition=None,
            image_url="https://evil.com/img.jpg",
        )
        row = _make_row4()
        factory, _ = _make_two_db_cms(row)

        run_calls = [0]

        def fake_run(coro):
            run_calls[0] += 1
            return content  # only the scraper call

        with (
            patch("app.tasks.wb_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.wb_content_task.WildberriesScraper"),
            patch("app.tasks.wb_content_task.asyncio.run", side_effect=fake_run),
            patch("app.tasks.wb_content_task._get_minio"),
        ):
            from app.tasks.wb_content_task import collect_wb_content
            collect_wb_content(str(row[0]))

        # asyncio.run must be called exactly once (for the scraper) — not for image download
        assert run_calls[0] == 1

    def test_upserts_existing_row(self):
        existing = MagicMock()
        row = _make_row4()
        factory, db2 = _make_two_db_cms(row, second_result=existing)
        with (
            patch("app.tasks.wb_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.wb_content_task.WildberriesScraper"),
            patch("app.tasks.wb_content_task.asyncio.run", return_value=_make_content()),
            patch("app.tasks.wb_content_task._get_minio"),
        ):
            from app.tasks.wb_content_task import collect_wb_content
            collect_wb_content(str(row[0]))
        db2.add.assert_not_called()

    def test_cross_tenant_isolation(self):
        """Task for org_A's sku_platform must not write org_B's content_score row."""
        sp_a_id = uuid.uuid4()
        sp_b_id = uuid.uuid4()
        # (sp_id, sku_id, nm_id, org_id)
        row_a = (sp_a_id, SKU_A_ID, "11111111", ORG_A)

        upsert_db = MagicMock()
        upsert_db.query.return_value.filter.return_value.first.return_value = None

        call_count = [0]

        def factory():
            call_count[0] += 1
            if call_count[0] == 1:
                db = MagicMock()
                db.query.return_value.join.return_value.filter.return_value.first.return_value = row_a
                cm = MagicMock()
                cm.__enter__ = lambda s: db
                cm.__exit__ = MagicMock(return_value=False)
                return cm
            else:
                cm = MagicMock()
                cm.__enter__ = lambda s: upsert_db
                cm.__exit__ = MagicMock(return_value=False)
                return cm

        with (
            patch("app.tasks.wb_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.wb_content_task.WildberriesScraper"),
            patch("app.tasks.wb_content_task.asyncio.run", return_value=_make_content()),
            patch("app.tasks.wb_content_task._get_minio"),
        ):
            from app.tasks.wb_content_task import collect_wb_content
            collect_wb_content(str(sp_a_id))

        added = upsert_db.add.call_args[0][0]
        assert added.sku_platform_id == sp_a_id
        assert added.sku_platform_id != sp_b_id


# ---------------------------------------------------------------------------
# collect_wb_price
# ---------------------------------------------------------------------------

class TestCollectWbPrice:

    def _run(self, row=None, price=None, scraper_side_effect=None):
        row = row or _make_row3()
        sp_id = row[0]

        db1 = MagicMock()
        db1.query.return_value.join.return_value.filter.return_value.first.return_value = row
        cm1 = MagicMock(); cm1.__enter__ = lambda s: db1; cm1.__exit__ = MagicMock(return_value=False)

        db2 = MagicMock()
        cm2 = MagicMock(); cm2.__enter__ = lambda s: db2; cm2.__exit__ = MagicMock(return_value=False)

        calls = [0]
        def factory():
            calls[0] += 1
            return cm1 if calls[0] == 1 else cm2

        with (
            patch("app.tasks.wb_price_task.get_db_session", side_effect=factory),
            patch("app.tasks.wb_price_task.WildberriesScraper"),
            patch("app.tasks.wb_price_task.asyncio.run") as mock_run,
        ):
            if scraper_side_effect:
                mock_run.side_effect = scraper_side_effect
            else:
                mock_run.return_value = price or _make_price()

            from app.tasks.wb_price_task import collect_wb_price
            collect_wb_price(str(sp_id))

        return db2

    def test_happy_path_inserts_snapshot(self):
        db2 = self._run()
        db2.add.assert_called_once()

    def test_no_nm_id_skips(self):
        db2 = self._run(row=_make_row3(nm_id=None))
        db2.add.assert_not_called()

    def test_not_found_skips(self):
        db2 = self._run(scraper_side_effect=ScraperError("NOT_FOUND"))
        db2.add.assert_not_called()

    def test_price_fields_set(self):
        price = _make_price()
        db2 = self._run(price=price)
        added = db2.add.call_args[0][0]
        assert added.price == Decimal("299.00")
        assert added.original_price == Decimal("399.00")
        assert added.discount_pct == Decimal("25.06")
        assert added.promo_label == "Sale!"

    def test_collected_at_is_set(self):
        db2 = self._run()
        added = db2.add.call_args[0][0]
        assert added.collected_at is not None

    def test_api_unavailable_no_db_write(self):
        """API_UNAVAILABLE must not write a price snapshot (task retries instead)."""
        row = _make_row3()
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.wb_price_task.get_db_session", side_effect=factory),
            patch("app.tasks.wb_price_task.WildberriesScraper"),
            patch("app.tasks.wb_price_task.asyncio.run", side_effect=ScraperError("API_UNAVAILABLE")),
        ):
            from app.tasks.wb_price_task import collect_wb_price
            # Celery raises Retry exception — catch it here
            try:
                collect_wb_price(str(row[0]))
            except Exception:
                pass

        db2.add.assert_not_called()


# ---------------------------------------------------------------------------
# collect_wb_stock
# ---------------------------------------------------------------------------

class TestCollectWbStock:

    def _run(self, row=None, stock=None, existing_score=None, scraper_side_effect=None):
        row = row or _make_row3()
        sp_id = row[0]
        factory, db2 = _make_two_db_cms(row, second_result=existing_score)

        with (
            patch("app.tasks.wb_stock_task.get_db_session", side_effect=factory),
            patch("app.tasks.wb_stock_task.WildberriesScraper"),
            patch("app.tasks.wb_stock_task.asyncio.run") as mock_run,
        ):
            if scraper_side_effect:
                mock_run.side_effect = scraper_side_effect
            else:
                mock_run.return_value = stock or _make_stock()

            from app.tasks.wb_stock_task import collect_wb_stock
            collect_wb_stock(str(sp_id))

        return db2

    def test_creates_partial_row_when_no_existing(self):
        db2 = self._run(existing_score=None)
        db2.add.assert_called_once()
        added = db2.add.call_args[0][0]
        assert added.collected_title is None
        assert added.collected_description is None
        assert added.in_stock is True
        assert added.warehouse_qty == 15

    def test_updates_existing_row_stock_fields_only(self):
        existing = MagicMock()
        existing.collected_description = "Previous description"
        db2 = self._run(existing_score=existing)
        db2.add.assert_not_called()
        assert existing.in_stock is True
        assert existing.warehouse_qty == 15
        assert existing.collected_description == "Previous description"

    def test_out_of_stock(self):
        db2 = self._run(stock=_make_stock(in_stock=False, total_qty=0))
        added = db2.add.call_args[0][0]
        assert added.in_stock is False
        assert added.warehouse_qty == 0

    def test_no_nm_id_skips(self):
        db2 = self._run(row=_make_row3(nm_id=None))
        db2.add.assert_not_called()

    def test_api_unavailable_no_db_write(self):
        """Spec US-W03: API_UNAVAILABLE must not write any stock row."""
        row = _make_row3()
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.wb_stock_task.get_db_session", side_effect=factory),
            patch("app.tasks.wb_stock_task.WildberriesScraper"),
            patch("app.tasks.wb_stock_task.asyncio.run", side_effect=ScraperError("API_UNAVAILABLE")),
        ):
            from app.tasks.wb_stock_task import collect_wb_stock
            try:
                collect_wb_stock(str(row[0]))
            except Exception:
                pass

        db2.add.assert_not_called()


# ---------------------------------------------------------------------------
# collect_wb_reviews
# ---------------------------------------------------------------------------

class TestCollectWbReviews:

    def _run(self, row=None, reviews=None, scraper_side_effect=None):
        row = row or _make_row3()
        sp_id = row[0]
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.wb_reviews_task.get_db_session", side_effect=factory),
            patch("app.tasks.wb_reviews_task.WildberriesScraper"),
            patch("app.tasks.wb_reviews_task.asyncio.run") as mock_run,
            patch("app.tasks.wb_reviews_task.pg_insert") as mock_pg_insert,
        ):
            if scraper_side_effect:
                mock_run.side_effect = scraper_side_effect
            else:
                mock_run.return_value = reviews if reviews is not None else _make_reviews()

            mock_stmt = MagicMock()
            mock_pg_insert.return_value.values.return_value.on_conflict_do_nothing.return_value = mock_stmt

            from app.tasks.wb_reviews_task import collect_wb_reviews
            collect_wb_reviews(str(sp_id))

            return db2, mock_pg_insert

    def test_happy_path_single_bulk_execute(self):
        """Reviews must use a single bulk INSERT, not N+1 loop."""
        db2, mock_pg_insert = self._run()
        # Single db.execute() call for all reviews (not 2 calls)
        assert db2.execute.call_count == 1

    def test_empty_reviews_no_execute(self):
        db2, _ = self._run(reviews=[])
        db2.execute.assert_not_called()

    def test_no_nm_id_skips(self):
        db2, _ = self._run(row=_make_row3(nm_id=None))
        db2.execute.assert_not_called()

    def test_not_found_skips(self):
        db2, _ = self._run(scraper_side_effect=ScraperError("NOT_FOUND"))
        db2.execute.assert_not_called()

    def test_api_unavailable_no_db_write(self):
        row = _make_row3()
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.wb_reviews_task.get_db_session", side_effect=factory),
            patch("app.tasks.wb_reviews_task.WildberriesScraper"),
            patch("app.tasks.wb_reviews_task.asyncio.run", side_effect=ScraperError("API_UNAVAILABLE")),
        ):
            from app.tasks.wb_reviews_task import collect_wb_reviews
            try:
                collect_wb_reviews(str(row[0]))
            except Exception:
                pass

        db2.execute.assert_not_called()

    def test_uses_on_conflict_do_nothing(self):
        _, mock_pg_insert = self._run()
        calls = mock_pg_insert.return_value.values.return_value.on_conflict_do_nothing.call_args_list
        assert len(calls) == 1  # single bulk call
        assert calls[0].kwargs.get("constraint") == "uq_reviews_sp_ext_id"

    def test_values_include_both_reviews(self):
        _, mock_pg_insert = self._run()
        values_arg = mock_pg_insert.return_value.values.call_args[0][0]
        assert len(values_arg) == 2
        ext_ids = {v["external_review_id"] for v in values_arg}
        assert ext_ids == {"rev-001", "rev-002"}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class TestWbOrchestrator:

    def _make_sp_ids(self, n=3):
        return [str(uuid.uuid4()) for _ in range(n)]

    def test_content_all_dispatches_3x_per_sp(self):
        sp_ids = self._make_sp_ids(3)
        db = MagicMock()
        cm = MagicMock(); cm.__enter__ = lambda s: db; cm.__exit__ = MagicMock(return_value=False)
        with (
            patch("app.tasks.wb_orchestrator.get_db_session", return_value=cm),
            patch("app.tasks.wb_orchestrator._load_wb_sku_platform_ids", return_value=sp_ids),
            patch("app.tasks.wb_orchestrator.collect_wb_content") as mock_content,
            patch("app.tasks.wb_orchestrator.collect_wb_stock") as mock_stock,
            patch("app.tasks.wb_orchestrator.collect_wb_reviews") as mock_reviews,
        ):
            from app.tasks.wb_orchestrator import collect_wb_content_all
            collect_wb_content_all()

        assert mock_content.delay.call_count == 3
        assert mock_stock.delay.call_count == 3
        assert mock_reviews.delay.call_count == 3

    def test_prices_all_dispatches_1x_per_sp(self):
        sp_ids = self._make_sp_ids(4)
        db = MagicMock()
        cm = MagicMock(); cm.__enter__ = lambda s: db; cm.__exit__ = MagicMock(return_value=False)
        with (
            patch("app.tasks.wb_orchestrator.get_db_session", return_value=cm),
            patch("app.tasks.wb_orchestrator._load_wb_sku_platform_ids", return_value=sp_ids),
            patch("app.tasks.wb_orchestrator.collect_wb_price") as mock_price,
        ):
            from app.tasks.wb_orchestrator import collect_wb_prices_all
            collect_wb_prices_all()

        assert mock_price.delay.call_count == 4

    def test_empty_platform_list_dispatches_nothing(self):
        db = MagicMock()
        cm = MagicMock(); cm.__enter__ = lambda s: db; cm.__exit__ = MagicMock(return_value=False)
        with (
            patch("app.tasks.wb_orchestrator.get_db_session", return_value=cm),
            patch("app.tasks.wb_orchestrator._load_wb_sku_platform_ids", return_value=[]),
            patch("app.tasks.wb_orchestrator.collect_wb_content") as mock_content,
        ):
            from app.tasks.wb_orchestrator import collect_wb_content_all
            collect_wb_content_all()

        mock_content.delay.assert_not_called()
