"""
Pydantic request/response schemas for the auth domain.

Design rules (Refinement.md § 2, Pseudocode.md § 1):
- LoginRequest enforces min/max length on password — never store or log passwords.
- TokenResponse embeds UserInfo so the frontend has user context on login without
  a separate /me call.
- RefreshResponse returns only the new access_token — the refresh token does NOT
  rotate on each refresh (Architecture.md § 7: tokens are multi-use until revoked).
- No field exposes password_hash, failed_attempts, or locked_until to clients.
- `model_config = ConfigDict(from_attributes=True)` enables ORM model → schema
  conversion via `UserInfo.model_validate(user_orm_instance)`.
"""

import uuid
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pydantic.functional_validators import AfterValidator


def _normalise_email(v: str) -> str:
    """Lowercase and strip whitespace — email is case-insensitive by spec."""
    return v.strip().lower()


# LoginEmail accepts any syntactically valid email without TLD deliverability
# checks. Seeds and dev users may have .local or .demo domains that are valid
# internally but rejected by the stricter EmailStr (email-validator library).
# Registration still uses EmailStr (full validation) — login only needs the
# value to exist in the DB.
LoginEmail = Annotated[str, Field(min_length=3, max_length=255), AfterValidator(_normalise_email)]


# ---------------------------------------------------------------------------
# Shared sub-models
# ---------------------------------------------------------------------------

class UserInfo(BaseModel):
    """
    Slim user representation embedded in login / token responses.

    Contains only the fields the frontend needs to render the UI:
    identity (id, email), access control (role), and tenant scope (org_id, org_name).

    org_name is NOT on the ORM User model — it must be joined from Organization
    and passed explicitly when constructing this schema in the service layer.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="User UUID.")
    email: str = Field(description="User email address.")
    role: str = Field(description="RBAC role: admin | manager | viewer.")
    org_id: uuid.UUID = Field(description="Organisation UUID (tenant scope).")
    org_name: str = Field(description="Human-readable organisation name.")


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    """
    Credentials submitted to POST /api/v1/auth/login.

    email is lowercased by the service layer before DB lookup (Refinement.md § 1,
    edge case 1: email case normalisation).
    """

    email: LoginEmail = Field(
        description="User email address. Case-insensitive — normalised to lowercase.",
    )
    password: str = Field(
        min_length=8,
        max_length=128,
        description=(
            "Plaintext password. Min 8, max 128 characters. "
            "Never logged or stored — only ever passed to bcrypt verify."
        ),
    )


class TokenResponse(BaseModel):
    """
    Successful login response containing both tokens and embedded user context.

    token_type is always "Bearer" per RFC 6750.
    expires_in is in seconds (matches ACCESS_TOKEN_EXPIRE_SECONDS = 900).
    refresh_token is the raw JWT — the client must keep it secret (HttpOnly cookie
    or secure storage). Only the SHA256 hash of this value is stored server-side.
    """

    access_token: str = Field(description="Short-lived JWT access token (15 min).")
    refresh_token: str = Field(description="Long-lived JWT refresh token (7 days).")
    token_type: str = Field(default="Bearer", description="OAuth2 token type.")
    expires_in: int = Field(default=900, description="Access token TTL in seconds.")
    user: UserInfo = Field(description="Authenticated user context.")


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------

class RefreshRequest(BaseModel):
    """Body for POST /api/v1/auth/refresh."""

    refresh_token: str = Field(description="Valid, non-revoked refresh JWT.")


class RefreshResponse(BaseModel):
    """
    New access token issued on a successful refresh.

    The refresh token itself is NOT rotated — it remains valid until its own
    expiry or an explicit logout. (Architecture.md § 7, edge case 8 in Refinement.md)
    """

    access_token: str = Field(description="New short-lived JWT access token (15 min).")
    expires_in: int = Field(default=900, description="Access token TTL in seconds.")


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

class LogoutRequest(BaseModel):
    """
    Body for POST /api/v1/auth/logout.

    The service computes SHA256(refresh_token) and marks the matching DB row
    as revoked. If the token is not found the logout is silently successful
    (idempotent — Pseudocode.md § 2, revoke_refresh_token algorithm).
    """

    refresh_token: str = Field(description="Refresh JWT to revoke.")


# ---------------------------------------------------------------------------
# Switch client context
# ---------------------------------------------------------------------------

class SwitchClientRequest(BaseModel):
    """
    Body for POST /api/v1/auth/switch-client.

    Pass ``client_id`` to scope the new access token to a specific client.
    Pass ``null`` to return to all-clients mode (no client scope in token).
    """

    client_id: Optional[uuid.UUID] = Field(
        default=None,
        description=(
            "UUID of the client to switch to. "
            "Pass null to clear client context (all-clients mode)."
        ),
    )


class SwitchClientTokenResponse(BaseModel):
    """
    Response from POST /api/v1/auth/switch-client.

    Returns only a new access token — the refresh token is unaffected.
    The frontend should replace its stored access token with this value
    and invalidate all cached query results.
    """

    access_token: str = Field(
        description="New short-lived JWT access token (15 min) scoped to the requested client."
    )
    token_type: str = Field(default="bearer", description="OAuth2 token type.")
