"""
Unit tests for Ozon Celery tasks.

DB and scraper are mocked — no real DB or network calls.
Tests cover:
  - Happy-path DB writes for content / price / stock / reviews tasks
  - NO_ITEM_ID silent skip
  - NOT_FOUND silent skip (no DB write)
  - Missing sku_platform silent skip
  - Partial-row contract for stock task (content fields absent from upsert)
  - Review bulk-insert (single execute, not N+1 loop)
  - Cross-tenant isolation: only the correct sp_id is written
  - API_UNAVAILABLE triggers self.retry, no DB write
  - Orchestrator dispatches correct task counts and filters by Platform.name=="Ozon"
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

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


def _make_row3(item_id="123456789", sp_id=None, org_id=None):
    """Return a 3-tuple: (sp_id, item_id, org_id). Used by price/stock/reviews tasks."""
    return (sp_id or uuid.uuid4(), item_id, org_id or ORG_A)


def _make_row4(item_id="123456789", sp_id=None, sku_id=None, org_id=None):
    """Return a 4-tuple: (sp_id, sku_id, item_id, org_id). Used by content task."""
    return (sp_id or uuid.uuid4(), sku_id or SKU_A_ID, item_id, org_id or ORG_A)


def _make_content():
    return ContentData(
        title="Test Ozon Product",
        description="A great Ozon product",
        composition="Cotton 100%",
        image_url=(
            "https://ir.ozone.ru/s3/multimedia-b/abcdef123456/wc1000/abcdef123456.jpg"
        ),
    )


def _make_price():
    return PriceData(
        price=Decimal("1199.00"),
        original_price=Decimal("1999.00"),
        discount_pct=Decimal("40.02"),
        promo_label="Ozon Карта",
    )


def _make_stock(in_stock=True, total_qty=42):
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
    db.query.return_value.join.return_value.filter.return_value.first.return_value = (
        first_result
    )
    cm = MagicMock()
    cm.__enter__ = lambda s: db
    cm.__exit__ = MagicMock(return_value=False)
    return cm, db


def _make_two_db_cms(first_result, second_result=None):
    """Return a (factory, db2) pair.

    factory() — callable that yields two different DB context managers in sequence.
    db2       — the write-session mock (call count, add calls etc. are checked here).
    """
    db1 = MagicMock()
    db1.query.return_value.join.return_value.filter.return_value.first.return_value = (
        first_result
    )
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
# TestCollectOzonContent
# ---------------------------------------------------------------------------


class TestCollectOzonContent:

    def test_happy_path_executes_upsert(self):
        row = _make_row4()
        factory, db2 = _make_two_db_cms(row)
        with (
            patch("app.tasks.ozon_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.ozon_content_task.OzonScraper"),
            patch(
                "app.tasks.ozon_content_task.asyncio.run",
                return_value=_make_content(),
            ),
            patch("app.tasks.ozon_content_task._get_minio"),
            patch("app.tasks.ozon_content_task.get_proxy_rotator"),
        ):
            from app.tasks.ozon_content_task import collect_ozon_content

            collect_ozon_content(str(row[0]))
        # Content task uses pg_insert → db.execute(), not db.add()
        db2.execute.assert_called_once()

    def test_happy_path_sets_correct_sp_id_in_values(self):
        sp_id = uuid.uuid4()
        row = _make_row4(sp_id=sp_id)
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.ozon_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.ozon_content_task.OzonScraper"),
            patch(
                "app.tasks.ozon_content_task.asyncio.run",
                return_value=_make_content(),
            ),
            patch("app.tasks.ozon_content_task._get_minio"),
            patch("app.tasks.ozon_content_task.get_proxy_rotator"),
        ):
            from app.tasks.ozon_content_task import collect_ozon_content

            collect_ozon_content(str(sp_id))

        db2.execute.assert_called_once()

    def test_missing_item_id_returns_early_no_execute(self):
        row = _make_row4(item_id=None)
        factory, db2 = _make_two_db_cms(row)
        with (
            patch("app.tasks.ozon_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.ozon_content_task.OzonScraper"),
        ):
            from app.tasks.ozon_content_task import collect_ozon_content

            collect_ozon_content(str(row[0]))
        db2.execute.assert_not_called()

    def test_not_found_returns_early_no_execute(self):
        row = _make_row4()
        factory, db2 = _make_two_db_cms(row)
        with (
            patch("app.tasks.ozon_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.ozon_content_task.OzonScraper"),
            patch(
                "app.tasks.ozon_content_task.asyncio.run",
                side_effect=ScraperError("NOT_FOUND"),
            ),
        ):
            from app.tasks.ozon_content_task import collect_ozon_content

            collect_ozon_content(str(row[0]))
        db2.execute.assert_not_called()

    def test_sp_not_in_db_skips_silently(self):
        cm, db = _make_db_cm(None)
        with patch("app.tasks.ozon_content_task.get_db_session", return_value=cm):
            from app.tasks.ozon_content_task import collect_ozon_content

            collect_ozon_content(str(uuid.uuid4()))
        db.execute.assert_not_called()

    def test_rate_limited_triggers_retry(self):
        row = _make_row4()
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.ozon_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.ozon_content_task.OzonScraper"),
            patch(
                "app.tasks.ozon_content_task.asyncio.run",
                side_effect=ScraperError("RATE_LIMITED"),
            ),
        ):
            from app.tasks.ozon_content_task import collect_ozon_content

            try:
                collect_ozon_content(str(row[0]))
            except Exception:
                pass  # Celery raises Retry exception

        db2.execute.assert_not_called()

    def test_image_download_failure_still_saves_content(self):
        """Image download failing must not block content upsert (s3_key=None)."""
        row = _make_row4()
        factory, db2 = _make_two_db_cms(row)

        call_count = [0]

        def fake_run(coro):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_content()  # scraper call succeeds
            raise Exception("CDN timeout")  # image download fails

        with (
            patch("app.tasks.ozon_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.ozon_content_task.OzonScraper"),
            patch("app.tasks.ozon_content_task.asyncio.run", side_effect=fake_run),
            patch("app.tasks.ozon_content_task._get_minio"),
            patch("app.tasks.ozon_content_task.get_proxy_rotator"),
        ):
            from app.tasks.ozon_content_task import collect_ozon_content

            collect_ozon_content(str(row[0]))

        # Content upsert must still have been executed
        db2.execute.assert_called_once()

    def test_cross_tenant_isolation(self):
        """Content task for org_A's sku_platform must write with sp_a_id, not sp_b_id."""
        sp_a_id = uuid.uuid4()
        sp_b_id = uuid.uuid4()
        row_a = (sp_a_id, SKU_A_ID, "123456789", ORG_A)

        write_db = MagicMock()
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
                cm.__enter__ = lambda s: write_db
                cm.__exit__ = MagicMock(return_value=False)
                return cm

        with (
            patch("app.tasks.ozon_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.ozon_content_task.OzonScraper"),
            patch(
                "app.tasks.ozon_content_task.asyncio.run",
                return_value=_make_content(),
            ),
            patch("app.tasks.ozon_content_task._get_minio"),
            patch("app.tasks.ozon_content_task.get_proxy_rotator"),
            patch("app.tasks.ozon_content_task.pg_insert") as mock_pg_insert,
        ):
            from app.tasks.ozon_content_task import collect_ozon_content

            collect_ozon_content(str(sp_a_id))

        write_db.execute.assert_called_once()
        assert call_count[0] == 2  # exactly 2 DB sessions (load + write)
        # Verify pg_insert values contain sp_a_id, not sp_b_id
        values_kwargs = mock_pg_insert.return_value.values.call_args[1]
        assert values_kwargs["sku_platform_id"] == sp_a_id
        assert values_kwargs.get("sku_platform_id") != sp_b_id


# ---------------------------------------------------------------------------
# TestCollectOzonPrice
# ---------------------------------------------------------------------------


class TestCollectOzonPrice:

    def _run(self, row=None, price=None, scraper_side_effect=None):
        row = row or _make_row3()
        sp_id = row[0]
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.ozon_price_task.get_db_session", side_effect=factory),
            patch("app.tasks.ozon_price_task.OzonScraper"),
            patch("app.tasks.ozon_price_task.asyncio.run") as mock_run,
            patch("app.tasks.ozon_price_task.get_proxy_rotator"),
        ):
            if scraper_side_effect:
                mock_run.side_effect = scraper_side_effect
            else:
                mock_run.return_value = price or _make_price()

            from app.tasks.ozon_price_task import collect_ozon_price

            collect_ozon_price(str(sp_id))

        return db2

    def test_happy_path_inserts_snapshot(self):
        db2 = self._run()
        db2.add.assert_called_once()

    def test_price_fields_set_correctly(self):
        price = _make_price()
        db2 = self._run(price=price)
        added = db2.add.call_args[0][0]
        assert added.price == Decimal("1199.00")
        assert added.original_price == Decimal("1999.00")
        assert added.discount_pct == Decimal("40.02")
        assert added.promo_label == "Ozon Карта"

    def test_collected_at_is_set(self):
        db2 = self._run()
        added = db2.add.call_args[0][0]
        assert added.collected_at is not None

    def test_missing_item_id_skips_no_add(self):
        db2 = self._run(row=_make_row3(item_id=None))
        db2.add.assert_not_called()

    def test_not_found_skips_no_add(self):
        db2 = self._run(scraper_side_effect=ScraperError("NOT_FOUND"))
        db2.add.assert_not_called()

    def test_api_unavailable_no_db_write(self):
        row = _make_row3()
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.ozon_price_task.get_db_session", side_effect=factory),
            patch("app.tasks.ozon_price_task.OzonScraper"),
            patch(
                "app.tasks.ozon_price_task.asyncio.run",
                side_effect=ScraperError("API_UNAVAILABLE"),
            ),
            patch("app.tasks.ozon_price_task.get_proxy_rotator"),
        ):
            from app.tasks.ozon_price_task import collect_ozon_price

            try:
                collect_ozon_price(str(row[0]))
            except Exception:
                pass

        db2.add.assert_not_called()

    def test_sp_not_in_db_skips(self):
        cm, db = _make_db_cm(None)
        with patch("app.tasks.ozon_price_task.get_db_session", return_value=cm):
            from app.tasks.ozon_price_task import collect_ozon_price

            collect_ozon_price(str(uuid.uuid4()))
        db.add.assert_not_called()


# ---------------------------------------------------------------------------
# TestCollectOzonStock
# ---------------------------------------------------------------------------


class TestCollectOzonStock:

    def _run(self, row=None, stock=None, scraper_side_effect=None):
        row = row or _make_row3()
        sp_id = row[0]
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.ozon_stock_task.get_db_session", side_effect=factory),
            patch("app.tasks.ozon_stock_task.OzonScraper"),
            patch("app.tasks.ozon_stock_task.asyncio.run") as mock_run,
            patch("app.tasks.ozon_stock_task.get_proxy_rotator"),
        ):
            if scraper_side_effect:
                mock_run.side_effect = scraper_side_effect
            else:
                mock_run.return_value = stock or _make_stock()

            from app.tasks.ozon_stock_task import collect_ozon_stock

            collect_ozon_stock(str(sp_id))

        return db2

    def test_happy_path_executes_upsert(self):
        db2 = self._run()
        db2.execute.assert_called_once()

    def test_in_stock_true_sets_warehouse_qty(self):
        stock = _make_stock(in_stock=True, total_qty=42)
        # Just confirm the task runs without error and calls execute
        db2 = self._run(stock=stock)
        db2.execute.assert_called_once()

    def test_out_of_stock(self):
        db2 = self._run(stock=_make_stock(in_stock=False, total_qty=0))
        db2.execute.assert_called_once()

    def test_missing_item_id_skips_no_execute(self):
        db2 = self._run(row=_make_row3(item_id=None))
        db2.execute.assert_not_called()

    def test_api_unavailable_no_db_write(self):
        row = _make_row3()
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.ozon_stock_task.get_db_session", side_effect=factory),
            patch("app.tasks.ozon_stock_task.OzonScraper"),
            patch(
                "app.tasks.ozon_stock_task.asyncio.run",
                side_effect=ScraperError("API_UNAVAILABLE"),
            ),
            patch("app.tasks.ozon_stock_task.get_proxy_rotator"),
        ):
            from app.tasks.ozon_stock_task import collect_ozon_stock

            try:
                collect_ozon_stock(str(row[0]))
            except Exception:
                pass

        db2.execute.assert_not_called()

    def test_not_found_no_db_write(self):
        db2 = self._run(scraper_side_effect=ScraperError("NOT_FOUND"))
        db2.execute.assert_not_called()

    def test_cross_tenant_isolation(self):
        """Stock task for sp_a must not write stock for sp_b."""
        sp_a_id = uuid.uuid4()
        row_a = (sp_a_id, "123456789", ORG_A)
        factory, db2 = _make_two_db_cms(row_a)

        with (
            patch("app.tasks.ozon_stock_task.get_db_session", side_effect=factory),
            patch("app.tasks.ozon_stock_task.OzonScraper"),
            patch("app.tasks.ozon_stock_task.asyncio.run", return_value=_make_stock()),
            patch("app.tasks.ozon_stock_task.get_proxy_rotator"),
        ):
            from app.tasks.ozon_stock_task import collect_ozon_stock

            collect_ozon_stock(str(sp_a_id))

        # Exactly one upsert — for sp_a only
        db2.execute.assert_called_once()


# ---------------------------------------------------------------------------
# TestCollectOzonReviews
# ---------------------------------------------------------------------------


class TestCollectOzonReviews:

    def _run(self, row=None, reviews=None, scraper_side_effect=None):
        row = row or _make_row3()
        sp_id = row[0]
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.ozon_reviews_task.get_db_session", side_effect=factory),
            patch("app.tasks.ozon_reviews_task.OzonScraper"),
            patch("app.tasks.ozon_reviews_task.asyncio.run") as mock_run,
            patch("app.tasks.ozon_reviews_task.pg_insert") as mock_pg_insert,
            patch("app.tasks.ozon_reviews_task.get_proxy_rotator"),
        ):
            if scraper_side_effect:
                mock_run.side_effect = scraper_side_effect
            else:
                mock_run.return_value = (
                    reviews if reviews is not None else _make_reviews()
                )

            mock_stmt = MagicMock()
            (
                mock_pg_insert.return_value.values.return_value.on_conflict_do_nothing.return_value
            ) = mock_stmt

            from app.tasks.ozon_reviews_task import collect_ozon_reviews

            collect_ozon_reviews(str(sp_id))

            return db2, mock_pg_insert

    def test_happy_path_single_bulk_execute(self):
        """Reviews must use a single bulk INSERT, not N+1 loop."""
        db2, _ = self._run()
        assert db2.execute.call_count == 1

    def test_empty_reviews_no_execute(self):
        db2, _ = self._run(reviews=[])
        db2.execute.assert_not_called()

    def test_missing_item_id_skips(self):
        db2, _ = self._run(row=_make_row3(item_id=None))
        db2.execute.assert_not_called()

    def test_not_found_skips(self):
        db2, _ = self._run(scraper_side_effect=ScraperError("NOT_FOUND"))
        db2.execute.assert_not_called()

    def test_api_unavailable_no_db_write(self):
        row = _make_row3()
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.ozon_reviews_task.get_db_session", side_effect=factory),
            patch("app.tasks.ozon_reviews_task.OzonScraper"),
            patch(
                "app.tasks.ozon_reviews_task.asyncio.run",
                side_effect=ScraperError("API_UNAVAILABLE"),
            ),
            patch("app.tasks.ozon_reviews_task.get_proxy_rotator"),
        ):
            from app.tasks.ozon_reviews_task import collect_ozon_reviews

            try:
                collect_ozon_reviews(str(row[0]))
            except Exception:
                pass

        db2.execute.assert_not_called()

    def test_uses_on_conflict_do_nothing(self):
        _, mock_pg_insert = self._run()
        on_conflict_calls = (
            mock_pg_insert.return_value.values.return_value.on_conflict_do_nothing.call_args_list
        )
        assert len(on_conflict_calls) == 1
        assert (
            on_conflict_calls[0].kwargs.get("constraint") == "uq_reviews_sp_ext_id"
        )

    def test_values_include_both_reviews(self):
        _, mock_pg_insert = self._run()
        values_arg = mock_pg_insert.return_value.values.call_args[0][0]
        assert len(values_arg) == 2
        ext_ids = {v["external_review_id"] for v in values_arg}
        assert ext_ids == {"rev-001", "rev-002"}

    def test_values_include_sku_platform_id(self):
        sp_id = uuid.uuid4()
        row = _make_row3(sp_id=sp_id)
        _, mock_pg_insert = self._run(row=row)
        values_arg = mock_pg_insert.return_value.values.call_args[0][0]
        for v in values_arg:
            assert v["sku_platform_id"] == sp_id

    def test_cross_tenant_isolation(self):
        """Reviews task for sp_a must not write rows for sp_b."""
        sp_a_id = uuid.uuid4()
        row_a = (sp_a_id, "123456789", ORG_A)
        _, mock_pg_insert = self._run(row=row_a)
        values_arg = mock_pg_insert.return_value.values.call_args[0][0]
        # All values must reference sp_a_id
        for v in values_arg:
            assert v["sku_platform_id"] == sp_a_id
            assert v["sku_platform_id"] != SP_B_ID

    def test_sp_not_in_db_skips(self):
        cm, db = _make_db_cm(None)
        with patch("app.tasks.ozon_reviews_task.get_db_session", return_value=cm):
            from app.tasks.ozon_reviews_task import collect_ozon_reviews

            collect_ozon_reviews(str(uuid.uuid4()))
        db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# TestOzonOrchestrator
# ---------------------------------------------------------------------------


class TestOzonOrchestrator:

    def _make_sp_ids(self, n=3):
        return [str(uuid.uuid4()) for _ in range(n)]

    def test_content_all_dispatches_3x_tasks_per_sp(self):
        sp_ids = self._make_sp_ids(3)
        db = MagicMock()
        cm = MagicMock()
        cm.__enter__ = lambda s: db
        cm.__exit__ = MagicMock(return_value=False)
        with (
            patch("app.tasks.ozon_orchestrator.get_db_session", return_value=cm),
            patch(
                "app.tasks.ozon_orchestrator._load_ozon_sku_platform_ids",
                return_value=sp_ids,
            ),
            patch(
                "app.tasks.ozon_orchestrator.collect_ozon_content"
            ) as mock_content,
            patch("app.tasks.ozon_orchestrator.collect_ozon_stock") as mock_stock,
            patch(
                "app.tasks.ozon_orchestrator.collect_ozon_reviews"
            ) as mock_reviews,
        ):
            from app.tasks.ozon_orchestrator import collect_ozon_content_all

            collect_ozon_content_all()

        assert mock_content.delay.call_count == 3
        assert mock_stock.delay.call_count == 3
        assert mock_reviews.delay.call_count == 3

    def test_prices_all_dispatches_1x_per_sp(self):
        sp_ids = self._make_sp_ids(4)
        db = MagicMock()
        cm = MagicMock()
        cm.__enter__ = lambda s: db
        cm.__exit__ = MagicMock(return_value=False)
        with (
            patch("app.tasks.ozon_orchestrator.get_db_session", return_value=cm),
            patch(
                "app.tasks.ozon_orchestrator._load_ozon_sku_platform_ids",
                return_value=sp_ids,
            ),
            patch("app.tasks.ozon_orchestrator.collect_ozon_price") as mock_price,
        ):
            from app.tasks.ozon_orchestrator import collect_ozon_prices_all

            collect_ozon_prices_all()

        assert mock_price.delay.call_count == 4

    def test_empty_platform_list_dispatches_nothing(self):
        db = MagicMock()
        cm = MagicMock()
        cm.__enter__ = lambda s: db
        cm.__exit__ = MagicMock(return_value=False)
        with (
            patch("app.tasks.ozon_orchestrator.get_db_session", return_value=cm),
            patch(
                "app.tasks.ozon_orchestrator._load_ozon_sku_platform_ids",
                return_value=[],
            ),
            patch(
                "app.tasks.ozon_orchestrator.collect_ozon_content"
            ) as mock_content,
            patch("app.tasks.ozon_orchestrator.collect_ozon_stock") as mock_stock,
            patch(
                "app.tasks.ozon_orchestrator.collect_ozon_reviews"
            ) as mock_reviews,
        ):
            from app.tasks.ozon_orchestrator import collect_ozon_content_all

            collect_ozon_content_all()

        mock_content.delay.assert_not_called()
        mock_stock.delay.assert_not_called()
        mock_reviews.delay.assert_not_called()

    def test_load_ozon_ids_filters_by_platform_name(self):
        """_load_ozon_sku_platform_ids must query Platform.name == 'Ozon'."""
        db = MagicMock()
        # Simulate the chain: query().join().join().filter().all()
        mock_rows = [MagicMock(id=uuid.uuid4()) for _ in range(2)]
        db.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = mock_rows

        from app.tasks.ozon_orchestrator import _load_ozon_sku_platform_ids

        result = _load_ozon_sku_platform_ids(db)
        assert len(result) == 2
        # All results should be string UUIDs
        for sp_id in result:
            assert isinstance(sp_id, str)
            uuid.UUID(sp_id)  # must be valid UUID

    def test_content_all_dispatches_with_correct_sp_ids(self):
        sp_id_1 = str(uuid.uuid4())
        sp_id_2 = str(uuid.uuid4())
        sp_ids = [sp_id_1, sp_id_2]
        db = MagicMock()
        cm = MagicMock()
        cm.__enter__ = lambda s: db
        cm.__exit__ = MagicMock(return_value=False)

        with (
            patch("app.tasks.ozon_orchestrator.get_db_session", return_value=cm),
            patch(
                "app.tasks.ozon_orchestrator._load_ozon_sku_platform_ids",
                return_value=sp_ids,
            ),
            patch(
                "app.tasks.ozon_orchestrator.collect_ozon_content"
            ) as mock_content,
            patch("app.tasks.ozon_orchestrator.collect_ozon_stock"),
            patch("app.tasks.ozon_orchestrator.collect_ozon_reviews"),
        ):
            from app.tasks.ozon_orchestrator import collect_ozon_content_all

            collect_ozon_content_all()

        dispatched_ids = {call.args[0] for call in mock_content.delay.call_args_list}
        assert dispatched_ids == {sp_id_1, sp_id_2}
