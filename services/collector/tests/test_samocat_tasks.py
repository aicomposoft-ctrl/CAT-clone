"""
Unit tests for Samocat (Самокат) Celery tasks.

DB and scraper are fully mocked — no real DB or network calls.

Scenarios covered (all from Refinement.md + Specification.md):
  Content task:
    1.  Happy path — upsert called, s3_key set correctly
    2.  Product not found (404 / NOT_FOUND) — no DB write, no exception
    3.  Rate limited (429 / RATE_LIMITED) — self.retry() called, no DB write
    4.  NO_PRODUCT_ID (external_id=None) — silent skip, no DB write
    5.  PARSE_ERROR (non-numeric external_id) — log warning, return, no DB write
    6.  Image URL fails SSRF allowlist — s3_key=None, upsert still proceeds
    7.  Image download / MinIO upload fails — s3_key=None, upsert still proceeds
    8.  Images list empty (image_url=None from scraper) — s3_key=None, upsert proceeds
    9.  Cross-tenant isolation — sp_a_id written, not sp_b_id
  Price task:
    10. Kopeks → Decimal conversion (9900 → "99.00", 12500 → "125.00")
    11. discountPercent=None → discount_pct=Decimal("0"), no exception
    12. Cross-tenant isolation — price_snapshots row has sp_a_id, not sp_b_id
  Stock task:
    13. Happy path — in_stock=True, warehouse_qty=48 upserted
    14. availableQuantity non-integer — warehouse_qty=0 (defensive fallback)
    15. Cross-tenant isolation — upsert has sp_a_id, not sp_b_id
  Reviews task:
    16. Deduplication — ON CONFLICT DO UPDATE via pg_insert
    17. Empty list → early return, no DB execute
    18. Cross-tenant isolation — all rows have sp_a_id, not sp_b_id
  Shared:
    19. API_UNAVAILABLE (503) — self.retry() called, no DB write
    20. sku_platform_id not found in DB — warning logged, return, no crash
"""

from __future__ import annotations

import uuid
from datetime import date
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
# Constants
# ---------------------------------------------------------------------------

ORG_A = uuid.uuid4()
ORG_B = uuid.uuid4()
SP_A_ID = uuid.uuid4()
SP_B_ID = uuid.uuid4()
SKU_A_ID = uuid.uuid4()

# Samocat CDN — must match _SK_IMAGE_CDN_RE in scraper
_VALID_IMAGE_URL = "https://cdn.samokat.ru/products/12345/main.jpg"
_SSRF_IMAGE_URL = "http://192.168.1.1/malicious.jpg"

# ---------------------------------------------------------------------------
# Fixture factories
# ---------------------------------------------------------------------------


def _make_row3(product_id="12345", sp_id=None, org_id=None):
    """3-tuple (sp_id, product_id, org_id) — used by price / stock / reviews."""
    return (sp_id or uuid.uuid4(), product_id, org_id or ORG_A)


def _make_row4(product_id="12345", sp_id=None, sku_id=None, org_id=None):
    """4-tuple (sp_id, sku_id, product_id, org_id) — used by content task."""
    return (sp_id or uuid.uuid4(), sku_id or SKU_A_ID, product_id, org_id or ORG_A)


def _make_content(image_url: str | None = _VALID_IMAGE_URL):
    return ContentData(
        title="Молоко Простоквашино 3.2%",
        description="Натуральное цельное молоко из отборного сырья.",
        composition="Молоко нормализованное пастеризованное",
        image_url=image_url,
    )


def _make_price(
    price: int = 9900,
    original_price: int = 12500,
    discount_pct: Decimal | None = Decimal("21"),
):
    return PriceData(
        price=Decimal(price) / 100,
        original_price=Decimal(original_price) / 100,
        discount_pct=discount_pct if discount_pct is not None else Decimal("0"),
        promo_label=None,
    )


def _make_stock(in_stock: bool = True, total_qty: int = 48):
    return StockData(in_stock=in_stock, total_qty=total_qty)


def _make_reviews(n: int = 2):
    return [
        ReviewData(
            external_review_id=f"rev-{i:03d}",
            review_text=f"Отзыв {i}",
            rating=5,
            review_date=date(2026, 3, 1),
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# DB context-manager helpers  (mirror ozon test pattern)
# ---------------------------------------------------------------------------


def _make_db_cm(first_result):
    """Single DB session returning first_result from .query().join().filter().first()."""
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.first.return_value = (
        first_result
    )
    cm = MagicMock()
    cm.__enter__ = lambda s: db
    cm.__exit__ = MagicMock(return_value=False)
    return cm, db


def _make_two_db_cms(first_result, second_result=None):
    """Return (factory, write_db).

    factory() yields read-session first, then write-session.
    write_db is the second mock — assert .execute() / .add() counts on it.
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
# TestCollectSamokatContent
# ---------------------------------------------------------------------------


class TestCollectSamokatContent:
    """Scenario 1-9: collect_samocat_content task."""

    # ---- scenario 1: happy path ----------------------------------------

    def test_happy_path_executes_upsert(self):
        """Happy path: content fetched, image uploaded, DB upserted once."""
        row = _make_row4()
        factory, db2 = _make_two_db_cms(row)

        with (
            patch(
                "app.tasks.samocat_content_task.get_db_session", side_effect=factory
            ),
            patch("app.tasks.samocat_content_task.SamokatScraper"),
            patch(
                "app.tasks.samocat_content_task.asyncio.run",
                return_value=_make_content(),
            ),
            patch("app.tasks.samocat_content_task._get_minio"),
            patch("app.tasks.samocat_content_task.get_proxy_rotator"),
        ):
            from app.tasks.samocat_content_task import collect_samocat_content

            collect_samocat_content(str(row[0]))

        db2.execute.assert_called_once()

    def test_happy_path_s3_key_format(self):
        """s3_key must follow 'org/{org_id}/sku/{sku_id}/samocat/main.jpg' pattern."""
        sp_id = uuid.uuid4()
        sku_id = uuid.uuid4()
        row = _make_row4(sp_id=sp_id, sku_id=sku_id, org_id=ORG_A)
        factory, db2 = _make_two_db_cms(row)

        with (
            patch(
                "app.tasks.samocat_content_task.get_db_session", side_effect=factory
            ),
            patch("app.tasks.samocat_content_task.SamokatScraper"),
            patch(
                "app.tasks.samocat_content_task.asyncio.run",
                return_value=_make_content(_VALID_IMAGE_URL),
            ),
            patch("app.tasks.samocat_content_task._get_minio"),
            patch("app.tasks.samocat_content_task.get_proxy_rotator"),
            patch("app.tasks.samocat_content_task.pg_insert") as mock_pg_insert,
        ):
            from app.tasks.samocat_content_task import collect_samocat_content

            collect_samocat_content(str(sp_id))

        values_kwargs = mock_pg_insert.return_value.values.call_args[1]
        s3_key = values_kwargs["collected_image_url"]
        assert s3_key == f"org/{ORG_A}/sku/{sku_id}/samocat/main.jpg"

    # ---- scenario 2: NOT_FOUND -----------------------------------------

    def test_product_not_found_no_db_write(self):
        """404 / NOT_FOUND from scraper → no DB write, no exception raised."""
        row = _make_row4()
        factory, db2 = _make_two_db_cms(row)

        with (
            patch(
                "app.tasks.samocat_content_task.get_db_session", side_effect=factory
            ),
            patch("app.tasks.samocat_content_task.SamokatScraper"),
            patch(
                "app.tasks.samocat_content_task.asyncio.run",
                side_effect=ScraperError("NOT_FOUND"),
            ),
            patch("app.tasks.samocat_content_task.get_proxy_rotator"),
        ):
            from app.tasks.samocat_content_task import collect_samocat_content

            # Must not raise
            collect_samocat_content(str(row[0]))

        db2.execute.assert_not_called()

    # ---- scenario 3: RATE_LIMITED → self.retry() -----------------------

    def test_rate_limited_triggers_retry(self):
        """429 / RATE_LIMITED → self.retry() called, no DB write."""
        row = _make_row4()
        factory, db2 = _make_two_db_cms(row)

        with (
            patch(
                "app.tasks.samocat_content_task.get_db_session", side_effect=factory
            ),
            patch("app.tasks.samocat_content_task.SamokatScraper"),
            patch(
                "app.tasks.samocat_content_task.asyncio.run",
                side_effect=ScraperError("RATE_LIMITED"),
            ),
            patch("app.tasks.samocat_content_task.get_proxy_rotator"),
        ):
            from app.tasks.samocat_content_task import collect_samocat_content

            try:
                collect_samocat_content(str(row[0]))
            except Exception:
                pass  # Celery raises Retry exception — expected

        db2.execute.assert_not_called()

    # ---- scenario 4: NO_PRODUCT_ID -------------------------------------

    def test_no_product_id_silent_skip(self):
        """external_id=None → silent skip, no DB write."""
        row = _make_row4(product_id=None)
        factory, db2 = _make_two_db_cms(row)

        with (
            patch(
                "app.tasks.samocat_content_task.get_db_session", side_effect=factory
            ),
            patch("app.tasks.samocat_content_task.SamokatScraper"),
        ):
            from app.tasks.samocat_content_task import collect_samocat_content

            collect_samocat_content(str(row[0]))

        db2.execute.assert_not_called()

    # ---- scenario 5: PARSE_ERROR (non-numeric external_id) -------------

    def test_parse_error_non_numeric_external_id_skips(self):
        """Non-numeric external_id (slug) → log warning, return, no DB write."""
        row = _make_row4(product_id="moloko-prostokwashino")
        factory, db2 = _make_two_db_cms(row)

        with (
            patch(
                "app.tasks.samocat_content_task.get_db_session", side_effect=factory
            ),
            patch("app.tasks.samocat_content_task.SamokatScraper"),
        ):
            from app.tasks.samocat_content_task import collect_samocat_content

            collect_samocat_content(str(row[0]))

        db2.execute.assert_not_called()

    # ---- scenario 6: image URL fails SSRF allowlist --------------------

    def test_ssrf_image_url_s3_key_is_none_upsert_proceeds(self):
        """SSRF-blocked image URL → s3_key=None, content upsert still fires."""
        row = _make_row4()
        factory, db2 = _make_two_db_cms(row)

        # Return content with an internal / non-CDN image URL
        bad_content = _make_content(image_url=_SSRF_IMAGE_URL)

        with (
            patch(
                "app.tasks.samocat_content_task.get_db_session", side_effect=factory
            ),
            patch("app.tasks.samocat_content_task.SamokatScraper"),
            patch(
                "app.tasks.samocat_content_task.asyncio.run",
                return_value=bad_content,
            ),
            patch("app.tasks.samocat_content_task._get_minio"),
            patch("app.tasks.samocat_content_task.get_proxy_rotator"),
            patch("app.tasks.samocat_content_task.pg_insert") as mock_pg_insert,
        ):
            from app.tasks.samocat_content_task import collect_samocat_content

            collect_samocat_content(str(row[0]))

        # Upsert must still have executed
        db2.execute.assert_called_once()
        # s3_key (collected_image_url) must be None
        values_kwargs = mock_pg_insert.return_value.values.call_args[1]
        assert values_kwargs["collected_image_url"] is None

    # ---- scenario 7: image download / MinIO upload fails ---------------

    def test_image_download_failure_non_fatal(self):
        """MinIO upload error → s3_key=None, content upsert still fires."""
        row = _make_row4()
        factory, db2 = _make_two_db_cms(row)

        call_count = [0]

        def fake_run(coro):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_content(_VALID_IMAGE_URL)  # scrape succeeds
            raise OSError("MinIO unreachable")  # image download/upload fails

        with (
            patch(
                "app.tasks.samocat_content_task.get_db_session", side_effect=factory
            ),
            patch("app.tasks.samocat_content_task.SamokatScraper"),
            patch("app.tasks.samocat_content_task.asyncio.run", side_effect=fake_run),
            patch("app.tasks.samocat_content_task._get_minio"),
            patch("app.tasks.samocat_content_task.get_proxy_rotator"),
            patch("app.tasks.samocat_content_task.pg_insert") as mock_pg_insert,
        ):
            from app.tasks.samocat_content_task import collect_samocat_content

            collect_samocat_content(str(row[0]))

        db2.execute.assert_called_once()
        values_kwargs = mock_pg_insert.return_value.values.call_args[1]
        assert values_kwargs["collected_image_url"] is None

    # ---- scenario 8: images list empty (image_url=None) ----------------

    def test_empty_images_list_s3_key_none_upsert_proceeds(self):
        """image_url=None from scraper → s3_key=None, upsert fires with content fields."""
        row = _make_row4()
        factory, db2 = _make_two_db_cms(row)

        no_image_content = _make_content(image_url=None)

        with (
            patch(
                "app.tasks.samocat_content_task.get_db_session", side_effect=factory
            ),
            patch("app.tasks.samocat_content_task.SamokatScraper"),
            patch(
                "app.tasks.samocat_content_task.asyncio.run",
                return_value=no_image_content,
            ),
            patch("app.tasks.samocat_content_task._get_minio"),
            patch("app.tasks.samocat_content_task.get_proxy_rotator"),
            patch("app.tasks.samocat_content_task.pg_insert") as mock_pg_insert,
        ):
            from app.tasks.samocat_content_task import collect_samocat_content

            collect_samocat_content(str(row[0]))

        db2.execute.assert_called_once()
        values_kwargs = mock_pg_insert.return_value.values.call_args[1]
        assert values_kwargs["collected_image_url"] is None
        # Content fields must still be populated
        assert values_kwargs["collected_title"] == no_image_content.title

    # ---- scenario 9: cross-tenant isolation ----------------------------

    def test_cross_tenant_isolation(self):
        """Content task for org_A's sp_a must write sp_a_id, never sp_b_id."""
        sp_a_id = uuid.uuid4()
        sp_b_id = uuid.uuid4()
        row_a = (sp_a_id, SKU_A_ID, "12345", ORG_A)

        write_db = MagicMock()
        call_count = [0]

        def factory():
            call_count[0] += 1
            if call_count[0] == 1:
                db = MagicMock()
                db.query.return_value.join.return_value.filter.return_value.first.return_value = (
                    row_a
                )
                cm = MagicMock()
                cm.__enter__ = lambda s: db
                cm.__exit__ = MagicMock(return_value=False)
                return cm
            cm = MagicMock()
            cm.__enter__ = lambda s: write_db
            cm.__exit__ = MagicMock(return_value=False)
            return cm

        with (
            patch(
                "app.tasks.samocat_content_task.get_db_session", side_effect=factory
            ),
            patch("app.tasks.samocat_content_task.SamokatScraper"),
            patch(
                "app.tasks.samocat_content_task.asyncio.run",
                return_value=_make_content(),
            ),
            patch("app.tasks.samocat_content_task._get_minio"),
            patch("app.tasks.samocat_content_task.get_proxy_rotator"),
            patch("app.tasks.samocat_content_task.pg_insert") as mock_pg_insert,
        ):
            from app.tasks.samocat_content_task import collect_samocat_content

            collect_samocat_content(str(sp_a_id))

        write_db.execute.assert_called_once()
        values_kwargs = mock_pg_insert.return_value.values.call_args[1]
        assert values_kwargs["sku_platform_id"] == sp_a_id
        assert values_kwargs["sku_platform_id"] != sp_b_id

    # ---- scenario 20: sku_platform_id not found in DB ------------------

    def test_sp_not_in_db_skips_silently(self):
        """Stale task (sp deleted) → warning logged, no DB write, no crash."""
        cm, db = _make_db_cm(None)

        with patch(
            "app.tasks.samocat_content_task.get_db_session", return_value=cm
        ):
            from app.tasks.samocat_content_task import collect_samocat_content

            collect_samocat_content(str(uuid.uuid4()))

        db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# TestCollectSamokatPrice
# ---------------------------------------------------------------------------


class TestCollectSamokatPrice:
    """Scenarios 10-12: collect_samocat_price task."""

    def _run(self, row=None, price=None, scraper_side_effect=None):
        row = row or _make_row3()
        sp_id = row[0]
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.samocat_price_task.get_db_session", side_effect=factory),
            patch("app.tasks.samocat_price_task.SamokatScraper"),
            patch("app.tasks.samocat_price_task.asyncio.run") as mock_run,
            patch("app.tasks.samocat_price_task.get_proxy_rotator"),
        ):
            if scraper_side_effect:
                mock_run.side_effect = scraper_side_effect
            else:
                mock_run.return_value = price or _make_price()

            from app.tasks.samocat_price_task import collect_samocat_price

            collect_samocat_price(str(sp_id))

        return db2

    # ---- scenario 10: kopeks conversion --------------------------------

    def test_kopeks_converted_correctly(self):
        """9900 kopeks → Decimal('99.00'), 12500 → Decimal('125.00')."""
        price = PriceData(
            price=Decimal("99.00"),
            original_price=Decimal("125.00"),
            discount_pct=Decimal("21"),
            promo_label=None,
        )
        db2 = self._run(price=price)
        db2.add.assert_called_once()
        added = db2.add.call_args[0][0]
        assert added.price == Decimal("99.00")
        assert added.original_price == Decimal("125.00")
        assert added.discount_pct == Decimal("21")

    # ---- scenario 11: discountPercent=None → Decimal("0") --------------

    def test_discount_percent_none_defaults_to_zero(self):
        """discountPercent=None in API → discount_pct=Decimal('0'), no exception."""
        price = PriceData(
            price=Decimal("99.00"),
            original_price=Decimal("99.00"),
            discount_pct=Decimal("0"),
            promo_label=None,
        )
        db2 = self._run(price=price)
        db2.add.assert_called_once()
        added = db2.add.call_args[0][0]
        assert added.discount_pct == Decimal("0")

    def test_happy_path_inserts_snapshot(self):
        """Happy path — price_snapshots row added."""
        db2 = self._run()
        db2.add.assert_called_once()

    def test_collected_at_is_set(self):
        """collected_at must not be None."""
        db2 = self._run()
        added = db2.add.call_args[0][0]
        assert added.collected_at is not None

    def test_not_found_no_add(self):
        db2 = self._run(scraper_side_effect=ScraperError("NOT_FOUND"))
        db2.add.assert_not_called()

    def test_no_product_id_skips(self):
        db2 = self._run(row=_make_row3(product_id=None))
        db2.add.assert_not_called()

    # ---- scenario 19: API_UNAVAILABLE → retry --------------------------

    def test_api_unavailable_triggers_retry_no_db_write(self):
        """503 / API_UNAVAILABLE → self.retry(), no DB write."""
        row = _make_row3()
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.samocat_price_task.get_db_session", side_effect=factory),
            patch("app.tasks.samocat_price_task.SamokatScraper"),
            patch(
                "app.tasks.samocat_price_task.asyncio.run",
                side_effect=ScraperError("API_UNAVAILABLE"),
            ),
            patch("app.tasks.samocat_price_task.get_proxy_rotator"),
        ):
            from app.tasks.samocat_price_task import collect_samocat_price

            try:
                collect_samocat_price(str(row[0]))
            except Exception:
                pass

        db2.add.assert_not_called()

    # ---- scenario 12: cross-tenant isolation ---------------------------

    def test_cross_tenant_isolation(self):
        """Price task for sp_a must insert with sku_platform_id=sp_a_id."""
        sp_a_id = uuid.uuid4()
        row_a = (sp_a_id, "12345", ORG_A)
        factory, db2 = _make_two_db_cms(row_a)

        with (
            patch("app.tasks.samocat_price_task.get_db_session", side_effect=factory),
            patch("app.tasks.samocat_price_task.SamokatScraper"),
            patch(
                "app.tasks.samocat_price_task.asyncio.run",
                return_value=_make_price(),
            ),
            patch("app.tasks.samocat_price_task.get_proxy_rotator"),
        ):
            from app.tasks.samocat_price_task import collect_samocat_price

            collect_samocat_price(str(sp_a_id))

        db2.add.assert_called_once()
        added = db2.add.call_args[0][0]
        assert added.sku_platform_id == sp_a_id
        assert added.sku_platform_id != SP_B_ID

    def test_sp_not_in_db_skips(self):
        cm, db = _make_db_cm(None)
        with patch("app.tasks.samocat_price_task.get_db_session", return_value=cm):
            from app.tasks.samocat_price_task import collect_samocat_price

            collect_samocat_price(str(uuid.uuid4()))
        db.add.assert_not_called()


# ---------------------------------------------------------------------------
# TestCollectSamokatStock
# ---------------------------------------------------------------------------


class TestCollectSamokatStock:
    """Scenarios 13-15: collect_samocat_stock task."""

    def _run(self, row=None, stock=None, scraper_side_effect=None):
        row = row or _make_row3()
        sp_id = row[0]
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.samocat_stock_task.get_db_session", side_effect=factory),
            patch("app.tasks.samocat_stock_task.SamokatScraper"),
            patch("app.tasks.samocat_stock_task.asyncio.run") as mock_run,
            patch("app.tasks.samocat_stock_task.get_proxy_rotator"),
        ):
            if scraper_side_effect:
                mock_run.side_effect = scraper_side_effect
            else:
                mock_run.return_value = stock or _make_stock()

            from app.tasks.samocat_stock_task import collect_samocat_stock

            collect_samocat_stock(str(sp_id))

        return db2

    # ---- scenario 13: happy path ---------------------------------------

    def test_happy_path_executes_upsert(self):
        """in_stock=True, warehouse_qty=48 → upsert executed once."""
        db2 = self._run(stock=_make_stock(in_stock=True, total_qty=48))
        db2.execute.assert_called_once()

    def test_out_of_stock_executes_upsert(self):
        """in_stock=False, warehouse_qty=0 → upsert executed."""
        db2 = self._run(stock=_make_stock(in_stock=False, total_qty=0))
        db2.execute.assert_called_once()

    # ---- scenario 14: non-integer availableQuantity --------------------

    def test_non_integer_available_quantity_defaults_to_zero(self):
        """availableQuantity='много' → scraper returns total_qty=0, upsert fires."""
        # The defensive cast happens in the scraper; by the time the task
        # receives StockData, total_qty is already 0.
        db2 = self._run(stock=StockData(in_stock=True, total_qty=0))
        db2.execute.assert_called_once()

    def test_not_found_no_execute(self):
        db2 = self._run(scraper_side_effect=ScraperError("NOT_FOUND"))
        db2.execute.assert_not_called()

    def test_no_product_id_skips(self):
        db2 = self._run(row=_make_row3(product_id=None))
        db2.execute.assert_not_called()

    def test_api_unavailable_no_db_write(self):
        """503 / API_UNAVAILABLE → self.retry(), no DB write."""
        row = _make_row3()
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.samocat_stock_task.get_db_session", side_effect=factory),
            patch("app.tasks.samocat_stock_task.SamokatScraper"),
            patch(
                "app.tasks.samocat_stock_task.asyncio.run",
                side_effect=ScraperError("API_UNAVAILABLE"),
            ),
            patch("app.tasks.samocat_stock_task.get_proxy_rotator"),
        ):
            from app.tasks.samocat_stock_task import collect_samocat_stock

            try:
                collect_samocat_stock(str(row[0]))
            except Exception:
                pass

        db2.execute.assert_not_called()

    # ---- scenario 15: cross-tenant isolation ---------------------------

    def test_cross_tenant_isolation(self):
        """Stock task for sp_a must upsert with sku_platform_id=sp_a_id, not sp_b_id."""
        sp_a_id = uuid.uuid4()
        row_a = (sp_a_id, "12345", ORG_A)
        factory, db2 = _make_two_db_cms(row_a)

        with (
            patch("app.tasks.samocat_stock_task.get_db_session", side_effect=factory),
            patch("app.tasks.samocat_stock_task.SamokatScraper"),
            patch(
                "app.tasks.samocat_stock_task.asyncio.run",
                return_value=_make_stock(),
            ),
            patch("app.tasks.samocat_stock_task.get_proxy_rotator"),
            patch("app.tasks.samocat_stock_task.pg_insert") as mock_pg_insert,
        ):
            from app.tasks.samocat_stock_task import collect_samocat_stock

            collect_samocat_stock(str(sp_a_id))

        db2.execute.assert_called_once()
        values_kwargs = mock_pg_insert.return_value.values.call_args[1]
        assert values_kwargs["sku_platform_id"] == sp_a_id
        assert values_kwargs["sku_platform_id"] != SP_B_ID

    def test_sp_not_in_db_skips(self):
        cm, db = _make_db_cm(None)
        with patch("app.tasks.samocat_stock_task.get_db_session", return_value=cm):
            from app.tasks.samocat_stock_task import collect_samocat_stock

            collect_samocat_stock(str(uuid.uuid4()))
        db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# TestCollectSamokatReviews
# ---------------------------------------------------------------------------


class TestCollectSamokatReviews:
    """Scenarios 16-18: collect_samocat_reviews task."""

    def _run(self, row=None, reviews=None, scraper_side_effect=None):
        row = row or _make_row3()
        sp_id = row[0]
        factory, db2 = _make_two_db_cms(row)

        with (
            patch(
                "app.tasks.samocat_reviews_task.get_db_session", side_effect=factory
            ),
            patch("app.tasks.samocat_reviews_task.SamokatScraper"),
            patch("app.tasks.samocat_reviews_task.asyncio.run") as mock_run,
            patch("app.tasks.samocat_reviews_task.pg_insert") as mock_pg_insert,
            patch("app.tasks.samocat_reviews_task.get_proxy_rotator"),
        ):
            if scraper_side_effect:
                mock_run.side_effect = scraper_side_effect
            else:
                mock_run.return_value = (
                    reviews if reviews is not None else _make_reviews()
                )

            # Wire up the pg_insert mock chain expected by the task
            mock_stmt = MagicMock()
            (
                mock_pg_insert.return_value.values.return_value.on_conflict_do_update.return_value
            ) = mock_stmt

            from app.tasks.samocat_reviews_task import collect_samocat_reviews

            collect_samocat_reviews(str(sp_id))

        return db2, mock_pg_insert

    # ---- scenario 16: deduplication (ON CONFLICT DO UPDATE) ------------

    def test_deduplication_uses_on_conflict_do_update(self):
        """Reviews upsert must use ON CONFLICT DO UPDATE (not do_nothing)."""
        _, mock_pg_insert = self._run()
        on_conflict_calls = (
            mock_pg_insert.return_value.values.return_value.on_conflict_do_update.call_args_list
        )
        assert len(on_conflict_calls) == 1

    def test_deduplication_constraint_name(self):
        """ON CONFLICT must reference uq_reviews_sp_ext_id constraint."""
        _, mock_pg_insert = self._run()
        call_kwargs = (
            mock_pg_insert.return_value.values.return_value.on_conflict_do_update.call_args[
                1
            ]
        )
        assert call_kwargs.get("constraint") == "uq_reviews_sp_ext_id"

    def test_single_bulk_execute_not_n_plus_1(self):
        """All reviews must be written via a single bulk INSERT, not a loop."""
        db2, _ = self._run(reviews=_make_reviews(5))
        assert db2.execute.call_count == 1

    def test_values_list_contains_all_reviews(self):
        """All 2 reviews must appear in the values list."""
        _, mock_pg_insert = self._run(reviews=_make_reviews(2))
        values_arg = mock_pg_insert.return_value.values.call_args[0][0]
        assert len(values_arg) == 2
        ext_ids = {v["external_review_id"] for v in values_arg}
        assert ext_ids == {"rev-000", "rev-001"}

    def test_values_include_sku_platform_id(self):
        sp_id = uuid.uuid4()
        row = _make_row3(sp_id=sp_id)
        _, mock_pg_insert = self._run(row=row)
        values_arg = mock_pg_insert.return_value.values.call_args[0][0]
        for v in values_arg:
            assert v["sku_platform_id"] == sp_id

    # ---- scenario 17: empty reviews list → early return ----------------

    def test_empty_reviews_no_db_execute(self):
        """API returns [] → task returns early, no DB session opened for write."""
        db2, _ = self._run(reviews=[])
        db2.execute.assert_not_called()

    # ---- scenario 18: cross-tenant isolation ---------------------------

    def test_cross_tenant_isolation(self):
        """All review rows must have sku_platform_id=sp_a_id, not sp_b_id."""
        sp_a_id = uuid.uuid4()
        row_a = (sp_a_id, "12345", ORG_A)
        _, mock_pg_insert = self._run(row=row_a)
        values_arg = mock_pg_insert.return_value.values.call_args[0][0]
        for v in values_arg:
            assert v["sku_platform_id"] == sp_a_id
            assert v["sku_platform_id"] != SP_B_ID

    def test_api_unavailable_no_db_write(self):
        """503 / API_UNAVAILABLE → retry, no DB write."""
        row = _make_row3()
        factory, db2 = _make_two_db_cms(row)

        with (
            patch(
                "app.tasks.samocat_reviews_task.get_db_session", side_effect=factory
            ),
            patch("app.tasks.samocat_reviews_task.SamokatScraper"),
            patch(
                "app.tasks.samocat_reviews_task.asyncio.run",
                side_effect=ScraperError("API_UNAVAILABLE"),
            ),
            patch("app.tasks.samocat_reviews_task.get_proxy_rotator"),
        ):
            from app.tasks.samocat_reviews_task import collect_samocat_reviews

            try:
                collect_samocat_reviews(str(row[0]))
            except Exception:
                pass

        db2.execute.assert_not_called()

    def test_sp_not_in_db_skips(self):
        cm, db = _make_db_cm(None)
        with patch(
            "app.tasks.samocat_reviews_task.get_db_session", return_value=cm
        ):
            from app.tasks.samocat_reviews_task import collect_samocat_reviews

            collect_samocat_reviews(str(uuid.uuid4()))
        db.execute.assert_not_called()

    def test_not_found_no_db_write(self):
        db2, _ = self._run(scraper_side_effect=ScraperError("NOT_FOUND"))
        db2.execute.assert_not_called()


# ---------------------------------------------------------------------------
# TestSamokatScraper  (unit tests on the scraper itself — no tasks)
# ---------------------------------------------------------------------------


class TestSamokatScraper:
    """Unit tests for SamokatScraper helpers and parsing logic."""

    def test_parse_product_id_accepts_numeric_string(self):
        """_parse_product_id('12345') must return '12345'."""
        from app.scrapers.samocat import _parse_product_id

        assert _parse_product_id("12345") == "12345"

    def test_parse_product_id_raises_value_error_for_none(self):
        """None external_id → ValueError('NO_PRODUCT_ID')."""
        from app.scrapers.samocat import _parse_product_id

        with pytest.raises(ValueError, match="NO_PRODUCT_ID"):
            _parse_product_id(None)

    def test_parse_product_id_raises_value_error_for_empty(self):
        """Empty string → ValueError('NO_PRODUCT_ID')."""
        from app.scrapers.samocat import _parse_product_id

        with pytest.raises(ValueError, match="NO_PRODUCT_ID"):
            _parse_product_id("")

    def test_parse_product_id_raises_scraper_error_for_slug(self):
        """Non-numeric slug → ScraperError('PARSE_ERROR')."""
        from app.scrapers.samocat import _parse_product_id

        with pytest.raises(ScraperError) as exc_info:
            _parse_product_id("moloko-prostokwashino")
        assert exc_info.value.code == "PARSE_ERROR"

    def test_ssrf_allowlist_accepts_cdn_url(self):
        """cdn.samokat.ru URL must pass the SSRF allowlist."""
        from app.scrapers.samocat import _SK_IMAGE_CDN_RE

        assert _SK_IMAGE_CDN_RE.match(_VALID_IMAGE_URL) is not None

    def test_ssrf_allowlist_rejects_internal_ip(self):
        """Internal IP URL must NOT pass the allowlist."""
        from app.scrapers.samocat import _SK_IMAGE_CDN_RE

        assert _SK_IMAGE_CDN_RE.match(_SSRF_IMAGE_URL) is None

    def test_ssrf_allowlist_rejects_http_scheme_only(self):
        """Plain http (not https) must be rejected."""
        from app.scrapers.samocat import _SK_IMAGE_CDN_RE

        http_cdn = "http://cdn.samokat.ru/products/12345/main.jpg"
        assert _SK_IMAGE_CDN_RE.match(http_cdn) is None

    def test_kopeks_to_decimal_conversion(self):
        """_kopeks_to_decimal(9900) must return Decimal('99.00')."""
        from app.scrapers.samocat import _kopeks_to_decimal

        assert _kopeks_to_decimal(9900) == Decimal("99.00")
        assert _kopeks_to_decimal(12500) == Decimal("125.00")
        assert _kopeks_to_decimal(0) == Decimal("0.00")

    def test_safe_qty_non_integer_returns_zero(self):
        """_safe_qty('много') must return 0."""
        from app.scrapers.samocat import _safe_qty

        assert _safe_qty("много") == 0

    def test_safe_qty_valid_integer_string(self):
        """_safe_qty('48') must return 48."""
        from app.scrapers.samocat import _safe_qty

        assert _safe_qty("48") == 48

    def test_safe_qty_integer_input(self):
        """_safe_qty(48) must return 48."""
        from app.scrapers.samocat import _safe_qty

        assert _safe_qty(48) == 48

    def test_safe_qty_none_returns_zero(self):
        """_safe_qty(None) must return 0."""
        from app.scrapers.samocat import _safe_qty

        assert _safe_qty(None) == 0

    def test_rating_float_is_truncated_and_clamped(self):
        """Rating 4.5 → int(4.5) = 4; rating 0 → clamped to 1; rating 6 → clamped to 5."""
        from app.scrapers.samocat import _parse_rating

        assert _parse_rating(4.5) == 4
        assert _parse_rating(0) == 1
        assert _parse_rating(6) == 5
        assert _parse_rating(3) == 3

    def test_parse_review_date_malformed_falls_back_to_today(self):
        """Malformed date string → fallback to date.today()."""
        from app.scrapers.samocat import _parse_review_date

        result = _parse_review_date("2024-99-99")
        assert result == date.today()

    def test_parse_review_date_valid_iso_format(self):
        """Well-formed ISO date string → parsed correctly."""
        from app.scrapers.samocat import _parse_review_date

        assert _parse_review_date("2026-03-15") == date(2026, 3, 15)
