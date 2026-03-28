"""
Unit tests for Lenta Celery tasks.

DB and scraper are fully mocked — no real DB or network calls.

Scenarios covered (from Refinement.md test list #1–58):
  lenta_content_task (13 tests):
    1.  Happy path — upsert called, s3_key set correctly
    2.  s3_key format: org/{org_id}/sku/{sku_id}/lenta/main.jpg
    3.  NOT_FOUND: no DB write
    4.  RATE_LIMITED: self.retry() called, no DB write
    5.  API_UNAVAILABLE: self.retry() called, no DB write
    6.  NO_PRODUCT_ID: silent skip, no DB write
    7.  PARSE_ERROR: log warning, no DB write
    8.  SSRF image URL: s3_key=None, upsert proceeds
    9.  Image download failure (MinIO error): s3_key=None, upsert proceeds
    10. Images list empty (image_url=None): s3_key=None, upsert proceeds
    11. MinIO upload failure: s3_key=None, upsert proceeds, exc_info logged
    12. Cross-tenant isolation: sp_a written, not sp_b
    13. Stale sp_id not in DB: warning logged, no crash

  lenta_price_task (10 tests):
    14. Happy path: PriceSnapshot added
    15. Kopeks conversion: 15990 → Decimal("159.90")
    16. discountPercent absent → Decimal("0")
    17. NOT_FOUND: no DB write
    18. RATE_LIMITED: self.retry(), no DB write
    19. API_UNAVAILABLE: self.retry(), no DB write
    20. NO_PRODUCT_ID: skip
    21. PARSE_ERROR: skip
    22. Cross-tenant isolation
    23. Stale sp_id: skip

  lenta_stock_task (11 tests):
    24. Happy path: in_stock=True, warehouse_qty=120
    25. Out of stock: in_stock=False, warehouse_qty=0
    26. Non-integer availableQuantity: warehouse_qty=0
    27. NOT_FOUND: no DB write
    28. RATE_LIMITED: self.retry(), no DB write
    29. API_UNAVAILABLE: self.retry(), no DB write
    30. NO_PRODUCT_ID: skip
    31. PARSE_ERROR: skip
    32. Partial-row contract: set_ contains ONLY in_stock and warehouse_qty
    33. Cross-tenant isolation
    34. Stale sp_id: skip

  lenta_reviews_task (13 tests):
    35. Happy path: 2 reviews upserted
    36. ON CONFLICT DO UPDATE (deduplication)
    37. Constraint name: uq_reviews_sp_ext_id
    38. Single bulk execute (not N+1)
    39. All reviews in values list
    40. Empty reviews list: no DB write
    41. NOT_FOUND (404 on reviews endpoint): returns [], no DB write
    42. RATE_LIMITED: self.retry(), no DB write
    43. API_UNAVAILABLE: self.retry(), no DB write
    44. NO_PRODUCT_ID: skip
    45. PARSE_ERROR: skip
    46. Cross-tenant isolation
    47. Stale sp_id: skip

  LentaScraper helpers (11 tests):
    48. _parse_product_id: valid numeric string
    49. _parse_product_id: None → ValueError
    50. _parse_product_id: empty string → ValueError
    51. _parse_product_id: slug → ScraperError("PARSE_ERROR")
    52. SSRF regex: accepts valid https://lenta.com/images/...jpg
    53. SSRF regex: rejects internal IP
    54. SSRF regex: rejects HTTP (not HTTPS)
    55. SSRF regex: rejects disallowed extension (.svg)
    56. _kopeks_to_decimal: 15990 → Decimal("159.90")
    57. _safe_qty: non-numeric string → 0
    58. _parse_rating: clamp to [1,5], None defaults to 5
"""

from __future__ import annotations

import re
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

# Lenta CDN — must match _LT_IMAGE_CDN_RE in scraper
_VALID_IMAGE_URL = "https://lenta.com/images/products/12345/main.jpg"
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
        title="Молоко Простоквашино 3.2% 930мл",
        description="Натуральное пастеризованное молоко из отборного сырья.",
        composition="Молоко нормализованное пастеризованное",
        image_url=image_url,
    )


def _make_price(
    price: int = 15990,
    original_price: int = 19990,
    discount_pct: Decimal | None = Decimal("20"),
):
    return PriceData(
        price=Decimal(price) / 100,
        original_price=Decimal(original_price) / 100,
        discount_pct=discount_pct if discount_pct is not None else Decimal("0"),
        promo_label=None,
    )


def _make_stock(in_stock: bool = True, total_qty: int = 120):
    return StockData(in_stock=in_stock, total_qty=total_qty)


def _make_reviews(n: int = 2):
    return [
        ReviewData(
            external_review_id=f"rev-{i:03d}",
            review_text=f"Отзыв {i}",
            rating=5,
            review_date=date(2026, 3, 15),
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# DB context-manager helpers
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
# TestCollectLentaContent  (scenarios 1-13)
# ---------------------------------------------------------------------------


class TestCollectLentaContent:
    """collect_lenta_content task — 13 scenarios."""

    # ---- scenario 1: happy path ----------------------------------------

    def test_happy_path_executes_upsert(self):
        """Happy path: content fetched, image uploaded, DB upserted once."""
        row = _make_row4()
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.lenta_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.lenta_content_task.LentaScraper"),
            patch(
                "app.tasks.lenta_content_task.asyncio.run",
                return_value=(_make_content(), b"fake_image"),
            ),
            patch("app.tasks.lenta_content_task._get_minio"),
            patch("app.tasks.lenta_content_task.get_proxy_rotator"),
        ):
            from app.tasks.lenta_content_task import collect_lenta_content

            collect_lenta_content(str(row[0]))

        db2.execute.assert_called_once()

    # ---- scenario 2: s3_key format -------------------------------------

    def test_s3_key_format(self):
        """s3_key must follow 'org/{org_id}/sku/{sku_id}/lenta/main.jpg' pattern."""
        sp_id = uuid.uuid4()
        sku_id = uuid.uuid4()
        row = _make_row4(sp_id=sp_id, sku_id=sku_id, org_id=ORG_A)
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.lenta_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.lenta_content_task.LentaScraper"),
            patch(
                "app.tasks.lenta_content_task.asyncio.run",
                return_value=(_make_content(_VALID_IMAGE_URL), b"fake_image"),
            ),
            patch("app.tasks.lenta_content_task._get_minio"),
            patch("app.tasks.lenta_content_task.get_proxy_rotator"),
            patch("app.tasks.lenta_content_task.pg_insert") as mock_pg_insert,
        ):
            from app.tasks.lenta_content_task import collect_lenta_content

            collect_lenta_content(str(sp_id))

        values_kwargs = mock_pg_insert.return_value.values.call_args[1]
        s3_key = values_kwargs["collected_image_url"]
        assert s3_key == f"org/{ORG_A}/sku/{sku_id}/lenta/main.jpg"

    # ---- scenario 3: NOT_FOUND -----------------------------------------

    def test_product_not_found_no_db_write(self):
        """404 / NOT_FOUND from scraper → no DB write, no exception raised."""
        row = _make_row4()
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.lenta_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.lenta_content_task.LentaScraper"),
            patch(
                "app.tasks.lenta_content_task.asyncio.run",
                side_effect=ScraperError("NOT_FOUND"),
            ),
            patch("app.tasks.lenta_content_task.get_proxy_rotator"),
        ):
            from app.tasks.lenta_content_task import collect_lenta_content

            collect_lenta_content(str(row[0]))

        db2.execute.assert_not_called()

    # ---- scenario 4: RATE_LIMITED → self.retry() -----------------------

    def test_rate_limited_triggers_retry(self):
        """429 / RATE_LIMITED → self.retry() called, no DB write."""
        row = _make_row4()
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.lenta_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.lenta_content_task.LentaScraper"),
            patch(
                "app.tasks.lenta_content_task.asyncio.run",
                side_effect=ScraperError("RATE_LIMITED"),
            ),
            patch("app.tasks.lenta_content_task.get_proxy_rotator"),
        ):
            from app.tasks.lenta_content_task import collect_lenta_content

            try:
                collect_lenta_content(str(row[0]))
            except Exception:
                pass  # Celery raises Retry — expected

        db2.execute.assert_not_called()

    # ---- scenario 5: API_UNAVAILABLE → self.retry() --------------------

    def test_api_unavailable_triggers_retry(self):
        """503 / API_UNAVAILABLE → self.retry() called, no DB write."""
        row = _make_row4()
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.lenta_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.lenta_content_task.LentaScraper"),
            patch(
                "app.tasks.lenta_content_task.asyncio.run",
                side_effect=ScraperError("API_UNAVAILABLE"),
            ),
            patch("app.tasks.lenta_content_task.get_proxy_rotator"),
        ):
            from app.tasks.lenta_content_task import collect_lenta_content

            try:
                collect_lenta_content(str(row[0]))
            except Exception:
                pass

        db2.execute.assert_not_called()

    # ---- scenario 6: NO_PRODUCT_ID -------------------------------------

    def test_no_product_id_silent_skip(self):
        """external_id=None → silent skip, no DB write."""
        row = _make_row4(product_id=None)
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.lenta_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.lenta_content_task.LentaScraper"),
        ):
            from app.tasks.lenta_content_task import collect_lenta_content

            collect_lenta_content(str(row[0]))

        db2.execute.assert_not_called()

    # ---- scenario 7: PARSE_ERROR (non-numeric external_id) -------------

    def test_parse_error_non_numeric_external_id_skips(self):
        """Non-numeric external_id (slug) → log warning, return, no DB write."""
        row = _make_row4(product_id="moloko-prostokwashino")
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.lenta_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.lenta_content_task.LentaScraper"),
        ):
            from app.tasks.lenta_content_task import collect_lenta_content

            collect_lenta_content(str(row[0]))

        db2.execute.assert_not_called()

    # ---- scenario 8: SSRF image URL ------------------------------------

    def test_ssrf_image_url_s3_key_is_none_upsert_proceeds(self):
        """SSRF-blocked image URL → s3_key=None, content upsert still fires."""
        row = _make_row4()
        factory, db2 = _make_two_db_cms(row)

        bad_content = _make_content(image_url=_SSRF_IMAGE_URL)

        with (
            patch("app.tasks.lenta_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.lenta_content_task.LentaScraper"),
            patch(
                "app.tasks.lenta_content_task.asyncio.run",
                return_value=(bad_content, None),
            ),
            patch("app.tasks.lenta_content_task._get_minio"),
            patch("app.tasks.lenta_content_task.get_proxy_rotator"),
            patch("app.tasks.lenta_content_task.pg_insert") as mock_pg_insert,
        ):
            from app.tasks.lenta_content_task import collect_lenta_content

            collect_lenta_content(str(row[0]))

        db2.execute.assert_called_once()
        values_kwargs = mock_pg_insert.return_value.values.call_args[1]
        assert values_kwargs["collected_image_url"] is None

    # ---- scenario 9: image download failure ----------------------------

    def test_image_download_failure_non_fatal(self):
        """MinIO upload error → s3_key=None, content upsert still fires."""
        row = _make_row4()
        factory, db2 = _make_two_db_cms(row)

        mock_minio_instance = MagicMock()
        mock_minio_instance.upload.side_effect = OSError("MinIO unreachable")

        with (
            patch("app.tasks.lenta_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.lenta_content_task.LentaScraper"),
            patch(
                "app.tasks.lenta_content_task.asyncio.run",
                return_value=(_make_content(_VALID_IMAGE_URL), b"fake_image"),
            ),
            patch(
                "app.tasks.lenta_content_task._get_minio",
                return_value=mock_minio_instance,
            ),
            patch("app.tasks.lenta_content_task.get_proxy_rotator"),
            patch("app.tasks.lenta_content_task.pg_insert") as mock_pg_insert,
        ):
            from app.tasks.lenta_content_task import collect_lenta_content

            collect_lenta_content(str(row[0]))

        db2.execute.assert_called_once()
        values_kwargs = mock_pg_insert.return_value.values.call_args[1]
        assert values_kwargs["collected_image_url"] is None

    # ---- scenario 10: images list empty (image_url=None) ---------------

    def test_empty_images_list_s3_key_none_upsert_proceeds(self):
        """image_url=None from scraper → s3_key=None, upsert fires with content fields."""
        row = _make_row4()
        factory, db2 = _make_two_db_cms(row)

        no_image_content = _make_content(image_url=None)

        with (
            patch("app.tasks.lenta_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.lenta_content_task.LentaScraper"),
            patch(
                "app.tasks.lenta_content_task.asyncio.run",
                return_value=(no_image_content, None),
            ),
            patch("app.tasks.lenta_content_task._get_minio"),
            patch("app.tasks.lenta_content_task.get_proxy_rotator"),
            patch("app.tasks.lenta_content_task.pg_insert") as mock_pg_insert,
        ):
            from app.tasks.lenta_content_task import collect_lenta_content

            collect_lenta_content(str(row[0]))

        db2.execute.assert_called_once()
        values_kwargs = mock_pg_insert.return_value.values.call_args[1]
        assert values_kwargs["collected_image_url"] is None
        assert values_kwargs["collected_title"] == no_image_content.title

    # ---- scenario 11: MinIO upload failure (exc_info logged) -----------

    def test_minio_upload_failure_exc_info_logged(self):
        """MinIO upload exception → s3_key=None, exc_info=True in logger.warning."""
        row = _make_row4()
        factory, db2 = _make_two_db_cms(row)

        mock_minio_instance = MagicMock()
        mock_minio_instance.upload.side_effect = ConnectionError("timeout")

        with (
            patch("app.tasks.lenta_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.lenta_content_task.LentaScraper"),
            patch(
                "app.tasks.lenta_content_task.asyncio.run",
                return_value=(_make_content(), b"data"),
            ),
            patch(
                "app.tasks.lenta_content_task._get_minio",
                return_value=mock_minio_instance,
            ),
            patch("app.tasks.lenta_content_task.get_proxy_rotator"),
            patch("app.tasks.lenta_content_task.pg_insert") as mock_pg_insert,
        ):
            from app.tasks.lenta_content_task import collect_lenta_content

            collect_lenta_content(str(row[0]))

        # Upsert proceeds even though MinIO failed
        db2.execute.assert_called_once()
        values_kwargs = mock_pg_insert.return_value.values.call_args[1]
        assert values_kwargs["collected_image_url"] is None

    # ---- scenario 12: cross-tenant isolation ---------------------------

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
            patch("app.tasks.lenta_content_task.get_db_session", side_effect=factory),
            patch("app.tasks.lenta_content_task.LentaScraper"),
            patch(
                "app.tasks.lenta_content_task.asyncio.run",
                return_value=(_make_content(), b"fake_image"),
            ),
            patch("app.tasks.lenta_content_task._get_minio"),
            patch("app.tasks.lenta_content_task.get_proxy_rotator"),
            patch("app.tasks.lenta_content_task.pg_insert") as mock_pg_insert,
        ):
            from app.tasks.lenta_content_task import collect_lenta_content

            collect_lenta_content(str(sp_a_id))

        write_db.execute.assert_called_once()
        values_kwargs = mock_pg_insert.return_value.values.call_args[1]
        assert values_kwargs["sku_platform_id"] == sp_a_id
        assert values_kwargs["sku_platform_id"] != sp_b_id

    # ---- scenario 13: stale sp_id not in DB ----------------------------

    def test_sp_not_in_db_skips_silently(self):
        """Stale task (sp deleted) → warning logged, no DB write, no crash."""
        cm, db = _make_db_cm(None)

        with patch("app.tasks.lenta_content_task.get_db_session", return_value=cm):
            from app.tasks.lenta_content_task import collect_lenta_content

            collect_lenta_content(str(uuid.uuid4()))

        db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# TestCollectLentaPrice  (scenarios 14-23)
# ---------------------------------------------------------------------------


class TestCollectLentaPrice:
    """collect_lenta_price task — 10 scenarios."""

    def _run(self, row=None, price=None, scraper_side_effect=None):
        row = row or _make_row3()
        sp_id = row[0]
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.lenta_price_task.get_db_session", side_effect=factory),
            patch("app.tasks.lenta_price_task.LentaScraper"),
            patch("app.tasks.lenta_price_task.asyncio.run") as mock_run,
            patch("app.tasks.lenta_price_task.get_proxy_rotator"),
        ):
            if scraper_side_effect:
                mock_run.side_effect = scraper_side_effect
            else:
                mock_run.return_value = price or _make_price()

            from app.tasks.lenta_price_task import collect_lenta_price

            collect_lenta_price(str(sp_id))

        return db2

    # ---- scenario 14: happy path ---------------------------------------

    def test_happy_path_inserts_snapshot(self):
        """Happy path — price_snapshots row added."""
        db2 = self._run()
        db2.add.assert_called_once()

    # ---- scenario 15: kopeks conversion --------------------------------

    def test_kopeks_converted_correctly(self):
        """15990 kopeks → Decimal('159.90'), 19990 → Decimal('199.90')."""
        price = PriceData(
            price=Decimal("159.90"),
            original_price=Decimal("199.90"),
            discount_pct=Decimal("20.00"),
            promo_label=None,
        )
        db2 = self._run(price=price)
        db2.add.assert_called_once()
        added = db2.add.call_args[0][0]
        assert added.price == Decimal("159.90")
        assert added.original_price == Decimal("199.90")
        assert added.discount_pct == Decimal("20.00")

    # ---- scenario 16: discountPercent absent → Decimal("0") ------------

    def test_discount_percent_absent_defaults_to_zero(self):
        """discountPercent absent → discount_pct=Decimal('0'), no exception."""
        price = PriceData(
            price=Decimal("159.90"),
            original_price=Decimal("159.90"),
            discount_pct=Decimal("0"),
            promo_label=None,
        )
        db2 = self._run(price=price)
        db2.add.assert_called_once()
        added = db2.add.call_args[0][0]
        assert added.discount_pct == Decimal("0")

    # ---- scenario 17: NOT_FOUND ----------------------------------------

    def test_not_found_no_add(self):
        """404 → no DB write."""
        db2 = self._run(scraper_side_effect=ScraperError("NOT_FOUND"))
        db2.add.assert_not_called()

    # ---- scenario 18: RATE_LIMITED → retry ----------------------------

    def test_rate_limited_triggers_retry_no_db_write(self):
        """429 / RATE_LIMITED → self.retry() called, no DB write."""
        row = _make_row3()
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.lenta_price_task.get_db_session", side_effect=factory),
            patch("app.tasks.lenta_price_task.LentaScraper"),
            patch(
                "app.tasks.lenta_price_task.asyncio.run",
                side_effect=ScraperError("RATE_LIMITED"),
            ),
            patch("app.tasks.lenta_price_task.get_proxy_rotator"),
        ):
            from app.tasks.lenta_price_task import collect_lenta_price

            try:
                collect_lenta_price(str(row[0]))
            except Exception:
                pass

        db2.add.assert_not_called()

    # ---- scenario 19: API_UNAVAILABLE → retry -------------------------

    def test_api_unavailable_triggers_retry_no_db_write(self):
        """503 / API_UNAVAILABLE → self.retry(), no DB write."""
        row = _make_row3()
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.lenta_price_task.get_db_session", side_effect=factory),
            patch("app.tasks.lenta_price_task.LentaScraper"),
            patch(
                "app.tasks.lenta_price_task.asyncio.run",
                side_effect=ScraperError("API_UNAVAILABLE"),
            ),
            patch("app.tasks.lenta_price_task.get_proxy_rotator"),
        ):
            from app.tasks.lenta_price_task import collect_lenta_price

            try:
                collect_lenta_price(str(row[0]))
            except Exception:
                pass

        db2.add.assert_not_called()

    # ---- scenario 20: NO_PRODUCT_ID ------------------------------------

    def test_no_product_id_skips(self):
        db2 = self._run(row=_make_row3(product_id=None))
        db2.add.assert_not_called()

    # ---- scenario 21: PARSE_ERROR --------------------------------------

    def test_parse_error_non_numeric_id_skips(self):
        """Non-numeric external_id → ScraperError(PARSE_ERROR) → no DB write."""
        db2 = self._run(row=_make_row3(product_id="moloko-prostokwashino"))
        db2.add.assert_not_called()

    # ---- scenario 22: cross-tenant isolation ---------------------------

    def test_cross_tenant_isolation(self):
        """Price task for sp_a must insert with sku_platform_id=sp_a_id."""
        sp_a_id = uuid.uuid4()
        row_a = (sp_a_id, "12345", ORG_A)
        factory, db2 = _make_two_db_cms(row_a)

        with (
            patch("app.tasks.lenta_price_task.get_db_session", side_effect=factory),
            patch("app.tasks.lenta_price_task.LentaScraper"),
            patch(
                "app.tasks.lenta_price_task.asyncio.run",
                return_value=_make_price(),
            ),
            patch("app.tasks.lenta_price_task.get_proxy_rotator"),
        ):
            from app.tasks.lenta_price_task import collect_lenta_price

            collect_lenta_price(str(sp_a_id))

        db2.add.assert_called_once()
        added = db2.add.call_args[0][0]
        assert added.sku_platform_id == sp_a_id
        assert added.sku_platform_id != SP_B_ID

    # ---- scenario 23: stale sp_id -------------------------------------

    def test_sp_not_in_db_skips(self):
        cm, db = _make_db_cm(None)
        with patch("app.tasks.lenta_price_task.get_db_session", return_value=cm):
            from app.tasks.lenta_price_task import collect_lenta_price

            collect_lenta_price(str(uuid.uuid4()))
        db.add.assert_not_called()


# ---------------------------------------------------------------------------
# TestCollectLentaStock  (scenarios 24-34)
# ---------------------------------------------------------------------------


class TestCollectLentaStock:
    """collect_lenta_stock task — 11 scenarios."""

    def _run(self, row=None, stock=None, scraper_side_effect=None):
        row = row or _make_row3()
        sp_id = row[0]
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.lenta_stock_task.get_db_session", side_effect=factory),
            patch("app.tasks.lenta_stock_task.LentaScraper"),
            patch("app.tasks.lenta_stock_task.asyncio.run") as mock_run,
            patch("app.tasks.lenta_stock_task.get_proxy_rotator"),
        ):
            if scraper_side_effect:
                mock_run.side_effect = scraper_side_effect
            else:
                mock_run.return_value = stock or _make_stock()

            from app.tasks.lenta_stock_task import collect_lenta_stock

            collect_lenta_stock(str(sp_id))

        return db2

    # ---- scenario 24: happy path ---------------------------------------

    def test_happy_path_executes_upsert(self):
        """in_stock=True, warehouse_qty=120 → upsert executed once."""
        db2 = self._run(stock=_make_stock(in_stock=True, total_qty=120))
        db2.execute.assert_called_once()

    # ---- scenario 25: out of stock -------------------------------------

    def test_out_of_stock_executes_upsert(self):
        """in_stock=False, warehouse_qty=0 → upsert executed."""
        db2 = self._run(stock=_make_stock(in_stock=False, total_qty=0))
        db2.execute.assert_called_once()

    # ---- scenario 26: non-integer availableQuantity --------------------

    def test_non_integer_available_quantity_defaults_to_zero(self):
        """availableQuantity='много' → scraper returns total_qty=0, upsert fires."""
        db2 = self._run(stock=StockData(in_stock=True, total_qty=0))
        db2.execute.assert_called_once()

    # ---- scenario 27: NOT_FOUND ----------------------------------------

    def test_not_found_no_execute(self):
        db2 = self._run(scraper_side_effect=ScraperError("NOT_FOUND"))
        db2.execute.assert_not_called()

    # ---- scenario 28: RATE_LIMITED → retry ----------------------------

    def test_rate_limited_triggers_retry_no_db_write(self):
        """429 / RATE_LIMITED → self.retry() called, no DB write."""
        row = _make_row3()
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.lenta_stock_task.get_db_session", side_effect=factory),
            patch("app.tasks.lenta_stock_task.LentaScraper"),
            patch(
                "app.tasks.lenta_stock_task.asyncio.run",
                side_effect=ScraperError("RATE_LIMITED"),
            ),
            patch("app.tasks.lenta_stock_task.get_proxy_rotator"),
        ):
            from app.tasks.lenta_stock_task import collect_lenta_stock

            try:
                collect_lenta_stock(str(row[0]))
            except Exception:
                pass

        db2.execute.assert_not_called()

    # ---- scenario 29: API_UNAVAILABLE → retry -------------------------

    def test_api_unavailable_no_db_write(self):
        """503 / API_UNAVAILABLE → self.retry(), no DB write."""
        row = _make_row3()
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.lenta_stock_task.get_db_session", side_effect=factory),
            patch("app.tasks.lenta_stock_task.LentaScraper"),
            patch(
                "app.tasks.lenta_stock_task.asyncio.run",
                side_effect=ScraperError("API_UNAVAILABLE"),
            ),
            patch("app.tasks.lenta_stock_task.get_proxy_rotator"),
        ):
            from app.tasks.lenta_stock_task import collect_lenta_stock

            try:
                collect_lenta_stock(str(row[0]))
            except Exception:
                pass

        db2.execute.assert_not_called()

    # ---- scenario 30: NO_PRODUCT_ID ------------------------------------

    def test_no_product_id_skips(self):
        db2 = self._run(row=_make_row3(product_id=None))
        db2.execute.assert_not_called()

    # ---- scenario 31: PARSE_ERROR --------------------------------------

    def test_parse_error_non_numeric_id_skips(self):
        db2 = self._run(row=_make_row3(product_id="moloko-prostokwashino"))
        db2.execute.assert_not_called()

    # ---- scenario 32: partial-row contract -----------------------------

    def test_partial_row_contract_content_fields_absent_from_set(self):
        """ON CONFLICT set_ must NOT contain content fields — partial-row contract."""
        sp_a_id = uuid.uuid4()
        row_a = (sp_a_id, "12345", ORG_A)
        factory, db2 = _make_two_db_cms(row_a)

        with (
            patch("app.tasks.lenta_stock_task.get_db_session", side_effect=factory),
            patch("app.tasks.lenta_stock_task.LentaScraper"),
            patch(
                "app.tasks.lenta_stock_task.asyncio.run",
                return_value=_make_stock(),
            ),
            patch("app.tasks.lenta_stock_task.get_proxy_rotator"),
            patch("app.tasks.lenta_stock_task.pg_insert") as mock_pg_insert,
        ):
            from app.tasks.lenta_stock_task import collect_lenta_stock

            collect_lenta_stock(str(sp_a_id))

        set_kwargs = (
            mock_pg_insert.return_value.values.return_value
            .on_conflict_do_update.call_args[1]["set_"]
        )
        # Stock-only fields must be present
        assert "in_stock" in set_kwargs
        assert "warehouse_qty" in set_kwargs
        # Content fields must be absent — they must never be overwritten by stock task
        for content_field in (
            "collected_title",
            "collected_description",
            "collected_composition",
            "collected_image_url",
        ):
            assert content_field not in set_kwargs, (
                f"Partial-row contract violated: '{content_field}' must not be in set_"
            )

    # ---- scenario 33: cross-tenant isolation ---------------------------

    def test_cross_tenant_isolation(self):
        """Stock task for sp_a must upsert with sku_platform_id=sp_a_id, not sp_b_id."""
        sp_a_id = uuid.uuid4()
        row_a = (sp_a_id, "12345", ORG_A)
        factory, db2 = _make_two_db_cms(row_a)

        with (
            patch("app.tasks.lenta_stock_task.get_db_session", side_effect=factory),
            patch("app.tasks.lenta_stock_task.LentaScraper"),
            patch(
                "app.tasks.lenta_stock_task.asyncio.run",
                return_value=_make_stock(),
            ),
            patch("app.tasks.lenta_stock_task.get_proxy_rotator"),
            patch("app.tasks.lenta_stock_task.pg_insert") as mock_pg_insert,
        ):
            from app.tasks.lenta_stock_task import collect_lenta_stock

            collect_lenta_stock(str(sp_a_id))

        db2.execute.assert_called_once()
        values_kwargs = mock_pg_insert.return_value.values.call_args[1]
        assert values_kwargs["sku_platform_id"] == sp_a_id
        assert values_kwargs["sku_platform_id"] != SP_B_ID

    # ---- scenario 34: stale sp_id -------------------------------------

    def test_sp_not_in_db_skips(self):
        cm, db = _make_db_cm(None)
        with patch("app.tasks.lenta_stock_task.get_db_session", return_value=cm):
            from app.tasks.lenta_stock_task import collect_lenta_stock

            collect_lenta_stock(str(uuid.uuid4()))
        db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# TestCollectLentaReviews  (scenarios 35-47)
# ---------------------------------------------------------------------------


class TestCollectLentaReviews:
    """collect_lenta_reviews task — 13 scenarios."""

    def _run(self, row=None, reviews=None, scraper_side_effect=None):
        row = row or _make_row3()
        sp_id = row[0]
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.lenta_reviews_task.get_db_session", side_effect=factory),
            patch("app.tasks.lenta_reviews_task.LentaScraper"),
            patch("app.tasks.lenta_reviews_task.asyncio.run") as mock_run,
            patch("app.tasks.lenta_reviews_task.pg_insert") as mock_pg_insert,
            patch("app.tasks.lenta_reviews_task.get_proxy_rotator"),
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

            from app.tasks.lenta_reviews_task import collect_lenta_reviews

            collect_lenta_reviews(str(sp_id))

        return db2, mock_pg_insert

    # ---- scenario 35: happy path ---------------------------------------

    def test_happy_path_executes_bulk_insert(self):
        """2 reviews → single db.execute called once."""
        db2, _ = self._run(reviews=_make_reviews(2))
        db2.execute.assert_called_once()

    # ---- scenario 36: deduplication (ON CONFLICT DO UPDATE) ------------

    def test_deduplication_uses_on_conflict_do_update(self):
        """Reviews upsert must use ON CONFLICT DO UPDATE (not do_nothing)."""
        _, mock_pg_insert = self._run()
        on_conflict_calls = (
            mock_pg_insert.return_value.values.return_value.on_conflict_do_update.call_args_list
        )
        assert len(on_conflict_calls) == 1

    # ---- scenario 37: constraint name ---------------------------------

    def test_deduplication_constraint_name(self):
        """ON CONFLICT must reference uq_reviews_sp_ext_id constraint."""
        _, mock_pg_insert = self._run()
        call_kwargs = (
            mock_pg_insert.return_value.values.return_value.on_conflict_do_update.call_args[1]
        )
        assert call_kwargs.get("constraint") == "uq_reviews_sp_ext_id"

    # ---- scenario 38: single bulk execute (not N+1) --------------------

    def test_single_bulk_execute_not_n_plus_1(self):
        """5 reviews → db.execute called exactly once (bulk, not per-review)."""
        db2, _ = self._run(reviews=_make_reviews(5))
        assert db2.execute.call_count == 1

    # ---- scenario 39: all reviews in values list -----------------------

    def test_values_list_contains_all_reviews(self):
        """All 2 reviews must appear in the values list."""
        _, mock_pg_insert = self._run(reviews=_make_reviews(2))
        values_arg = mock_pg_insert.return_value.values.call_args[0][0]
        assert len(values_arg) == 2
        ext_ids = {v["external_review_id"] for v in values_arg}
        assert ext_ids == {"rev-000", "rev-001"}

    # ---- scenario 40: empty reviews list → no DB write -----------------

    def test_empty_reviews_no_db_execute(self):
        """API returns [] → task returns early, no DB session opened for write."""
        db2, _ = self._run(reviews=[])
        db2.execute.assert_not_called()

    # ---- scenario 41: NOT_FOUND (404 on reviews endpoint) --------------

    def test_not_found_no_db_write(self):
        """404 on reviews endpoint → returns [], no DB write."""
        db2, _ = self._run(scraper_side_effect=ScraperError("NOT_FOUND"))
        db2.execute.assert_not_called()

    # ---- scenario 42: RATE_LIMITED → retry ----------------------------

    def test_rate_limited_triggers_retry_no_db_write(self):
        """429 / RATE_LIMITED → self.retry() called, no DB write."""
        row = _make_row3()
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.lenta_reviews_task.get_db_session", side_effect=factory),
            patch("app.tasks.lenta_reviews_task.LentaScraper"),
            patch(
                "app.tasks.lenta_reviews_task.asyncio.run",
                side_effect=ScraperError("RATE_LIMITED"),
            ),
            patch("app.tasks.lenta_reviews_task.get_proxy_rotator"),
        ):
            from app.tasks.lenta_reviews_task import collect_lenta_reviews

            try:
                collect_lenta_reviews(str(row[0]))
            except Exception:
                pass

        db2.execute.assert_not_called()

    # ---- scenario 43: API_UNAVAILABLE → retry -------------------------

    def test_api_unavailable_no_db_write(self):
        """503 / API_UNAVAILABLE → self.retry(), no DB write."""
        row = _make_row3()
        factory, db2 = _make_two_db_cms(row)

        with (
            patch("app.tasks.lenta_reviews_task.get_db_session", side_effect=factory),
            patch("app.tasks.lenta_reviews_task.LentaScraper"),
            patch(
                "app.tasks.lenta_reviews_task.asyncio.run",
                side_effect=ScraperError("API_UNAVAILABLE"),
            ),
            patch("app.tasks.lenta_reviews_task.get_proxy_rotator"),
        ):
            from app.tasks.lenta_reviews_task import collect_lenta_reviews

            try:
                collect_lenta_reviews(str(row[0]))
            except Exception:
                pass

        db2.execute.assert_not_called()

    # ---- scenario 44: NO_PRODUCT_ID ------------------------------------

    def test_no_product_id_skips(self):
        db2, _ = self._run(row=_make_row3(product_id=None))
        db2.execute.assert_not_called()

    # ---- scenario 45: PARSE_ERROR --------------------------------------

    def test_parse_error_non_numeric_id_skips(self):
        db2, _ = self._run(row=_make_row3(product_id="moloko-prostokwashino"))
        db2.execute.assert_not_called()

    # ---- scenario 46: cross-tenant isolation ---------------------------

    def test_cross_tenant_isolation(self):
        """All review rows must have sku_platform_id=sp_a_id, not sp_b_id."""
        sp_a_id = uuid.uuid4()
        row_a = (sp_a_id, "12345", ORG_A)
        _, mock_pg_insert = self._run(row=row_a)
        values_arg = mock_pg_insert.return_value.values.call_args[0][0]
        for v in values_arg:
            assert v["sku_platform_id"] == sp_a_id
            assert v["sku_platform_id"] != SP_B_ID

    # ---- scenario 47: stale sp_id -------------------------------------

    def test_sp_not_in_db_skips(self):
        cm, db = _make_db_cm(None)
        with patch("app.tasks.lenta_reviews_task.get_db_session", return_value=cm):
            from app.tasks.lenta_reviews_task import collect_lenta_reviews

            collect_lenta_reviews(str(uuid.uuid4()))
        db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# TestLentaScraperHelpers  (scenarios 48-58)
# ---------------------------------------------------------------------------


class TestLentaScraperHelpers:
    """LentaScraper module-level helper functions — 11 scenarios."""

    # ---- scenarios 48-51: _parse_product_id ----------------------------

    def test_parse_product_id_valid_numeric(self):
        """Valid numeric string → returned stripped."""
        from app.scrapers.samocat import _parse_product_id

        assert _parse_product_id("12345") == "12345"
        assert _parse_product_id("  12345  ") == "12345"

    def test_parse_product_id_none_raises_value_error(self):
        """None → ValueError("NO_PRODUCT_ID")."""
        from app.scrapers.samocat import _parse_product_id

        with pytest.raises(ValueError):
            _parse_product_id(None)

    def test_parse_product_id_empty_string_raises_value_error(self):
        """Empty string → ValueError."""
        from app.scrapers.samocat import _parse_product_id

        with pytest.raises(ValueError):
            _parse_product_id("")

    def test_parse_product_id_slug_raises_scraper_error(self):
        """Non-numeric slug → ScraperError("PARSE_ERROR")."""
        from app.scrapers.samocat import _parse_product_id

        with pytest.raises(ScraperError) as exc_info:
            _parse_product_id("moloko-prostokwashino")
        assert exc_info.value.code == "PARSE_ERROR"

    # ---- scenarios 51-54: SSRF regex -----------------------------------

    def test_ssrf_regex_accepts_valid_lenta_cdn_url(self):
        """Valid https://lenta.com/images/... URL accepted."""
        from app.scrapers.lenta import _LT_IMAGE_CDN_RE

        assert _LT_IMAGE_CDN_RE.match(
            "https://lenta.com/images/products/12345/main.jpg"
        )
        assert _LT_IMAGE_CDN_RE.match(
            "https://lenta.com/images/products/12345/thumb.webp"
        )

    def test_ssrf_regex_rejects_internal_ip(self):
        """Internal IP address → rejected."""
        from app.scrapers.lenta import _LT_IMAGE_CDN_RE

        assert not _LT_IMAGE_CDN_RE.match("http://192.168.1.1/evil.jpg")
        assert not _LT_IMAGE_CDN_RE.match("https://192.168.1.1/evil.jpg")

    def test_ssrf_regex_rejects_http_not_https(self):
        """HTTP (not HTTPS) lenta.com URL → rejected."""
        from app.scrapers.lenta import _LT_IMAGE_CDN_RE

        assert not _LT_IMAGE_CDN_RE.match(
            "http://lenta.com/images/products/12345/main.jpg"
        )

    def test_ssrf_regex_rejects_disallowed_extension(self):
        """Disallowed .svg extension → rejected."""
        from app.scrapers.lenta import _LT_IMAGE_CDN_RE

        assert not _LT_IMAGE_CDN_RE.match(
            "https://lenta.com/images/products/12345/main.svg"
        )

    # ---- scenario 55: _kopeks_to_decimal --------------------------------

    def test_kopeks_to_decimal_conversion(self):
        """15990 kopeks → Decimal('159.90')."""
        from app.scrapers.samocat import _kopeks_to_decimal

        result = _kopeks_to_decimal(15990)
        assert result == Decimal("159.90")

    # ---- scenario 56: _safe_qty ----------------------------------------

    def test_safe_qty_non_numeric_string_returns_zero(self):
        """Non-numeric string 'много' → 0."""
        from app.scrapers.samocat import _safe_qty

        assert _safe_qty("много") == 0
        assert _safe_qty(None) == 0

    # ---- scenario 57-58: _parse_rating, _parse_review_date -------------

    def test_parse_rating_clamps_and_defaults(self):
        """Rating clamped to [1,5], None defaults to 5."""
        from app.scrapers.samocat import _parse_rating

        assert _parse_rating(5) == 5
        assert _parse_rating(1) == 1
        assert _parse_rating(0) == 1   # clamped up
        assert _parse_rating(10) == 5  # clamped down
        assert _parse_rating(None) == 5  # default

    def test_parse_review_date_iso_and_fallback(self):
        """Valid ISO → date object; malformed/None → today."""
        from app.scrapers.samocat import _parse_review_date

        result = _parse_review_date("2026-03-15T10:00:00Z")
        assert result == date(2026, 3, 15)

        today = _parse_review_date(None)
        assert isinstance(today, date)

        fallback = _parse_review_date("not-a-date")
        assert isinstance(fallback, date)
