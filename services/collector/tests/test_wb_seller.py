"""
Unit tests for WBSellerAPIScraper (L0 Seller API scraper).

All HTTP calls are mocked with respx — no real network requests.
Tests cover:
  - Content happy path (title, description, composition, image_url)
  - NOT_FOUND when cards list is empty
  - TOKEN_INVALID on HTTP 401
  - RATE_LIMITED on HTTP 429
  - API_UNAVAILABLE on HTTP 500
  - Bearer token is NOT visible in exception messages (security)
  - Price happy path with discount calculation
  - Stock happy path (sum across multiple warehouse entries)
"""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx

from app.core.base_scraper import ContentData, DataType, PriceData, ScraperError, StockData
from app.scrapers.seller_api.wb_seller import WBSellerAPIScraper


# ---------------------------------------------------------------------------
# API response fixtures
# ---------------------------------------------------------------------------

WB_CARDS_RESPONSE = {
    "cards": [
        {
            "title": "Test Product",
            "description": "Test description",
            "characteristics": [{"Состав": "cotton 100%"}],
            "photos": [{"big": "https://cdn.wbstatic.net/big/photo.jpg"}],
        }
    ]
}

WB_CARDS_EMPTY = {"cards": []}

WB_PRICES_RESPONSE = {
    "data": {
        "listGoods": [
            {
                "nmID": 12345,
                "sizes": [
                    {"price": 1000, "discountedPrice": 850}
                ],
            }
        ]
    }
}

WB_PRICES_NO_DISCOUNT = {
    "data": {
        "listGoods": [
            {
                "nmID": 12345,
                "sizes": [
                    {"price": 500, "discountedPrice": 500}
                ],
            }
        ]
    }
}

WB_STOCKS_RESPONSE = [
    {"nmId": 12345, "quantity": 15},
    {"nmId": 12345, "quantity": 5},
    {"nmId": 99999, "quantity": 100},  # different nm_id — must not be summed
]

WB_STOCKS_EMPTY = []


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_TOKEN = "test.bearer.token.value.abcdefghij"
NM_ID = "12345"

_CARDS_URL = "https://content-api.wildberries.ru/content/v2/get/cards/list"
_PRICES_URL = "https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter"
_STOCKS_URL = "https://statistics-api.wildberries.ru/api/v1/supplier/stocks"


@pytest.fixture
def scraper():
    return WBSellerAPIScraper(FAKE_TOKEN)


# ---------------------------------------------------------------------------
# Content tests
# ---------------------------------------------------------------------------

@respx.mock
def test_collect_content_success(scraper):
    """Happy path: correct fields extracted from WB Content API response."""
    respx.post(_CARDS_URL).mock(return_value=httpx.Response(200, json=WB_CARDS_RESPONSE))

    result = scraper.collect(NM_ID, DataType.CONTENT)

    assert isinstance(result, ContentData)
    assert result.title == "Test Product"
    assert result.description == "Test description"
    assert result.composition == "cotton 100%"
    assert result.image_url == "https://cdn.wbstatic.net/big/photo.jpg"


@respx.mock
def test_collect_content_not_found(scraper):
    """Empty cards list → ScraperError('NOT_FOUND')."""
    respx.post(_CARDS_URL).mock(return_value=httpx.Response(200, json=WB_CARDS_EMPTY))

    with pytest.raises(ScraperError) as exc_info:
        scraper.collect(NM_ID, DataType.CONTENT)

    assert exc_info.value.code == "NOT_FOUND"


@respx.mock
def test_collect_content_no_composition(scraper):
    """Card without composition characteristic → composition is None."""
    no_comp = {
        "cards": [
            {
                "title": "Simple Product",
                "description": "Just a product",
                "characteristics": [],
                "photos": [],
            }
        ]
    }
    respx.post(_CARDS_URL).mock(return_value=httpx.Response(200, json=no_comp))

    result = scraper.collect(NM_ID, DataType.CONTENT)

    assert result.composition is None
    assert result.image_url is None


# ---------------------------------------------------------------------------
# HTTP error handling
# ---------------------------------------------------------------------------

@respx.mock
def test_collect_401_raises_token_invalid(scraper):
    """HTTP 401 → ScraperError('TOKEN_INVALID')."""
    respx.post(_CARDS_URL).mock(return_value=httpx.Response(401))

    with pytest.raises(ScraperError) as exc_info:
        scraper.collect(NM_ID, DataType.CONTENT)

    assert exc_info.value.code == "TOKEN_INVALID"


@respx.mock
def test_collect_429_raises_rate_limited(scraper):
    """HTTP 429 → ScraperError('RATE_LIMITED')."""
    respx.post(_CARDS_URL).mock(return_value=httpx.Response(429))

    with pytest.raises(ScraperError) as exc_info:
        scraper.collect(NM_ID, DataType.CONTENT)

    assert exc_info.value.code == "RATE_LIMITED"


@respx.mock
def test_collect_500_raises_api_unavailable(scraper):
    """HTTP 500 → ScraperError('API_UNAVAILABLE')."""
    respx.post(_CARDS_URL).mock(return_value=httpx.Response(500, text="internal error"))

    with pytest.raises(ScraperError) as exc_info:
        scraper.collect(NM_ID, DataType.CONTENT)

    assert exc_info.value.code == "API_UNAVAILABLE"


@respx.mock
def test_collect_503_raises_api_unavailable(scraper):
    """Any 5xx status → ScraperError('API_UNAVAILABLE')."""
    respx.post(_CARDS_URL).mock(return_value=httpx.Response(503))

    with pytest.raises(ScraperError) as exc_info:
        scraper.collect(NM_ID, DataType.CONTENT)

    assert exc_info.value.code == "API_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Security: token must NOT appear in exception messages
# ---------------------------------------------------------------------------

@respx.mock
def test_bearer_token_not_in_exception_message(scraper):
    """
    The Bearer token must never be exposed in ScraperError messages.
    This guards against accidental token leakage via logs or error responses.
    """
    respx.post(_CARDS_URL).mock(
        return_value=httpx.Response(500, text=f"Bearer {FAKE_TOKEN} something")
    )

    with pytest.raises(ScraperError) as exc_info:
        scraper.collect(NM_ID, DataType.CONTENT)

    error_str = str(exc_info.value)
    assert FAKE_TOKEN not in error_str, (
        f"Bearer token leaked in exception message: {error_str!r}"
    )


@respx.mock
def test_bearer_token_not_in_401_message(scraper):
    """TOKEN_INVALID error message must not contain the token value."""
    respx.post(_CARDS_URL).mock(return_value=httpx.Response(401))

    with pytest.raises(ScraperError) as exc_info:
        scraper.collect(NM_ID, DataType.CONTENT)

    assert FAKE_TOKEN not in str(exc_info.value)


# ---------------------------------------------------------------------------
# Price tests
# ---------------------------------------------------------------------------

@respx.mock
def test_collect_price_success(scraper):
    """Happy path: price, original_price and discount_pct correctly computed."""
    respx.get(_PRICES_URL).mock(return_value=httpx.Response(200, json=WB_PRICES_RESPONSE))

    result = scraper.collect(NM_ID, DataType.PRICE)

    assert isinstance(result, PriceData)
    assert result.price == Decimal("850")
    assert result.original_price == Decimal("1000")
    # discount = (1000 - 850) / 1000 * 100 = 15.00%
    assert result.discount_pct == Decimal("15.00")
    assert result.promo_label is None  # WB Seller API doesn't expose promo labels


@respx.mock
def test_collect_price_no_discount(scraper):
    """When discountedPrice == price, discount_pct must be 0.00."""
    respx.get(_PRICES_URL).mock(return_value=httpx.Response(200, json=WB_PRICES_NO_DISCOUNT))

    result = scraper.collect(NM_ID, DataType.PRICE)

    assert result.discount_pct == Decimal("0.00")
    assert result.price == result.original_price


@respx.mock
def test_collect_price_not_found(scraper):
    """Empty listGoods → ScraperError('NOT_FOUND')."""
    empty = {"data": {"listGoods": []}}
    respx.get(_PRICES_URL).mock(return_value=httpx.Response(200, json=empty))

    with pytest.raises(ScraperError) as exc_info:
        scraper.collect(NM_ID, DataType.PRICE)

    assert exc_info.value.code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Stock tests
# ---------------------------------------------------------------------------

@respx.mock
def test_collect_stock_success(scraper):
    """
    Stock quantities for the requested nm_id are summed across all warehouse
    entries. Entries for other nm_ids must be ignored.
    """
    respx.get(_STOCKS_URL).mock(return_value=httpx.Response(200, json=WB_STOCKS_RESPONSE))

    result = scraper.collect(NM_ID, DataType.STOCK)

    assert isinstance(result, StockData)
    # 15 + 5 = 20 (nm_id=12345 entries only; nm_id=99999 ignored)
    assert result.total_qty == 20
    assert result.in_stock is True


@respx.mock
def test_collect_stock_empty_response(scraper):
    """Empty stock list → in_stock=False, total_qty=0."""
    respx.get(_STOCKS_URL).mock(return_value=httpx.Response(200, json=WB_STOCKS_EMPTY))

    result = scraper.collect(NM_ID, DataType.STOCK)

    assert result.in_stock is False
    assert result.total_qty == 0


@respx.mock
def test_collect_stock_out_of_stock(scraper):
    """All quantities are 0 → in_stock=False."""
    zero_stock = [{"nmId": 12345, "quantity": 0}]
    respx.get(_STOCKS_URL).mock(return_value=httpx.Response(200, json=zero_stock))

    result = scraper.collect(NM_ID, DataType.STOCK)

    assert result.in_stock is False
    assert result.total_qty == 0


# ---------------------------------------------------------------------------
# Reviews — not supported by WB Seller API
# ---------------------------------------------------------------------------

def test_collect_reviews_raises_api_unavailable(scraper):
    """REVIEWS data type → ScraperError('API_UNAVAILABLE') — not supported by L0."""
    with pytest.raises(ScraperError) as exc_info:
        scraper.collect(NM_ID, DataType.REVIEWS)

    assert exc_info.value.code == "API_UNAVAILABLE"


# ---------------------------------------------------------------------------
# scraper_level attribute
# ---------------------------------------------------------------------------

def test_scraper_level_is_zero(scraper):
    """WBSellerAPIScraper must declare scraper_level=0 (Seller API tier)."""
    assert scraper.scraper_level == 0
