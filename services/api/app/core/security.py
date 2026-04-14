"""
Core security utilities for CAT API: JWT operations and password hashing.

Design decisions (from Architecture.md § 7):
- Algorithm: HS256 (symmetric, sufficient for single-service)
- Refresh tokens: returned as (raw, sha256_hash, expires_at); only the hash is stored in DB
- Bcrypt cost: 12 (hardcoded — NOT read from config to prevent accidental weakening)
- Timing attack mitigation: DUMMY_HASH is computed once at module load with real bcrypt cost=12

No DB access. Pure functions — fully unit-testable without application context.
"""

import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ALGORITHM = "HS256"
_ACCESS_TOKEN_TTL = 900       # 15 minutes — matches Architecture.md § 6
_REFRESH_TOKEN_TTL = 604800   # 7 days    — matches Architecture.md § 6

# Bcrypt cost is HARDCODED at 12. Do not source from config — a misconfigured
# env var could silently reduce security. (Refinement.md § 2)
_BCRYPT_COST = 12

# ---------------------------------------------------------------------------
# Passlib context — bcrypt only, no deprecated schemes
# ---------------------------------------------------------------------------

_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=_BCRYPT_COST,
)

# ---------------------------------------------------------------------------
# Timing attack mitigation (Refinement.md § 2)
#
# DUMMY_HASH must be a real bcrypt hash computed at cost=12 so that
# verify_password("dummy", DUMMY_HASH) takes ~250ms — the same wall-clock time
# as a legitimate bcrypt verify. A fake string would return instantly and
# leak user existence via timing analysis.
# ---------------------------------------------------------------------------

_DUMMY_TIMING_GUARD_HASH: str = _pwd_context.hash("_dummy_timing_guard_")


def get_timing_dummy_hash() -> str:
    """
    Return the module-level bcrypt hash of "_dummy_timing_guard_" (cost=12).

    Use this in authenticate_user when the email is not found to avoid timing
    attacks that would reveal whether an email exists in the system.

    Example:
        user = await user_repo.get_by_email(db, email)
        if user is None:
            verify_password("dummy", get_timing_dummy_hash())  # ~250ms burn
            raise AuthError("INVALID_CREDENTIALS")
    """
    return _DUMMY_TIMING_GUARD_HASH


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _jwt_secret() -> str:
    """
    Load JWT_SECRET from environment at call time.

    Raises KeyError if missing — validate_required_secrets() in main.py
    catches this before any requests are served.
    """
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise RuntimeError(
            "JWT_SECRET environment variable is not set. "
            "Call validate_required_secrets() at startup."
        )
    return secret


def _utcnow_ts() -> int:
    """Return the current UTC time as a Unix timestamp (integer seconds)."""
    return int(datetime.now(tz=timezone.utc).timestamp())


def _utcnow_dt() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Auth context — carries user + resolved tenant/client scope
# ---------------------------------------------------------------------------

@dataclass
class AuthContext:
    """
    Dependency injection payload returned by get_current_user.

    Replaces the bare User object so downstream code has access to
    org_id and the optional client_id JWT claim without extra DB queries.

    Fields:
        user      — ORM User instance (loaded from DB).
        org_id    — convenience alias for user.org_id (avoids attribute chains).
        client_id — UUID extracted from the "client_id" JWT claim, or None when
                    the token was issued without a client context (all-clients mode).
    """

    user: Any           # app.auth.models.User — typed as Any to avoid import cycle
    org_id: UUID
    client_id: UUID | None

    def __getattr__(self, name: str) -> Any:
        """Delegate unknown attribute access to the wrapped User object.

        Allows existing code written against ``User`` (e.g. ``ctx.id``,
        ``ctx.role``, ``ctx.email``) to continue working without modification
        after the dependency was updated to return ``AuthContext``.
        """
        # __getattr__ is only called when normal lookup fails, so dataclass
        # fields (user, org_id, client_id) are never caught here.
        try:
            return getattr(self.user, name)
        except AttributeError:
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}'"
            ) from None


# ---------------------------------------------------------------------------
# JWT — Access Token
# ---------------------------------------------------------------------------

def create_access_token(
    user_id: UUID,
    org_id: UUID,
    role: str,
    client_id: UUID | None = None,
) -> str:
    """
    Create a signed JWT access token.

    Payload fields (Architecture.md § 6):
        sub       — user UUID (string)
        org_id    — organisation UUID (string)
        role      — RBAC role: "admin" | "manager" | "viewer"
        type      — "access" (used by decode_token to reject wrong-type tokens)
        iat       — issued-at (Unix timestamp)
        exp       — expiry (iat + 900 seconds)
        client_id — (optional) client UUID string; omitted when None

    Args:
        user_id:   UUID of the authenticated user.
        org_id:    UUID of the user's organisation (tenant scope).
        role:      RBAC role string.
        client_id: Optional client UUID to scope the token to a single client.
                   Pass None (default) for all-clients mode (backward compatible).

    Returns:
        Signed HS256 JWT string.
    """
    now = _utcnow_ts()
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "org_id": str(org_id),
        "role": role,
        "type": "access",
        "jti": str(uuid4()),  # unique per token — prevents replay detection gaps
        "iat": now,
        "exp": now + _ACCESS_TOKEN_TTL,
    }
    if client_id is not None:
        payload["client_id"] = str(client_id)
    return jwt.encode(payload, _jwt_secret(), algorithm=_ALGORITHM)


# ---------------------------------------------------------------------------
# JWT — Refresh Token
# ---------------------------------------------------------------------------

def create_refresh_token(user_id: UUID) -> tuple[str, str, datetime]:
    """
    Create a signed JWT refresh token and its SHA-256 storage hash.

    Only the hash is stored in the database (Architecture.md § 7).
    A DB breach therefore does not yield usable tokens.

    Payload fields (Architecture.md § 6):
        sub   — user UUID (string)
        jti   — unique token ID (UUID4); enables per-token revocation
        type  — "refresh"
        iat   — issued-at (Unix timestamp)
        exp   — expiry (iat + 604800 seconds)

    Args:
        user_id: UUID of the authenticated user.

    Returns:
        Tuple of:
            raw_token   — the JWT string to return to the client
            token_hash  — SHA-256 hex digest of raw_token (store this in DB)
            expires_at  — aware datetime of token expiry (store in refresh_tokens table)
    """
    now = _utcnow_ts()
    jti = str(uuid4())
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "jti": jti,
        "type": "refresh",
        "iat": now,
        "exp": now + _REFRESH_TOKEN_TTL,
    }
    raw_token: str = jwt.encode(payload, _jwt_secret(), algorithm=_ALGORITHM)
    token_hash: str = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at: datetime = datetime.fromtimestamp(now + _REFRESH_TOKEN_TTL, tz=timezone.utc)
    return raw_token, token_hash, expires_at


# ---------------------------------------------------------------------------
# JWT — Decode and Validate
# ---------------------------------------------------------------------------

class AuthError(Exception):
    """
    Domain error for authentication failures.

    Carry a machine-readable code (e.g. "TOKEN_EXPIRED", "INVALID_TOKEN").
    Routers catch this and convert to HTTPException — never expose
    stack traces to clients.
    """

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(code)


class LockoutError(Exception):
    """
    Raised when a user account is locked out after repeated failed login attempts.

    lockout_until: timezone-aware datetime when the lockout expires.
    Routers should convert this to HTTP 423 with an X-Lockout-Until header.
    """

    def __init__(self, lockout_until: datetime) -> None:
        self.lockout_until = lockout_until
        super().__init__(f"Account locked until {lockout_until.isoformat()}")


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    """
    Decode and validate a JWT, verifying its type field.

    Args:
        token:         Raw JWT string (without "Bearer " prefix).
        expected_type: "access" or "refresh". Raises if the token carries
                       a different type (prevents refresh tokens being used
                       as access tokens and vice-versa).

    Returns:
        Decoded payload dict.

    Raises:
        AuthError("TOKEN_EXPIRED")   — signature valid but exp in the past
        AuthError("INVALID_TOKEN")   — bad signature, malformed, or wrong algorithm
        AuthError("WRONG_TOKEN_TYPE") — type field does not match expected_type
    """
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=[_ALGORITHM],
        )
    except ExpiredSignatureError:
        raise AuthError("TOKEN_EXPIRED", "Token has expired")
    except JWTError as exc:
        logger.debug("JWT decode failure: %s", exc)
        raise AuthError("INVALID_TOKEN", "Token is invalid or tampered")

    if payload.get("type") != expected_type:
        raise AuthError(
            "WRONG_TOKEN_TYPE",
            f"Expected token type '{expected_type}', got '{payload.get('type')}'",
        )

    return payload


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    """
    Hash a plaintext password using bcrypt at cost=12.

    Cost is hardcoded — not sourced from config — to prevent accidental
    weakening via misconfigured environment variables. (Refinement.md § 2)

    Args:
        plain: Plaintext password string (Pydantic enforces min_length=8
               before this function is called).

    Returns:
        bcrypt hash string suitable for storage in users.password_hash.
    """
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """
    Verify a plaintext password against a stored bcrypt hash.

    Takes ~250ms at cost=12 — this is intentional and blocks brute force.
    Always call this even when the user is not found (pass get_timing_dummy_hash())
    to prevent timing-based user enumeration. (Refinement.md § 2)

    Args:
        plain:  Plaintext candidate password.
        hashed: bcrypt hash from users.password_hash.

    Returns:
        True if the password matches, False otherwise.
    """
    return _pwd_context.verify(plain, hashed)
