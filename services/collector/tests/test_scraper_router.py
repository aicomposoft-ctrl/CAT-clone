"""
Unit tests for ScraperRouter — adaptive fallback pipeline.

All DB access is mocked with MagicMock. No real HTTP calls, no real DB.
Tests cover:
  - Happy-path L0 success (no fallback needed)
  - L0 TOKEN_INVALID → fallback to L1
  - ALL_LEVELS_FAILED when every level raises retriable error
  - Multi-tenant isolation: OrgPlatformCredentials always filtered by org_id (CRITICAL)
  - Non-retriable PARSE_ERROR propagates immediately without fallback
  - Default chain selection based on token presence
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch, call
from uuid import UUID

import pytest
from sqlalchemy import Select

from app.core.base_scraper import ContentData, DataType, ScraperError, StockData
from app.core.scraper_router import ScraperRouter
from app.models import OrgPlatformCredentials, Platform


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _make_platform(name: str = "Wildberries") -> Platform:
    p = MagicMock(spec=Platform)
    p.id = uuid.uuid4()
    p.name = name
    return p


def _make_creds(
    *,
    api_token_encrypted: str | None = "enc_token",
    api_token_type: str = "wb_seller",
    fallback_chain: list[str] | None = None,
) -> OrgPlatformCredentials:
    c = MagicMock(spec=OrgPlatformCredentials)
    c.api_token_encrypted = api_token_encrypted
    c.api_token_type = api_token_type
    c.fallback_chain = fallback_chain
    c.selectors = {}
    return c


def _make_content_data() -> ContentData:
    return ContentData(
        title="Test Product",
        description="A fine product",
        composition=None,
        image_url="https://cdn.wbstatic.net/big/photo.jpg",
    )


def _make_db(platform: Platform, creds: OrgPlatformCredentials | None):
    """
    Build a mock DB session where:
      - db.get(Platform, id) returns platform
      - db.execute(...).scalar_one_or_none() returns creds
    """
    db = MagicMock()
    db.get.return_value = platform
    db.execute.return_value.scalar_one_or_none.return_value = creds
    return db


# ---------------------------------------------------------------------------
# Test: L0 success — no fallback triggered
# ---------------------------------------------------------------------------

def test_collect_uses_l0_when_token_present():
    """L0 scraper returns result on first try; no fallback levels are attempted."""
    platform = _make_platform()
    creds = _make_creds(api_token_encrypted="tok", api_token_type="wb_seller")
    db = _make_db(platform, creds)

    expected = _make_content_data()

    mock_scraper = MagicMock()
    mock_scraper.scraper_level = 0
    mock_scraper.collect.return_value = expected

    with patch.object(ScraperRouter, "_instantiate", return_value=mock_scraper):
        router = ScraperRouter(db)
        # Force chain to ["l0"] so we don't need to stub l2
        with patch.object(router, "_build_chain", return_value=["l0"]):
            result = router.collect(platform.id, "12345", DataType.CONTENT, uuid.uuid4())

    mock_scraper.collect.assert_called_once_with("12345", DataType.CONTENT)
    assert result.title == "Test Product"


# ---------------------------------------------------------------------------
# Test: L0 TOKEN_INVALID → fallback to L1
# ---------------------------------------------------------------------------

def test_collect_falls_back_to_l1_on_token_invalid():
    """TOKEN_INVALID from L0 triggers fallback; L1 returns success."""
    platform = _make_platform()
    creds = _make_creds()
    db = _make_db(platform, creds)

    l0_scraper = MagicMock()
    l0_scraper.scraper_level = 0
    l0_scraper.collect.side_effect = ScraperError("TOKEN_INVALID", "expired")

    l1_scraper = MagicMock()
    l1_scraper.scraper_level = 1
    expected = _make_content_data()
    # L1 is async; _invoke wraps it with asyncio.run
    # We mock _invoke directly to avoid needing a real event loop
    with (
        patch.object(ScraperRouter, "_instantiate") as mock_instantiate,
        patch.object(ScraperRouter, "_invoke") as mock_invoke,
    ):
        def instantiate_side_effect(level, platform, creds, org_id=None):
            if level == "l0":
                return l0_scraper
            if level == "l1":
                return l1_scraper
            return None

        def invoke_side_effect(scraper, sku_id, data_type):
            if scraper is l0_scraper:
                raise ScraperError("TOKEN_INVALID", "expired")
            return expected

        mock_instantiate.side_effect = instantiate_side_effect
        mock_invoke.side_effect = invoke_side_effect

        router = ScraperRouter(db)
        with patch.object(router, "_build_chain", return_value=["l0", "l1"]):
            result = router.collect(platform.id, "12345", DataType.CONTENT, uuid.uuid4())

    assert result.title == "Test Product"
    # Both levels were attempted
    assert mock_invoke.call_count == 2


# ---------------------------------------------------------------------------
# Test: ALL_LEVELS_FAILED
# ---------------------------------------------------------------------------

def test_collect_raises_all_levels_failed():
    """All scrapers in chain fail with retriable errors → ALL_LEVELS_FAILED raised."""
    platform = _make_platform()
    creds = _make_creds()
    db = _make_db(platform, creds)

    with (
        patch.object(ScraperRouter, "_instantiate") as mock_instantiate,
        patch.object(ScraperRouter, "_invoke") as mock_invoke,
    ):
        mock_scraper = MagicMock()
        mock_scraper.scraper_level = 1
        mock_instantiate.return_value = mock_scraper
        mock_invoke.side_effect = ScraperError("API_UNAVAILABLE", "connection refused")

        router = ScraperRouter(db)
        with patch.object(router, "_build_chain", return_value=["l1", "l2"]):
            with pytest.raises(ScraperError) as exc_info:
                router.collect(platform.id, "12345", DataType.CONTENT, uuid.uuid4())

    assert exc_info.value.code == "ALL_LEVELS_FAILED"


# ---------------------------------------------------------------------------
# Test: Multi-tenant isolation — CRITICAL
# ---------------------------------------------------------------------------

def test_collect_org_isolation():
    """
    CRITICAL: _load_creds MUST filter OrgPlatformCredentials by BOTH platform_id
    AND org_id. This verifies the WHERE clause includes both columns.
    """
    platform_id = uuid.uuid4()
    org_id = uuid.uuid4()

    platform = _make_platform()
    platform.id = platform_id

    db = MagicMock()
    db.get.return_value = platform
    db.execute.return_value.scalar_one_or_none.return_value = None  # no creds

    router = ScraperRouter(db)

    # Patch _build_chain so collect() doesn't need a real scraper
    with patch.object(router, "_build_chain", return_value=[]):
        # Will raise ALL_LEVELS_FAILED since chain is empty, but that's fine —
        # we only care that the DB query was issued with org_id
        with pytest.raises(ScraperError) as exc_info:
            router.collect(platform_id, "12345", DataType.CONTENT, org_id)

    assert exc_info.value.code == "ALL_LEVELS_FAILED"

    # Verify db.execute was called once (for creds lookup)
    assert db.execute.call_count == 1
    stmt = db.execute.call_args[0][0]  # first positional arg is the SELECT statement

    # Inspect the WHERE clauses of the SQLAlchemy select statement
    # The statement must reference OrgPlatformCredentials.org_id and platform_id
    stmt_str = str(stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "org_platform_credentials.org_id" in stmt_str, (
        "org_id filter MISSING from OrgPlatformCredentials query — multi-tenant isolation broken!"
    )
    assert "org_platform_credentials.platform_id" in stmt_str, (
        "platform_id filter MISSING from OrgPlatformCredentials query"
    )


# ---------------------------------------------------------------------------
# Test: Non-retriable error propagates immediately
# ---------------------------------------------------------------------------

def test_collect_non_retriable_error_propagates():
    """
    PARSE_ERROR is not in _FALLBACK_CODES → must propagate immediately
    without attempting subsequent scraper levels.
    """
    platform = _make_platform()
    creds = _make_creds()
    db = _make_db(platform, creds)

    with (
        patch.object(ScraperRouter, "_instantiate") as mock_instantiate,
        patch.object(ScraperRouter, "_invoke") as mock_invoke,
    ):
        mock_scraper = MagicMock()
        mock_scraper.scraper_level = 0
        mock_instantiate.return_value = mock_scraper
        mock_invoke.side_effect = ScraperError("PARSE_ERROR", "unexpected JSON")

        router = ScraperRouter(db)
        with patch.object(router, "_build_chain", return_value=["l0", "l1"]):
            with pytest.raises(ScraperError) as exc_info:
                router.collect(platform.id, "12345", DataType.CONTENT, uuid.uuid4())

    assert exc_info.value.code == "PARSE_ERROR"
    # Only first level was tried — no fallback to l1
    assert mock_invoke.call_count == 1


# ---------------------------------------------------------------------------
# Test: _default_chain logic
# ---------------------------------------------------------------------------

def test_default_chain_with_token():
    """When creds has an api_token_encrypted, default chain is ['l0', 'l2']."""
    db = MagicMock()
    router = ScraperRouter(db)

    creds = _make_creds(api_token_encrypted="some_enc_token")
    chain = router._default_chain(creds)

    assert chain == ["l0", "l2"]


def test_default_chain_without_token():
    """When creds has no api_token_encrypted (or no creds at all), chain is ['l1', 'l2']."""
    db = MagicMock()
    router = ScraperRouter(db)

    # No creds
    assert router._default_chain(None) == ["l1", "l2"]

    # Creds but no token
    creds_no_token = _make_creds(api_token_encrypted=None)
    assert router._default_chain(creds_no_token) == ["l1", "l2"]


# ---------------------------------------------------------------------------
# Test: Per-org fallback_chain override
# ---------------------------------------------------------------------------

def test_custom_fallback_chain_override():
    """Explicit fallback_chain in creds overrides the default chain."""
    db = MagicMock()
    router = ScraperRouter(db)

    creds = _make_creds(fallback_chain=["l0", "l1", "l2"])
    chain = router._build_chain(creds)

    assert chain == ["l0", "l1", "l2"]


def test_invalid_fallback_chain_falls_back_to_default():
    """Malformed fallback_chain (not a list of strings) falls back to default chain."""
    db = MagicMock()
    router = ScraperRouter(db)

    creds = _make_creds(api_token_encrypted="tok", fallback_chain="not-a-list")
    chain = router._build_chain(creds)

    # Malformed → default chain for creds-with-token
    assert chain == ["l0", "l2"]
