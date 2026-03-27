"""
Unit tests for WildberriesScraper and core scraper utilities.

All HTTP calls are mocked with respx — no real network requests.
Tests cover: content parsing, price formula, stock sum, review dedup,
sanitize helper, basket URL construction, and error path handling.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import httpx
import pytest
import respx

from app.core.sanitize import sanitize
from app.core.proxy import ProxyRotator
from app.core.base_scraper import ScraperError
from app.scrapers.wildberries import (
    WildberriesScraper,
    _WB_IMAGE_CDN_RE,
    _build_image_url,
    _select_basket,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURE_NM_ID = "12345678"

FIXTURE_WB_CARD = {
    "data": {
        "products": [
            {
                "id": 12345678,
                "name": "Test Product <b>Name</b>",
                "description": "  Some <i>description</i>  here  ",
                "composition": "Cotton 100%",
                "promoTextCard": "Sale!",
                "sizes": [
                    {
                        "price": {"product": 29900, "basic": 39900},
                        "stocks": [
                            {"qty": 10, "wh": 1},
                            {"qty": 5, "wh": 2},
                        ],
                    }
                ],
            }
        ]
    }
}

FIXTURE_WB_REVIEWS = {
    "feedbacks": [
        {
            "id": "rev-001",
            "text": "<b>Отлично!</b> Доволен покупкой.",
            "productValuation": 5,
            "createdDate": "2026-03-01T12:00:00Z",
        },
        {
            "id": "rev-002",
            "text": "Нормально",
            "productValuation": 3,
            "createdDate": "2026-02-15T08:00:00Z",
        },
    ]
}


@pytest.fixture
def proxy_rotator():
    return ProxyRotator([])


@pytest.fixture
def scraper(proxy_rotator):
    return WildberriesScraper(proxy_rotator=proxy_rotator)


@pytest.fixture
def mock_wb_card(respx_mock):
    respx_mock.get("https://card.wb.ru/cards/v2/detail").mock(
        return_value=httpx.Response(200, json=FIXTURE_WB_CARD)
    )
    return respx_mock


@pytest.fixture
def mock_wb_card_not_found(respx_mock):
    respx_mock.get("https://card.wb.ru/cards/v2/detail").mock(
        return_value=httpx.Response(200, json={"data": {"products": []}})
    )
    return respx_mock


# ---------------------------------------------------------------------------
# sanitize helper
# ---------------------------------------------------------------------------

def test_sanitize_strips_html():
    assert sanitize("<b>Hello</b> world", 500) == "Hello world"


def test_sanitize_collapses_whitespace():
    assert sanitize("  one   two \n three  ", 100) == "one two three"


def test_sanitize_truncates_at_max_len():
    text = "A" * 600
    result = sanitize(text, 500)
    assert len(result) == 500


def test_sanitize_html_entities():
    assert sanitize("Цена &amp; скидка", 100) == "Цена & скидка"


def test_sanitize_none_returns_empty():
    assert sanitize(None, 100) == ""


def test_sanitize_empty_returns_empty():
    assert sanitize("", 100) == ""


# ---------------------------------------------------------------------------
# Image URL construction
# ---------------------------------------------------------------------------

def test_select_basket_low_vol():
    assert _select_basket(100) == 1  # vol 100 ≤ 143 → basket 1


def test_select_basket_high_vol():
    assert _select_basket(3500) == 20  # above all ranges → default 20


def test_build_image_url_structure():
    url = _build_image_url("12345678")
    # nm=12345678, vol=123, part=12345, basket=select_basket(123)=1
    assert url.startswith("https://basket-")
    assert "wbbasket.ru" in url
    assert "/images/big/1.jpg" in url


def test_wb_image_cdn_re_matches_valid():
    url = _build_image_url(FIXTURE_NM_ID)
    assert _WB_IMAGE_CDN_RE.match(url), f"URL did not match allowlist: {url}"


def test_wb_image_cdn_re_rejects_external():
    assert not _WB_IMAGE_CDN_RE.match("https://evil.com/img.jpg")
    assert not _WB_IMAGE_CDN_RE.match("http://basket-01.wbbasket.ru/vol123/part123/123/images/big/1.jpg")  # http not https


# ---------------------------------------------------------------------------
# collect_content
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_collect_content_parses_fields(scraper, mock_wb_card):
    content = await scraper.collect_content(FIXTURE_NM_ID)
    assert content.title == "Test Product Name"  # HTML stripped
    assert "Some" in content.description
    assert "description" in content.description
    assert content.composition == "Cotton 100%"
    assert content.image_url is not None
    assert "wbbasket.ru" in content.image_url


@pytest.mark.asyncio
async def test_collect_content_not_found_raises(scraper, mock_wb_card_not_found):
    with pytest.raises(ScraperError) as exc_info:
        await scraper.collect_content(FIXTURE_NM_ID)
    assert exc_info.value.code == "NOT_FOUND"


@pytest.mark.asyncio
async def test_collect_content_image_url_passes_allowlist(scraper, mock_wb_card):
    content = await scraper.collect_content(FIXTURE_NM_ID)
    assert _WB_IMAGE_CDN_RE.match(content.image_url)


# ---------------------------------------------------------------------------
# collect_price
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_collect_price_parses_kopeks(scraper, mock_wb_card):
    price_data = await scraper.collect_price(FIXTURE_NM_ID)
    # product=29900 kopeks / 100 = 299.00 RUB
    assert price_data.price == Decimal("299.00")
    # basic=39900 kopeks / 100 = 399.00 RUB
    assert price_data.original_price == Decimal("399.00")


@pytest.mark.asyncio
async def test_collect_price_discount_calculated(scraper, mock_wb_card):
    price_data = await scraper.collect_price(FIXTURE_NM_ID)
    # discount = (399 - 299) / 399 * 100 ≈ 25.06%
    assert price_data.discount_pct > Decimal("25.00")
    assert price_data.discount_pct < Decimal("26.00")


@pytest.mark.asyncio
async def test_collect_price_promo_label(scraper, mock_wb_card):
    price_data = await scraper.collect_price(FIXTURE_NM_ID)
    assert price_data.promo_label == "Sale!"


@pytest.mark.asyncio
async def test_collect_price_no_discount_when_same(scraper, respx_mock):
    no_discount_card = {
        "data": {
            "products": [
                {
                    "id": 12345678,
                    "name": "Product",
                    "sizes": [{"price": {"product": 10000, "basic": 10000}, "stocks": []}],
                }
            ]
        }
    }
    respx_mock.get("https://card.wb.ru/cards/v2/detail").mock(
        return_value=httpx.Response(200, json=no_discount_card)
    )
    price_data = await scraper.collect_price(FIXTURE_NM_ID)
    assert price_data.discount_pct == Decimal("0.00")
    assert price_data.price == price_data.original_price


# ---------------------------------------------------------------------------
# collect_stock
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_collect_stock_sums_all_warehouses(scraper, mock_wb_card):
    stock_data = await scraper.collect_stock(FIXTURE_NM_ID)
    # stocks: qty=10 + qty=5 = 15
    assert stock_data.total_qty == 15
    assert stock_data.in_stock is True


@pytest.mark.asyncio
async def test_collect_stock_out_of_stock(scraper, respx_mock):
    oos_card = {
        "data": {
            "products": [
                {
                    "id": 12345678,
                    "name": "Product",
                    "sizes": [{"price": {}, "stocks": [{"qty": 0, "wh": 1}]}],
                }
            ]
        }
    }
    respx_mock.get("https://card.wb.ru/cards/v2/detail").mock(
        return_value=httpx.Response(200, json=oos_card)
    )
    stock_data = await scraper.collect_stock(FIXTURE_NM_ID)
    assert stock_data.in_stock is False
    assert stock_data.total_qty == 0


# ---------------------------------------------------------------------------
# collect_reviews
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_collect_reviews_parses_list(scraper, respx_mock):
    respx_mock.get(re.compile(r"https://feedbacks2\.wb\.ru/feedbacks/v1/\d+")).mock(
        return_value=httpx.Response(200, json=FIXTURE_WB_REVIEWS)
    )
    reviews = await scraper.collect_reviews(FIXTURE_NM_ID, take=50)
    assert len(reviews) == 2
    review = reviews[0]
    assert review.external_review_id == "rev-001"
    assert review.review_text == "Отлично! Доволен покупкой."  # HTML stripped
    assert review.rating == 5
    assert review.review_date == date(2026, 3, 1)


@pytest.mark.asyncio
async def test_collect_reviews_empty(scraper, respx_mock):
    respx_mock.get(re.compile(r"https://feedbacks2\.wb\.ru/feedbacks/v1/\d+")).mock(
        return_value=httpx.Response(200, json={"feedbacks": []})
    )
    reviews = await scraper.collect_reviews(FIXTURE_NM_ID)
    assert reviews == []


@pytest.mark.asyncio
async def test_collect_reviews_rating_clamped(scraper, respx_mock):
    bad_ratings = {
        "feedbacks": [
            {"id": "r1", "text": "ok", "productValuation": 99, "createdDate": "2026-01-01T00:00:00Z"},
            {"id": "r2", "text": "ok", "productValuation": -5, "createdDate": "2026-01-01T00:00:00Z"},
        ]
    }
    respx_mock.get(re.compile(r"https://feedbacks2\.wb\.ru/feedbacks/v1/\d+")).mock(
        return_value=httpx.Response(200, json=bad_ratings)
    )
    reviews = await scraper.collect_reviews(FIXTURE_NM_ID)
    assert all(1 <= r.rating <= 5 for r in reviews)


# ---------------------------------------------------------------------------
# Retry / error paths
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scraper_retries_on_429(scraper, respx_mock):
    call_count = 0

    def handler(request):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(429)
        return httpx.Response(200, json=FIXTURE_WB_CARD)

    respx_mock.get("https://card.wb.ru/cards/v2/detail").mock(side_effect=handler)
    content = await scraper.collect_content(FIXTURE_NM_ID)
    assert content.title  # succeeded on 3rd attempt
    assert call_count == 3


@pytest.mark.asyncio
async def test_scraper_raises_rate_limited_after_max_retries(scraper, respx_mock):
    respx_mock.get("https://card.wb.ru/cards/v2/detail").mock(
        return_value=httpx.Response(429)
    )
    with pytest.raises(ScraperError) as exc_info:
        await scraper.collect_content(FIXTURE_NM_ID)
    assert exc_info.value.code == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_scraper_raises_api_unavailable_on_5xx(scraper, respx_mock):
    respx_mock.get("https://card.wb.ru/cards/v2/detail").mock(
        return_value=httpx.Response(503)
    )
    with pytest.raises(ScraperError) as exc_info:
        await scraper.collect_content(FIXTURE_NM_ID)
    assert exc_info.value.code == "API_UNAVAILABLE"


@pytest.mark.asyncio
async def test_scraper_raises_parse_error_on_null_data(scraper, respx_mock):
    """Spec error code PARSE_ERROR: API returns valid JSON but unexpected structure."""
    respx_mock.get("https://card.wb.ru/cards/v2/detail").mock(
        return_value=httpx.Response(200, json={"data": None})
    )
    with pytest.raises(ScraperError) as exc_info:
        await scraper.collect_content(FIXTURE_NM_ID)
    assert exc_info.value.code == "PARSE_ERROR"


@pytest.mark.asyncio
async def test_collect_price_empty_sizes_returns_zero(scraper, respx_mock):
    """No sizes list → price=0, discount_pct=0."""
    empty_sizes_card = {
        "data": {
            "products": [{"id": 12345678, "name": "Product", "sizes": []}]
        }
    }
    respx_mock.get("https://card.wb.ru/cards/v2/detail").mock(
        return_value=httpx.Response(200, json=empty_sizes_card)
    )
    price_data = await scraper.collect_price(FIXTURE_NM_ID)
    assert price_data.price == Decimal("0.00")
    assert price_data.discount_pct == Decimal("0.00")


@pytest.mark.asyncio
async def test_collect_stock_empty_sizes_out_of_stock(scraper, respx_mock):
    """No sizes → in_stock=False, total_qty=0."""
    empty_sizes_card = {
        "data": {
            "products": [{"id": 12345678, "name": "Product", "sizes": []}]
        }
    }
    respx_mock.get("https://card.wb.ru/cards/v2/detail").mock(
        return_value=httpx.Response(200, json=empty_sizes_card)
    )
    stock_data = await scraper.collect_stock(FIXTURE_NM_ID)
    assert stock_data.in_stock is False
    assert stock_data.total_qty == 0


def test_build_image_url_non_numeric_raises_parse_error():
    """Non-numeric nm_id must raise ScraperError(PARSE_ERROR), not ValueError."""
    with pytest.raises(ScraperError) as exc_info:
        _build_image_url("not-a-number")
    assert exc_info.value.code == "PARSE_ERROR"


def test_wb_image_cdn_re_rejects_one_digit_basket():
    """Basket number must be exactly 2 digits (\\d{2})."""
    url = "https://basket-1.wbbasket.ru/vol123/part12345/12345678/images/big/1.jpg"
    assert not _WB_IMAGE_CDN_RE.match(url)


def test_scraper_rate_limited_retry_count(scraper, respx_mock):
    """RATE_LIMITED exhaustion must make exactly max_retries attempts."""
    import asyncio

    call_count = [0]

    def handler(request):
        call_count[0] += 1
        return httpx.Response(429)

    respx_mock.get("https://card.wb.ru/cards/v2/detail").mock(side_effect=handler)
    with pytest.raises(ScraperError) as exc_info:
        asyncio.get_event_loop().run_until_complete(scraper.collect_content(FIXTURE_NM_ID))
    assert exc_info.value.code == "RATE_LIMITED"
    assert call_count[0] == 3  # max_retries=3
