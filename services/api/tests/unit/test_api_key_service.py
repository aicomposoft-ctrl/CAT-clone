"""
Unit tests for the generate_api_key() pure function in app.api_keys.service.

No DB, no async, no HTTP — pure function tests only.
"""

import hashlib

from app.api_keys.service import generate_api_key


# ---------------------------------------------------------------------------
# Format tests
# ---------------------------------------------------------------------------


def test_generate_api_key_format_live():
    """Full key starts with 'cat_live_', prefix is 8 chars, hash is 64-char hex."""
    full_key, prefix, key_hash = generate_api_key("live")

    assert full_key.startswith("cat_live_"), (
        f"Expected key to start with 'cat_live_', got: {full_key[:20]!r}"
    )
    assert len(prefix) == 8, f"Expected prefix length 8, got {len(prefix)}"
    assert len(key_hash) == 64, f"Expected hash length 64 (SHA-256 hex), got {len(key_hash)}"
    assert all(c in "0123456789abcdef" for c in key_hash), (
        "key_hash must be lowercase hex digits only"
    )


def test_generate_api_key_format_test():
    """Full key starts with 'cat_test_' when env='test'."""
    full_key, prefix, key_hash = generate_api_key("test")

    assert full_key.startswith("cat_test_"), (
        f"Expected key to start with 'cat_test_', got: {full_key[:20]!r}"
    )
    assert len(prefix) == 8
    assert len(key_hash) == 64


# ---------------------------------------------------------------------------
# Uniqueness test
# ---------------------------------------------------------------------------


def test_generate_api_key_uniqueness():
    """100 independently generated keys must all be distinct."""
    keys = {generate_api_key("live")[0] for _ in range(100)}
    assert len(keys) == 100, (
        "Expected 100 unique keys — collision detected (cryptographic failure or broken PRNG)"
    )


# ---------------------------------------------------------------------------
# Cryptographic correctness tests
# ---------------------------------------------------------------------------


def test_generate_api_key_hash_is_sha256_of_full_key():
    """Returned hash must equal hashlib.sha256(full_key.encode()).hexdigest()."""
    full_key, _, key_hash = generate_api_key("live")
    expected_hash = hashlib.sha256(full_key.encode()).hexdigest()
    assert key_hash == expected_hash, (
        "key_hash does not match SHA-256 of the full key — "
        "DB-stored hash will not match incoming requests"
    )


def test_generate_api_key_prefix_is_first_8_chars_of_raw():
    """Prefix must be the first 8 characters of the raw token (after 'cat_live_')."""
    full_key, prefix, _ = generate_api_key("live")

    # The raw portion follows "cat_live_" (9 chars)
    raw = full_key[len("cat_live_"):]
    assert prefix == raw[:8], (
        f"Expected prefix={raw[:8]!r} (raw[:8]), got {prefix!r}"
    )
