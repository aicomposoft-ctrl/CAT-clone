"""
JWT Token Type Enforcement
==========================

Pattern: decode_token(token, expected_type) validates BOTH signature AND token type.
Prevents refresh tokens from being used as access tokens and vice-versa.

When to use:
  - Any JWT system with multiple token types (access + refresh, or access + API token)
  - When token misuse (e.g. replaying a refresh token as an access token) is a risk

When NOT to use:
  - Single-token systems with no token types
  - When using opaque tokens (not JWTs)

Prerequisites: python-jose[cryptography]

Maturity: 🔴 Alpha
Source: CAT (core/security.py), 2026-04-05
"""

from jose import ExpiredSignatureError, JWTError, jwt
from typing import Any


class AuthError(Exception):
    """Domain authentication error with machine-readable code."""
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(code)


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    """
    Decode and validate a JWT, verifying its type claim.

    Args:
        token:         Raw JWT string (without "Bearer " prefix).
        expected_type: "access" or "refresh". Raises if the payload's
                       "type" field does not match.

    Returns:
        Decoded payload dict.

    Raises:
        AuthError("TOKEN_EXPIRED")    — valid signature, expired
        AuthError("INVALID_TOKEN")    — bad signature or malformed
        AuthError("WRONG_TOKEN_TYPE") — type field mismatch
    """
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            _get_secret(),           # load secret from env, never hardcode
            algorithms=["HS256"],
        )
    except ExpiredSignatureError:
        raise AuthError("TOKEN_EXPIRED", "Token has expired")
    except JWTError as exc:
        raise AuthError("INVALID_TOKEN", "Token is invalid or tampered")

    if payload.get("type") != expected_type:
        raise AuthError(
            "WRONG_TOKEN_TYPE",
            f"Expected token type '{expected_type}', got '{payload.get('type')}'",
        )

    return payload


# --- Token creation (always embed "type" claim) ---

def create_access_token(user_id: str, org_id: str, role: str, secret: str) -> str:
    import time
    now = int(time.time())
    payload = {
        "sub": user_id,
        "org_id": org_id,
        "role": role,
        "type": "access",    # <-- embed token type
        "iat": now,
        "exp": now + 900,    # 15 minutes
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def create_refresh_token(user_id: str, secret: str) -> str:
    import time
    from uuid import uuid4
    now = int(time.time())
    payload = {
        "sub": user_id,
        "jti": str(uuid4()),
        "type": "refresh",   # <-- different type
        "iat": now,
        "exp": now + 604800,  # 7 days
    }
    return jwt.encode(payload, secret, algorithm="HS256")


# --- Usage ---

# In FastAPI dependency:
# payload = decode_token(bearer_token, expected_type="access")   # access route
# payload = decode_token(bearer_token, expected_type="refresh")  # /refresh route


def _get_secret() -> str:
    """Load JWT secret from environment — never hardcode."""
    import os
    s = os.environ.get("JWT_SECRET")
    if not s:
        raise RuntimeError("JWT_SECRET not set")
    return s
