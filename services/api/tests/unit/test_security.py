"""
Unit tests for app.core.security — JWT encode/decode, bcrypt, timing guard.
No DB, no HTTP. Pure function tests.
"""

import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.core.security import (
    AuthError,
    LockoutError,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_timing_dummy_hash,
    hash_password,
    verify_password,
)

ORG_ID = uuid4()
USER_ID = uuid4()


# ── create_access_token ────────────────────────────────────────────────────────

def test_create_access_token_returns_string():
    token = create_access_token(USER_ID, ORG_ID, "manager")
    assert isinstance(token, str)
    assert len(token) > 20


def test_create_access_token_payload_fields():
    token = create_access_token(USER_ID, ORG_ID, "manager")
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == str(USER_ID)
    assert payload["org_id"] == str(ORG_ID)
    assert payload["role"] == "manager"
    assert payload["type"] == "access"


def test_create_access_token_expiry_is_15_minutes():
    before = int(time.time())
    token = create_access_token(USER_ID, ORG_ID, "viewer")
    payload = decode_token(token, expected_type="access")
    after = int(time.time())
    assert 900 <= payload["exp"] - before <= 900 + (after - before) + 1


# ── create_refresh_token ───────────────────────────────────────────────────────

def test_create_refresh_token_returns_tuple():
    raw_token, token_hash, expires_at = create_refresh_token(USER_ID)
    assert isinstance(raw_token, str)
    assert isinstance(token_hash, str)
    assert isinstance(expires_at, datetime)


def test_create_refresh_token_hash_is_sha256_hex():
    _, token_hash, _ = create_refresh_token(USER_ID)
    assert len(token_hash) == 64
    assert all(c in "0123456789abcdef" for c in token_hash)


def test_create_refresh_token_expiry_is_7_days():
    _, _, expires_at = create_refresh_token(USER_ID)
    now = datetime.now(timezone.utc)
    delta_seconds = (expires_at - now).total_seconds()
    assert 604800 - 5 <= delta_seconds <= 604800 + 5


def test_create_refresh_token_has_jti():
    raw_token, _, _ = create_refresh_token(USER_ID)
    payload = decode_token(raw_token, expected_type="refresh")
    assert "jti" in payload
    UUID(payload["jti"])  # must be valid UUID


# ── decode_token ───────────────────────────────────────────────────────────────

def test_decode_token_valid_access():
    token = create_access_token(USER_ID, ORG_ID, "admin")
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == str(USER_ID)


def test_decode_token_wrong_type_raises():
    access_token = create_access_token(USER_ID, ORG_ID, "manager")
    with pytest.raises(AuthError):
        decode_token(access_token, expected_type="refresh")


def test_decode_token_tampered_raises():
    token = create_access_token(USER_ID, ORG_ID, "viewer")
    # Flip a character in the signature part
    parts = token.split(".")
    parts[2] = parts[2][:-1] + ("A" if parts[2][-1] != "A" else "B")
    tampered = ".".join(parts)
    with pytest.raises(AuthError):
        decode_token(tampered, expected_type="access")


def test_decode_token_garbage_raises():
    with pytest.raises(AuthError):
        decode_token("not.a.jwt", expected_type="access")


# ── hash_password / verify_password ───────────────────────────────────────────

def test_hash_password_returns_bcrypt_string():
    h = hash_password("S3cr3t!")
    assert h.startswith("$2b$")


def test_hash_differs_from_plain():
    h = hash_password("password")
    assert h != "password"


def test_verify_password_correct():
    h = hash_password("correcthorse")
    assert verify_password("correcthorse", h) is True


def test_verify_password_wrong():
    h = hash_password("correcthorse")
    assert verify_password("wronghorse", h) is False


def test_verify_password_empty():
    h = hash_password("nonempty")
    assert verify_password("", h) is False


# ── timing dummy hash ──────────────────────────────────────────────────────────

def test_timing_dummy_hash_is_valid_bcrypt():
    dummy = get_timing_dummy_hash()
    assert dummy.startswith("$2b$")
    # Verify it's a real hash — verify_password must not crash
    result = verify_password("anything", dummy)
    assert result is False  # wrong password, but hash is valid


def test_timing_dummy_hash_is_stable():
    # Same object returned each call (computed at module level)
    assert get_timing_dummy_hash() == get_timing_dummy_hash()


# ── exception classes ─────────────────────────────────────────────────────────

def test_auth_error_message():
    exc = AuthError("INVALID_CREDENTIALS")
    assert str(exc) == "INVALID_CREDENTIALS"


def test_lockout_error_has_lockout_until():
    dt = datetime.now(timezone.utc)
    exc = LockoutError(dt)
    assert exc.lockout_until == dt
