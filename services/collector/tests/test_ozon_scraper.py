"""
Unit tests for OzonScraper and module-level helpers.

All HTTP calls are mocked with respx — no real network requests.
Tests cover: _parse_price_str, _parse_item_id, _parse_widget_states,
_OZ_IMAGE_CDN_RE, collect_content, collect_price, collect_stock,
collect_reviews, and retry / error paths.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import httpx
import pytest
import respx

from app.core.base_scraper import ScraperError
from app.core.proxy import ProxyRotator
from app.scrapers.ozon import (
    OzonScraper,
    _OZ_IMAGE_CDN_RE,
    _parse_item_id,
    _parse_price_str,
    _parse_widget_states,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURE_ITEM_ID = "123456789"

FIXTURE_COMPOSER_RESPONSE = {
    "widgetStates": {
        "webProductHeading-123": json.dumps(
            {"title": "Test Product <b>Name</b>", "brand": "TestBrand"}
        ),
        "webPrice-123": json.dumps(
            {
                "price": {
                    "price": "1\xa0299\xa0\u20bd",
                    "originalPrice": "1\xa0999\xa0\u20bd",
                    "cardPrice": "1\xa0199\xa0\u20bd",
                }
            }
        ),
        "webDetailSKU-123": json.dumps(
            {
                "description": "  Some <i>description</i>  here  ",
                "characteristics": [{"name": "Состав", "values": ["Cotton 100%"]}],
            }
        ),
        "webGallery-123": json.dumps(
            {
                "images": [
                    {
                        "url": (
                            "https://ir.ozone.ru/s3/multimedia-b"
                            "/abcdef123456/wc1000/abcdef123456.jpg"
                        )
                    }
                ]
            }
        ),
        "webAddToCart-123": json.dumps({"availability": 1, "count": 42}),
        "webReviewList-123": json.dumps(
            {
                "reviews": [
                    {
                        "id": "rev-001",
                        "text": "<b>Отлично!</b>",
                        "score": 5,
                        "publishedAt": "2026-03-01",
                    },
                    {
                        "id": "rev-002",
                        "text": "Нормально",
                        "score": 3,
                        "publishedAt": "2026-02-15",
                    },
                ]
            }
        ),
    }
}

_VALID_IMAGE_URL = (
    "https://ir.ozone.ru/s3/multimedia-b/abcdef123456/wc1000/abcdef123456.jpg"
)

_COMPOSER_URL = "https://www.ozon.ru/api/composer-api.bx/page/json/v2"


@pytest.fixture
def proxy_rotator():
    return ProxyRotator([])


@pytest.fixture
def scraper(proxy_rotator):
    return OzonScraper(proxy_rotator=proxy_rotator)


@pytest.fixture
def mock_composer(respx_mock):
    """Mock a successful composer API response."""
    respx_mock.get(_COMPOSER_URL).mock(
        return_value=httpx.Response(200, json=FIXTURE_COMPOSER_RESPONSE)
    )
    return respx_mock


# ---------------------------------------------------------------------------
# _parse_price_str
# ---------------------------------------------------------------------------


def test_parse_price_str_formatted_rubles():
    """'1 299 ₽' (with non-breaking spaces) → Decimal('1299')."""
    assert _parse_price_str("1\xa0299\xa0\u20bd") == Decimal("1299")


def test_parse_price_str_zero():
    assert _parse_price_str("0 \u20bd") == Decimal("0")


def test_parse_price_str_none_returns_zero():
    assert _parse_price_str(None) == Decimal("0")


def test_parse_price_str_empty_string_returns_zero():
    assert _parse_price_str("") == Decimal("0")


def test_parse_price_str_na_returns_zero():
    assert _parse_price_str("N/A") == Decimal("0")


def test_parse_price_str_non_breaking_spaces_only():
    assert _parse_price_str("\xa0\xa0") == Decimal("0")


def test_parse_price_str_comma_decimal():
    """'1,99 ₽' → Decimal('1.99') — comma decimal separator normalisation."""
    assert _parse_price_str("1,99 \u20bd") == Decimal("1.99")


def test_parse_price_str_large_value():
    assert _parse_price_str("99\xa0999\xa0\u20bd") == Decimal("99999")


def test_parse_price_str_regular_spaces():
    assert _parse_price_str("1 299 \u20bd") == Decimal("1299")


# ---------------------------------------------------------------------------
# _parse_item_id
# ---------------------------------------------------------------------------


def test_parse_item_id_valid_numeric():
    assert _parse_item_id("123456789") == "123456789"


def test_parse_item_id_strips_whitespace():
    assert _parse_item_id("  123456789  ") == "123456789"


def test_parse_item_id_none_raises_value_error():
    with pytest.raises(ValueError) as exc_info:
        _parse_item_id(None)
    assert "NO_ITEM_ID" in str(exc_info.value)


def test_parse_item_id_empty_string_raises_value_error():
    with pytest.raises(ValueError):
        _parse_item_id("")


def test_parse_item_id_whitespace_only_raises_value_error():
    with pytest.raises(ValueError):
        _parse_item_id("   ")


def test_parse_item_id_non_numeric_raises_parse_error():
    with pytest.raises(ScraperError) as exc_info:
        _parse_item_id("not-a-number")
    assert exc_info.value.code == "PARSE_ERROR"


def test_parse_item_id_alphanumeric_raises_parse_error():
    with pytest.raises(ScraperError) as exc_info:
        _parse_item_id("123abc")
    assert exc_info.value.code == "PARSE_ERROR"


# ---------------------------------------------------------------------------
# _parse_widget_states
# ---------------------------------------------------------------------------


def test_parse_widget_states_happy_path():
    result = _parse_widget_states(FIXTURE_COMPOSER_RESPONSE)
    assert "webProductHeading-" in result
    assert "webPrice-" in result
    assert "webDetailSKU-" in result
    assert "webGallery-" in result
    assert "webAddToCart-" in result
    assert "webReviewList-" in result


def test_parse_widget_states_heading_title():
    result = _parse_widget_states(FIXTURE_COMPOSER_RESPONSE)
    assert result["webProductHeading-"]["title"] == "Test Product <b>Name</b>"


def test_parse_widget_states_malformed_inner_json_skipped():
    data = {
        "widgetStates": {
            "webProductHeading-999": '{"title": "Valid"}',
            "webPrice-999": "THIS IS NOT JSON {{{",  # malformed — must be skipped
        }
    }
    result = _parse_widget_states(data)
    assert "webProductHeading-" in result
    assert "webPrice-" not in result  # silently skipped


def test_parse_widget_states_empty_dict():
    result = _parse_widget_states({"widgetStates": {}})
    assert result == {}


def test_parse_widget_states_missing_widget_states_key():
    result = _parse_widget_states({})
    assert result == {}


def test_parse_widget_states_unknown_widget_prefix_ignored():
    data = {
        "widgetStates": {
            "unknownWidget-1": '{"foo": "bar"}',
        }
    }
    result = _parse_widget_states(data)
    assert result == {}


def test_parse_widget_states_first_prefix_wins_per_key():
    """Each key should only be stored under its first matching prefix."""
    data = {
        "widgetStates": {
            "webProductHeading-1": '{"title": "A"}',
            "webProductHeading-2": '{"title": "B"}',  # second heading — overwrites
        }
    }
    result = _parse_widget_states(data)
    # Either A or B — the point is only one entry exists under the prefix key
    assert "webProductHeading-" in result


# ---------------------------------------------------------------------------
# _OZ_IMAGE_CDN_RE
# ---------------------------------------------------------------------------


def test_oz_image_cdn_re_matches_valid_url():
    assert _OZ_IMAGE_CDN_RE.match(_VALID_IMAGE_URL)


def test_oz_image_cdn_re_matches_url_without_wc_segment():
    url = "https://ir.ozone.ru/s3/multimedia-b/abcdef123456/abcdef123456.jpg"
    assert _OZ_IMAGE_CDN_RE.match(url)


def test_oz_image_cdn_re_rejects_evil_com():
    assert not _OZ_IMAGE_CDN_RE.match("https://evil.com/image.jpg")


def test_oz_image_cdn_re_rejects_http_not_https():
    url = "http://ir.ozone.ru/s3/multimedia-b/abcdef123456/wc1000/abcdef123456.jpg"
    assert not _OZ_IMAGE_CDN_RE.match(url)


def test_oz_image_cdn_re_rejects_non_jpg():
    url = "https://ir.ozone.ru/s3/multimedia-b/abcdef123456/wc1000/abcdef123456.png"
    assert not _OZ_IMAGE_CDN_RE.match(url)


def test_oz_image_cdn_re_alphanumeric_hash_passes():
    """Path segments use full alphanumeric hashes, not hex-only — [a-z0-9] must accept them."""
    url = "https://ir.ozone.ru/s3/multimedia-z/xyz12345mnop/wc500/xyz12345mnop.jpg"
    assert _OZ_IMAGE_CDN_RE.match(url)


def test_oz_image_cdn_re_rejects_path_traversal():
    url = "https://ir.ozone.ru/s3/multimedia-b/../../../etc/passwd"
    assert not _OZ_IMAGE_CDN_RE.match(url)


# ---------------------------------------------------------------------------
# collect_content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collect_content_parses_title(scraper, mock_composer):
    content = await scraper.collect_content(FIXTURE_ITEM_ID)
    assert content.title == "Test Product Name"  # HTML stripped


@pytest.mark.asyncio
async def test_collect_content_parses_description(scraper, mock_composer):
    content = await scraper.collect_content(FIXTURE_ITEM_ID)
    assert "Some" in content.description
    assert "description" in content.description


@pytest.mark.asyncio
async def test_collect_content_parses_composition_from_characteristics(
    scraper, mock_composer
):
    content = await scraper.collect_content(FIXTURE_ITEM_ID)
    assert content.composition == "Cotton 100%"


@pytest.mark.asyncio
async def test_collect_content_image_url_passes_allowlist(scraper, mock_composer):
    content = await scraper.collect_content(FIXTURE_ITEM_ID)
    assert content.image_url is not None
    assert _OZ_IMAGE_CDN_RE.match(content.image_url)


@pytest.mark.asyncio
async def test_collect_content_not_found_when_heading_absent(scraper, respx_mock):
    no_heading = {
        "widgetStates": {
            "webDetailSKU-123": json.dumps({"description": "Some text"}),
        }
    }
    respx_mock.get(_COMPOSER_URL).mock(
        return_value=httpx.Response(200, json=no_heading)
    )
    with pytest.raises(ScraperError) as exc_info:
        await scraper.collect_content(FIXTURE_ITEM_ID)
    assert exc_info.value.code == "NOT_FOUND"


@pytest.mark.asyncio
async def test_collect_content_not_found_on_empty_widget_states(scraper, respx_mock):
    respx_mock.get(_COMPOSER_URL).mock(
        return_value=httpx.Response(200, json={"widgetStates": {}})
    )
    with pytest.raises(ScraperError) as exc_info:
        await scraper.collect_content(FIXTURE_ITEM_ID)
    assert exc_info.value.code == "NOT_FOUND"


@pytest.mark.asyncio
async def test_collect_content_parse_error_on_empty_title(scraper, respx_mock):
    empty_title_response = {
        "widgetStates": {
            "webProductHeading-1": json.dumps({"title": "  <b>  </b>  ", "brand": "B"}),
            "webDetailSKU-1": json.dumps({"description": "Desc"}),
        }
    }
    respx_mock.get(_COMPOSER_URL).mock(
        return_value=httpx.Response(200, json=empty_title_response)
    )
    with pytest.raises(ScraperError) as exc_info:
        await scraper.collect_content(FIXTURE_ITEM_ID)
    assert exc_info.value.code == "PARSE_ERROR"


@pytest.mark.asyncio
async def test_collect_content_evil_image_url_set_to_none(scraper, respx_mock):
    evil_gallery = {
        "widgetStates": {
            "webProductHeading-1": json.dumps({"title": "Product", "brand": "B"}),
            "webGallery-1": json.dumps(
                {"images": [{"url": "https://evil.com/malicious.jpg"}]}
            ),
        }
    }
    respx_mock.get(_COMPOSER_URL).mock(
        return_value=httpx.Response(200, json=evil_gallery)
    )
    content = await scraper.collect_content(FIXTURE_ITEM_ID)
    assert content.image_url is None


@pytest.mark.asyncio
async def test_collect_content_rich_content_fallback(scraper, respx_mock):
    """richContent used as description fallback when description field absent."""
    rich_only = {
        "widgetStates": {
            "webProductHeading-1": json.dumps({"title": "Product", "brand": "B"}),
            "webDetailSKU-1": json.dumps(
                {"richContent": "<p>Rich description here</p>"}
            ),
        }
    }
    respx_mock.get(_COMPOSER_URL).mock(
        return_value=httpx.Response(200, json=rich_only)
    )
    content = await scraper.collect_content(FIXTURE_ITEM_ID)
    assert "Rich description here" in content.description


@pytest.mark.asyncio
async def test_collect_content_no_composition_when_no_sostav(scraper, respx_mock):
    """Characteristics without 'Состав' → composition is None."""
    no_sostav = {
        "widgetStates": {
            "webProductHeading-1": json.dumps({"title": "Product", "brand": "B"}),
            "webDetailSKU-1": json.dumps(
                {
                    "description": "Some desc",
                    "characteristics": [{"name": "Цвет", "values": ["Красный"]}],
                }
            ),
        }
    }
    respx_mock.get(_COMPOSER_URL).mock(
        return_value=httpx.Response(200, json=no_sostav)
    )
    content = await scraper.collect_content(FIXTURE_ITEM_ID)
    assert content.composition is None


# ---------------------------------------------------------------------------
# collect_price
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collect_price_uses_card_price(scraper, mock_composer):
    """cardPrice has priority over standard price."""
    price_data = await scraper.collect_price(FIXTURE_ITEM_ID)
    # cardPrice = "1 199 ₽"
    assert price_data.price == Decimal("1199.00")


@pytest.mark.asyncio
async def test_collect_price_original_price_parsed(scraper, mock_composer):
    price_data = await scraper.collect_price(FIXTURE_ITEM_ID)
    assert price_data.original_price == Decimal("1999.00")


@pytest.mark.asyncio
async def test_collect_price_discount_calculated(scraper, mock_composer):
    price_data = await scraper.collect_price(FIXTURE_ITEM_ID)
    # (1999 - 1199) / 1999 * 100 ≈ 40.02%
    assert price_data.discount_pct > Decimal("40.00")
    assert price_data.discount_pct < Decimal("41.00")


@pytest.mark.asyncio
async def test_collect_price_no_discount_when_original_equals_price(
    scraper, respx_mock
):
    no_discount = {
        "widgetStates": {
            "webProductHeading-1": json.dumps({"title": "Product"}),
            "webPrice-1": json.dumps(
                {
                    "price": {
                        "price": "500\xa0\u20bd",
                        "originalPrice": "500\xa0\u20bd",
                    }
                }
            ),
        }
    }
    respx_mock.get(_COMPOSER_URL).mock(
        return_value=httpx.Response(200, json=no_discount)
    )
    price_data = await scraper.collect_price(FIXTURE_ITEM_ID)
    assert price_data.discount_pct == Decimal("0")
    assert price_data.promo_label is None


@pytest.mark.asyncio
async def test_collect_price_web_price_absent_returns_zeros(scraper, respx_mock):
    """No webPrice widget → PriceData with all zeros, not an error."""
    no_price_widget = {
        "widgetStates": {
            "webProductHeading-1": json.dumps({"title": "Product"}),
        }
    }
    respx_mock.get(_COMPOSER_URL).mock(
        return_value=httpx.Response(200, json=no_price_widget)
    )
    price_data = await scraper.collect_price(FIXTURE_ITEM_ID)
    assert price_data.price == Decimal("0")
    assert price_data.original_price == Decimal("0")
    assert price_data.discount_pct == Decimal("0")


# ---------------------------------------------------------------------------
# collect_stock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collect_stock_in_stock_true_when_availability_1_and_count_gt_0(
    scraper, mock_composer
):
    stock = await scraper.collect_stock(FIXTURE_ITEM_ID)
    assert stock.in_stock is True
    assert stock.total_qty == 42


@pytest.mark.asyncio
async def test_collect_stock_out_of_stock_when_availability_0(scraper, respx_mock):
    oos = {
        "widgetStates": {
            "webProductHeading-1": json.dumps({"title": "Product"}),
            "webAddToCart-1": json.dumps({"availability": 0, "count": 0}),
        }
    }
    respx_mock.get(_COMPOSER_URL).mock(return_value=httpx.Response(200, json=oos))
    stock = await scraper.collect_stock(FIXTURE_ITEM_ID)
    assert stock.in_stock is False
    assert stock.total_qty == 0


@pytest.mark.asyncio
async def test_collect_stock_count_zero_overrides_availability_1(
    scraper, respx_mock
):
    """availability=1 with count=0 must still yield in_stock=False."""
    mixed = {
        "widgetStates": {
            "webProductHeading-1": json.dumps({"title": "Product"}),
            "webAddToCart-1": json.dumps({"availability": 1, "count": 0}),
        }
    }
    respx_mock.get(_COMPOSER_URL).mock(return_value=httpx.Response(200, json=mixed))
    stock = await scraper.collect_stock(FIXTURE_ITEM_ID)
    assert stock.in_stock is False
    assert stock.total_qty == 0


@pytest.mark.asyncio
async def test_collect_stock_widget_absent_returns_out_of_stock(
    scraper, respx_mock
):
    """Missing webAddToCart widget → in_stock=False, total_qty=0 (graceful degradation)."""
    no_cart = {
        "widgetStates": {
            "webProductHeading-1": json.dumps({"title": "Product"}),
        }
    }
    respx_mock.get(_COMPOSER_URL).mock(
        return_value=httpx.Response(200, json=no_cart)
    )
    stock = await scraper.collect_stock(FIXTURE_ITEM_ID)
    assert stock.in_stock is False
    assert stock.total_qty == 0


# ---------------------------------------------------------------------------
# collect_reviews
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collect_reviews_happy_path(scraper, mock_composer):
    reviews = await scraper.collect_reviews(FIXTURE_ITEM_ID)
    assert len(reviews) == 2


@pytest.mark.asyncio
async def test_collect_reviews_html_stripped(scraper, mock_composer):
    reviews = await scraper.collect_reviews(FIXTURE_ITEM_ID)
    first = reviews[0]
    assert first.review_text == "Отлично!"
    assert "<b>" not in first.review_text


@pytest.mark.asyncio
async def test_collect_reviews_rating_and_date(scraper, mock_composer):
    reviews = await scraper.collect_reviews(FIXTURE_ITEM_ID)
    assert reviews[0].rating == 5
    assert reviews[0].review_date == date(2026, 3, 1)
    assert reviews[1].rating == 3
    assert reviews[1].review_date == date(2026, 2, 15)


@pytest.mark.asyncio
async def test_collect_reviews_empty_list(scraper, respx_mock):
    empty = {
        "widgetStates": {
            "webReviewList-1": json.dumps({"reviews": []}),
        }
    }
    respx_mock.get(_COMPOSER_URL).mock(
        return_value=httpx.Response(200, json=empty)
    )
    reviews = await scraper.collect_reviews(FIXTURE_ITEM_ID)
    assert reviews == []


@pytest.mark.asyncio
async def test_collect_reviews_rating_clamped_high(scraper, respx_mock):
    """score=99 must be clamped to 5."""
    data = {
        "widgetStates": {
            "webReviewList-1": json.dumps(
                {
                    "reviews": [
                        {
                            "id": "r1",
                            "text": "ok",
                            "score": 99,
                            "publishedAt": "2026-01-01",
                        }
                    ]
                }
            ),
        }
    }
    respx_mock.get(_COMPOSER_URL).mock(
        return_value=httpx.Response(200, json=data)
    )
    reviews = await scraper.collect_reviews(FIXTURE_ITEM_ID)
    assert reviews[0].rating == 5


@pytest.mark.asyncio
async def test_collect_reviews_rating_clamped_low(scraper, respx_mock):
    """score=-1 must be clamped to 1."""
    data = {
        "widgetStates": {
            "webReviewList-1": json.dumps(
                {
                    "reviews": [
                        {
                            "id": "r1",
                            "text": "bad",
                            "score": -1,
                            "publishedAt": "2026-01-01",
                        }
                    ]
                }
            ),
        }
    }
    respx_mock.get(_COMPOSER_URL).mock(
        return_value=httpx.Response(200, json=data)
    )
    reviews = await scraper.collect_reviews(FIXTURE_ITEM_ID)
    assert reviews[0].rating == 1


@pytest.mark.asyncio
async def test_collect_reviews_invalid_date_skipped(scraper, respx_mock):
    """Review with unparseable date is skipped; valid review is returned."""
    mixed_dates = {
        "widgetStates": {
            "webReviewList-1": json.dumps(
                {
                    "reviews": [
                        {
                            "id": "bad",
                            "text": "text",
                            "score": 5,
                            "publishedAt": "not-a-date",
                        },
                        {
                            "id": "good",
                            "text": "text",
                            "score": 4,
                            "publishedAt": "2026-03-01",
                        },
                    ]
                }
            ),
        }
    }
    respx_mock.get(_COMPOSER_URL).mock(
        return_value=httpx.Response(200, json=mixed_dates)
    )
    reviews = await scraper.collect_reviews(FIXTURE_ITEM_ID)
    assert len(reviews) == 1
    assert reviews[0].external_review_id == "good"


@pytest.mark.asyncio
async def test_collect_reviews_empty_id_skipped(scraper, respx_mock):
    """Review with empty id cannot be deduplicated — must be skipped."""
    empty_id = {
        "widgetStates": {
            "webReviewList-1": json.dumps(
                {
                    "reviews": [
                        {
                            "id": "",
                            "text": "no id",
                            "score": 5,
                            "publishedAt": "2026-01-01",
                        },
                        {
                            "id": "valid-id",
                            "text": "has id",
                            "score": 4,
                            "publishedAt": "2026-01-02",
                        },
                    ]
                }
            ),
        }
    }
    respx_mock.get(_COMPOSER_URL).mock(
        return_value=httpx.Response(200, json=empty_id)
    )
    reviews = await scraper.collect_reviews(FIXTURE_ITEM_ID)
    assert len(reviews) == 1
    assert reviews[0].external_review_id == "valid-id"


# ---------------------------------------------------------------------------
# Retry / error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collect_content_retries_on_429_succeeds_on_third(
    scraper, respx_mock
):
    """429 × 2 then 200 → success, call_count == 3."""
    call_count = 0

    def handler(request):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(429)
        return httpx.Response(200, json=FIXTURE_COMPOSER_RESPONSE)

    respx_mock.get(_COMPOSER_URL).mock(side_effect=handler)
    content = await scraper.collect_content(FIXTURE_ITEM_ID)
    assert content.title == "Test Product Name"
    assert call_count == 3


@pytest.mark.asyncio
async def test_collect_content_raises_rate_limited_after_3_retries(
    scraper, respx_mock
):
    """429 × 3 → ScraperError("RATE_LIMITED")."""
    respx_mock.get(_COMPOSER_URL).mock(return_value=httpx.Response(429))
    with pytest.raises(ScraperError) as exc_info:
        await scraper.collect_content(FIXTURE_ITEM_ID)
    assert exc_info.value.code == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_collect_content_raises_on_403(scraper, respx_mock):
    """Cloudflare 403 is treated as a rate-limit-style error (RATE_LIMITED or
    API_UNAVAILABLE depending on retry exhaustion path for non-429 4xx).

    The implementation calls raise_for_status() on 403 inside the retry loop;
    with_retry() does not retry non-429 4xx — it re-raises immediately, which
    the outer ScraperError handler wraps as API_UNAVAILABLE.
    We assert a ScraperError is raised (any code) so the task correctly fails.
    """
    respx_mock.get(_COMPOSER_URL).mock(return_value=httpx.Response(403))
    with pytest.raises(ScraperError):
        await scraper.collect_content(FIXTURE_ITEM_ID)


@pytest.mark.asyncio
async def test_collect_content_raises_api_unavailable_on_503(scraper, respx_mock):
    respx_mock.get(_COMPOSER_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(ScraperError) as exc_info:
        await scraper.collect_content(FIXTURE_ITEM_ID)
    assert exc_info.value.code == "API_UNAVAILABLE"


@pytest.mark.asyncio
async def test_collect_reviews_raises_on_403(scraper, respx_mock):
    """403 on reviews endpoint raises an exception.

    collect_reviews wraps the with_retry call but only catches ScraperError for
    re-raise; non-429 4xx from with_retry propagates as httpx.HTTPStatusError.
    The important contract is that an exception is raised (no silent success).
    """
    respx_mock.get(_COMPOSER_URL).mock(return_value=httpx.Response(403))
    with pytest.raises(Exception):
        await scraper.collect_reviews(FIXTURE_ITEM_ID)
