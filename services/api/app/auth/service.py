"""
Auth service — business logic for authentication, token lifecycle, and user info.

No HTTP-layer imports (no HTTPException, no Request). Raises domain exceptions
(AuthError, LockoutError) which the router layer maps to HTTP status codes.
Both exception classes live in core.security so the router can import them from
a single stable location.

Algorithms follow Pseudocode.md section 2 exactly.
Security hardening from Refinement.md sections 1–2.
"""

import logging
from datetime import datetime, timezone
from hashlib import sha256
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.repository import (
    OrganizationRepository,
    RefreshTokenRepository,
    UserRepository,
)
from app.auth.schemas import TokenResponse, UserInfo
from app.core.security import (
    AuthError,
    LockoutError,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_timing_dummy_hash,
    verify_password,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _hash_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest of a raw JWT string."""
    return sha256(raw_token.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------

async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
) -> TokenResponse:
    """
    Login flow — Pseudocode.md Algorithm: authenticate_user.

    1.  Normalise email to lowercase (Refinement.md edge case #1).
    2.  Load user; run dummy verify if not found to prevent timing attack.
    3.  Check active lockout.
    4.  Verify password; increment attempts or set lockout on failure.
    5.  On success: reset attempts, issue tokens, return TokenResponse.
    """
    email = email.lower()

    # Step 1 — load user
    user = await UserRepository.get_by_email(db, email)

    # Step 2 — timing-safe "not found" path (Refinement.md section 2)
    # verify_password against a real bcrypt hash burns ~250ms to prevent
    # timing attacks that reveal whether an email exists.
    if user is None:
        verify_password("dummy", get_timing_dummy_hash())
        logger.warning(
            "auth.login.failure",
            extra={"email_domain": email.split("@")[-1], "reason": "INVALID_CREDENTIALS"},
        )
        raise AuthError("INVALID_CREDENTIALS")

    # Step 3 — check existing lockout
    now = _now_utc()
    if user.locked_until is not None and user.locked_until > now:
        logger.warning(
            "auth.login.failure",
            extra={"email_domain": email.split("@")[-1], "reason": "LOCKED"},
        )
        raise LockoutError(user.locked_until)

    # Step 4 — verify password
    password_ok: bool = verify_password(password, user.password_hash)

    if not password_ok:
        new_attempts = user.failed_attempts + 1
        if new_attempts >= 5:
            lockout_until = datetime.fromtimestamp(
                now.timestamp() + 900, tz=timezone.utc
            )
            await UserRepository.set_lockout(db, user.id, new_attempts, lockout_until)
            logger.warning(
                "auth.lockout.triggered",
                extra={"user_id": str(user.id), "attempts": new_attempts},
            )
            raise LockoutError(lockout_until)
        else:
            await UserRepository.increment_failed_attempts(db, user.id, new_attempts)
            logger.warning(
                "auth.login.failure",
                extra={
                    "email_domain": email.split("@")[-1],
                    "reason": "INVALID_CREDENTIALS",
                },
            )
            raise AuthError("INVALID_CREDENTIALS")

    # Step 5 — successful authentication: reset lockout state
    await UserRepository.reset_failed_attempts(db, user.id)

    # Issue tokens
    access_token: str = create_access_token(user.id, user.org_id, user.role)
    raw_refresh, token_hash, expires_at = create_refresh_token(user.id)
    await RefreshTokenRepository.create(db, user.id, token_hash, expires_at)

    # Load org name for UserInfo
    org = await OrganizationRepository.get_by_id(db, user.org_id)
    org_name: str = org.name if org is not None else ""

    logger.info(
        "auth.login.success",
        extra={"user_id": str(user.id), "org_id": str(user.org_id)},
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        token_type="Bearer",
        expires_in=900,
        user=UserInfo(
            id=user.id,
            email=user.email,
            role=user.role,
            org_id=user.org_id,
            org_name=org_name,
        ),
    )


async def refresh_access_token(
    db: AsyncSession,
    raw_refresh_token: str,
) -> str:
    """
    Token refresh flow — Pseudocode.md Algorithm: refresh_access_token.

    Validates the refresh token (JWT signature + DB state), then issues
    a new access token without touching the refresh token itself
    (multi-use until explicitly revoked on logout — Refinement.md edge case #8).

    Returns the raw access token string; the router wraps it in RefreshResponse.
    """
    # Step 1 — validate JWT signature and type claim
    try:
        decode_token(raw_refresh_token, expected_type="refresh")
    except AuthError:
        raise AuthError("INVALID_REFRESH_TOKEN")

    # Step 2 — look up in DB by hash
    token_hash = _hash_token(raw_refresh_token)
    stored = await RefreshTokenRepository.get_by_hash(db, token_hash)

    if stored is None:
        raise AuthError("INVALID_REFRESH_TOKEN")
    if stored.revoked:
        raise AuthError("INVALID_REFRESH_TOKEN")

    now = _now_utc()
    if stored.expires_at < now:
        raise AuthError("INVALID_REFRESH_TOKEN")

    # Step 7 — load user (handles deleted-user case — Refinement.md edge case #11)
    user = await UserRepository.get_by_id(db, stored.user_id)
    if user is None:
        raise AuthError("INVALID_REFRESH_TOKEN")

    new_access_token: str = create_access_token(user.id, user.org_id, user.role)

    logger.info("auth.token.refreshed", extra={"user_id": str(user.id)})

    return new_access_token


async def revoke_refresh_token(
    db: AsyncSession,
    raw_refresh_token: str,
) -> None:
    """
    Logout flow — Pseudocode.md Algorithm: revoke_refresh_token.

    Idempotent: silently succeeds if the token is not found in the DB.
    """
    token_hash = _hash_token(raw_refresh_token)
    await RefreshTokenRepository.revoke(db, token_hash)


async def get_user_info(
    db: AsyncSession,
    user: User,
) -> UserInfo:
    """
    Return public user information for the /me endpoint.

    Accepts the User ORM object already loaded by get_current_user dependency
    (avoids a redundant DB round-trip). Loads org name separately.

    Raises AuthError("USER_NOT_FOUND") if the user has been deleted since
    the JWT was issued — callers should map this to 401 (Refinement.md edge case #11).
    """
    org = await OrganizationRepository.get_by_id(db, user.org_id)
    org_name: str = org.name if org is not None else ""

    return UserInfo(
        id=user.id,
        email=user.email,
        role=user.role,
        org_id=user.org_id,
        org_name=org_name,
    )
