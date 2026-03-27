"""
Auth service — business logic for authentication, token lifecycle, and user info.

No HTTP-layer imports (no HTTPException, no Request). Raises domain exceptions
(AuthError, LockoutError) which the router layer maps to HTTP status codes.
Both exception classes live in core.security so the router can import them from
a single stable location.

Algorithms follow Pseudocode.md section 2 exactly.
Security hardening from Refinement.md sections 1–2.
"""

import asyncio
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
from app.auth.schemas import RefreshResponse, TokenResponse, UserInfo
from app.core.security import (
    AuthError,
    LockoutError,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_timing_dummy_hash,
    verify_password,
)

# ---------------------------------------------------------------------------
# Auth constants
# ---------------------------------------------------------------------------

_LOCKOUT_THRESHOLD: int = 5     # failed attempts before account lockout
_LOCKOUT_DURATION_SECONDS: int = 900   # 15 minutes
_ACCESS_TOKEN_TTL_SECONDS: int = 900   # must match security._ACCESS_TOKEN_TTL

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
    # Offload bcrypt to thread pool so the async event loop is not blocked
    # (~250ms CPU-bound work). asyncio.to_thread runs in the default executor.
    if user is None:
        await asyncio.to_thread(verify_password, "dummy", get_timing_dummy_hash())
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

    # Step 4 — verify password (offloaded to thread pool — bcrypt is CPU-bound)
    password_ok: bool = await asyncio.to_thread(verify_password, password, user.password_hash)

    if not password_ok:
        # Atomic SQL increment avoids read-modify-write race on concurrent attempts
        new_attempts = await UserRepository.increment_failed_attempts(db, user.id)
        if new_attempts >= _LOCKOUT_THRESHOLD:
            lockout_until = datetime.fromtimestamp(
                now.timestamp() + _LOCKOUT_DURATION_SECONDS, tz=timezone.utc
            )
            await UserRepository.set_lockout(db, user.id, new_attempts, lockout_until)
            logger.warning(
                "auth.lockout.triggered",
                extra={"user_id": str(user.id), "attempts": new_attempts},
            )
            raise LockoutError(lockout_until)
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
        expires_in=_ACCESS_TOKEN_TTL_SECONDS,
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
) -> RefreshResponse:
    """
    Token refresh flow — Pseudocode.md Algorithm: refresh_access_token.

    Validates the refresh token (JWT signature + DB state), then issues
    a new access token without touching the refresh token itself
    (multi-use until explicitly revoked on logout — Refinement.md edge case #8).
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
    # Normalize expires_at: SQLite returns naive datetimes; PostgreSQL returns aware.
    expires_at = stored.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        raise AuthError("INVALID_REFRESH_TOKEN")

    # Step 7 — load user (handles deleted-user case — Refinement.md edge case #11)
    user = await UserRepository.get_by_id(db, stored.user_id)
    if user is None:
        raise AuthError("INVALID_REFRESH_TOKEN")

    new_access_token: str = create_access_token(user.id, user.org_id, user.role)

    logger.info("auth.token.refreshed", extra={"user_id": str(user.id)})

    return RefreshResponse(access_token=new_access_token, expires_in=_ACCESS_TOKEN_TTL_SECONDS)


async def revoke_refresh_token(
    db: AsyncSession,
    raw_refresh_token: str,
    current_user_id: UUID,
) -> None:
    """
    Logout flow — Pseudocode.md Algorithm: revoke_refresh_token.

    Idempotent: silently succeeds if the token is not found in the DB.
    Ownership check: refuses to revoke a token belonging to a different user,
    preventing cross-tenant session DoS (Agent 3 review finding M11).
    """
    token_hash = _hash_token(raw_refresh_token)
    stored = await RefreshTokenRepository.get_by_hash(db, token_hash)
    if stored is not None and stored.user_id != current_user_id:
        logger.warning(
            "auth.logout.ownership_mismatch user_id=%s token_owner=%s",
            current_user_id,
            stored.user_id,
        )
        return  # silently ignore — do not reveal token existence to wrong user
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
