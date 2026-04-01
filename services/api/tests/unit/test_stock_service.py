"""
Unit tests for stock service helpers.

Tests _validate_row and _detect_encoding with no database calls.
"""

import pytest

from app.stock.service import _detect_encoding, _validate_row


class TestValidateRow:
    def test_valid_row_returns_no_errors(self):
        row = {
            "sku_barcode": "1234567890",
            "platform_name": "Wildberries",
            "group_name": "Electronics",
            "plan_tt_count": "100",
            "week_number": "12",
            "year": "2026",
        }
        assert _validate_row(2, row) == []

    def test_empty_sku_barcode_returns_error(self):
        row = {
            "sku_barcode": "",
            "platform_name": "WB",
            "group_name": "Cat",
            "plan_tt_count": "10",
            "week_number": "1",
            "year": "2026",
        }
        errors = _validate_row(2, row)
        assert any(e.field == "sku_barcode" for e in errors)

    def test_negative_plan_tt_count_returns_error(self):
        row = {
            "sku_barcode": "123",
            "platform_name": "WB",
            "group_name": "Cat",
            "plan_tt_count": "-5",
            "week_number": "1",
            "year": "2026",
        }
        errors = _validate_row(3, row)
        assert any(e.field == "plan_tt_count" for e in errors)

    def test_week_number_out_of_range_returns_error(self):
        row = {
            "sku_barcode": "123",
            "platform_name": "WB",
            "group_name": "Cat",
            "plan_tt_count": "10",
            "week_number": "54",
            "year": "2026",
        }
        errors = _validate_row(4, row)
        assert any(e.field == "week_number" for e in errors)

    def test_year_out_of_range_returns_error(self):
        row = {
            "sku_barcode": "123",
            "platform_name": "WB",
            "group_name": "Cat",
            "plan_tt_count": "10",
            "week_number": "1",
            "year": "1999",
        }
        errors = _validate_row(5, row)
        assert any(e.field == "year" for e in errors)

    def test_group_name_too_long_returns_error(self):
        row = {
            "sku_barcode": "123",
            "platform_name": "WB",
            "group_name": "A" * 101,
            "plan_tt_count": "10",
            "week_number": "1",
            "year": "2026",
        }
        errors = _validate_row(6, row)
        assert any(e.field == "group_name" for e in errors)

    def test_multiple_errors_reported_per_row(self):
        row = {
            "sku_barcode": "",
            "platform_name": "",
            "group_name": "",
            "plan_tt_count": "not_a_number",
            "week_number": "0",
            "year": "abc",
        }
        errors = _validate_row(7, row)
        assert len(errors) >= 5

    def test_row_index_preserved_in_errors(self):
        row = {
            "sku_barcode": "",
            "platform_name": "WB",
            "group_name": "Cat",
            "plan_tt_count": "10",
            "week_number": "1",
            "year": "2026",
        }
        errors = _validate_row(42, row)
        assert all(e.row == 42 for e in errors)


class TestDetectEncoding:
    def test_utf8_bom_detected(self):
        data = "\ufeffsku_barcode,platform\n".encode("utf-8-sig")
        assert _detect_encoding(data) == "utf-8-sig"

    def test_plain_utf8_detected(self):
        data = "sku_barcode,platform\n".encode("utf-8")
        assert _detect_encoding(data) == "utf-8"

    def test_non_utf8_falls_back_to_cp1251(self):
        data = "баркод,платформа\n".encode("cp1251")
        assert _detect_encoding(data) == "cp1251"
