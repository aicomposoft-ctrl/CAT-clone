"""
FastAPI dependencies for CAT API.

Provides:
  - get_db: yields AsyncSession per request
  - get_current_user: decodes JWT access token → returns authenticated User
  - require_role: factory that produces a dependency enforcing RBAC
  - get_org_by_api_key: validates X-API-Key header → returns Organization
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Organization, User
from app.auth.repository import UserRepository
from app.core.database import AsyncSessionLocal
from app.core.security import AuthContext, AuthError, decode_token

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession; rollback on exception, always close."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    """
    Decode Bearer access token and return an AuthContext.

    Behaviour (Pseudocode.md § Client Context Injection):
    1. Decode JWT, validate signature and type.
    2. Load User from DB.
    3. Extract optional ``client_id`` claim from JWT payload.
    4. If client_id is present, validate the client belongs to the user's org
       and is active — raises 401 INVALID_CLIENT_CONTEXT on failure (treats
       a forged/stale claim as an authentication failure, not authorisation).
    5. Return AuthContext(user, org_id, client_id).

    ClientRepository is imported lazily inside this function to prevent
    a circular-import cycle: clients → deps → clients.

    Raises:
        HTTPException(401): invalid/expired token, missing user, or bad client claim.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="UNAUTHORIZED",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_token(token, expected_type="access")
    except AuthError:
        raise credentials_exception

    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError):
        raise credentials_exception

    user = await UserRepository.get_by_id(db, user_id)
    if user is None:
        raise credentials_exception

    # --- Extract optional client_id claim (multi-client-support feature) -----
    raw_cid = payload.get("client_id")
    client_id: UUID | None = None
    if raw_cid is not None:
        try:
            client_id = UUID(raw_cid)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="INVALID_CLIENT_CONTEXT",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Validate client belongs to user's org and is still active.
        # Lazy import to avoid circular dependency: clients.repository → core.deps.
        from app.clients.repository import ClientRepository  # noqa: PLC0415

        client = await ClientRepository.get_active_by_id_and_org(
            db, client_id, user.org_id
        )
        if client is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="INVALID_CLIENT_CONTEXT",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return AuthContext(user=user, org_id=user.org_id, client_id=client_id)


def get_user(ctx: AuthContext = Depends(get_current_user)) -> User:
    """
    Thin compatibility shim — returns just the User from the AuthContext.

    Use this in routes that only need the User object and do not need
    client-context awareness (e.g. /auth/logout, /auth/me).
    New code should prefer ``Depends(get_current_user)`` → ``AuthContext``.
    """
    return ctx.user


def require_role(*roles: str):
    """
    Dependency factory for role-based access control.

    Returns ``AuthContext`` so callers have access to ``ctx.org_id`` and
    ``ctx.client_id`` without an extra dependency.

    Usage::

        @router.delete("/skus/{id}")
        async def delete_sku(ctx: AuthContext = Depends(require_role("admin", "manager"))):
            user = ctx.user
            ...

    Raises HTTPException(403) when the authenticated user's role is not in *roles*.
    """
    def checker(ctx: AuthContext = Depends(get_current_user)) -> AuthContext:
        if ctx.user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="INSUFFICIENT_PERMISSIONS",
            )
        return ctx

    return checker


async def get_org_by_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """
    Validate an X-API-Key header and return the associated Organization.

    Used by all /api/v1/public/* endpoints as the authentication dependency.
    The returned Organization carries org_id for all subsequent DB queries —
    there is no User context in the public API (Architecture.md § 10).

    Validation steps (Pseudocode.md § get_org_by_api_key):
    1. Extract X-API-Key header → 401 MISSING_API_KEY if absent
    2. Validate format prefix (cat_live_ or cat_test_) and minimum length → 401 INVALID_API_KEY
    3. Extract display prefix (chars 9-16 of raw key)
    4. [Rate limiting placeholder — see TODO below]
    5. Hash full key with SHA-256, look up in api_keys table → 401 INVALID_API_KEY if miss
    6. Check revoked flag → 401 API_KEY_REVOKED
    7. Check expires_at < now → 401 API_KEY_EXPIRED
    8. Update last_used_at asynchronously (fire-and-forget, non-blocking)
    9. Load and return the Organization row

    Security notes:
    - Returning 401 (not 403) for all validation failures prevents enumeration.
    - The full raw key is NEVER logged; only the masked prefix is used in log lines.
    - last_used_at failure is logged as WARNING and never propagated (M3 fix).

    Raises:
        HTTPException(401): Any auth failure (see detail codes above).
    """
    from app.api_keys.repository import APIKeyRepository

    # Step 1: extract header
    raw_key: str | None = request.headers.get("X-API-Key")
    if raw_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MISSING_API_KEY",
        )

    # Step 2: validate format
    valid_prefixes = ("cat_live_", "cat_test_")
    if not any(raw_key.startswith(p) for p in valid_prefixes):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="INVALID_API_KEY",
        )
    if len(raw_key) < 48:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="INVALID_API_KEY",
        )

    # Step 3: extract display prefix (8 chars after "cat_????_" → positions 9-16)
    _display_prefix = raw_key[9:17]  # used for logging only (never in Redis keys — see M4 fix)

    # TODO: add Redis rate limiting — see Pseudocode.md § get_org_by_api_key (Step 4).
    # Rate limit key MUST be based on key_hash[:16], NOT key_prefix — using the prefix
    # risks two distinct keys sharing a rate limit bucket due to 8-char collision space
    # (validation-report.md M4 fix). Implementation:
    #   rate_key = f"rate:apikey:{key_hash[:16]}"
    #   Use sliding-window sorted-set pattern from Pseudocode.md.
    #   Raise HTTP 429 "RATE_LIMIT_EXCEEDED" with Retry-After / X-RateLimit-* headers.

    # Step 5: hash lookup — compute hash AFTER rate-limit check in the full implementation
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = await APIKeyRepository.get_by_hash(db, key_hash)

    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="INVALID_API_KEY",
        )

    # Step 6: check revoked
    if api_key.revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API_KEY_REVOKED",
        )

    # Step 7: check expiry — must use timezone-aware UTC datetime (coding-style.md rule)
    if api_key.expires_at is not None and api_key.expires_at < datetime.now(tz=timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API_KEY_EXPIRED",
        )

    # Step 8: fire-and-forget last_used_at update (M3 fix: wrap in try/except, log WARNING)
    # asyncio.create_task() schedules the coroutine without blocking the response.
    # Any exception inside update_last_used is caught here and logged — never propagated.
    try:
        asyncio.create_task(
            APIKeyRepository.update_last_used(db, api_key.id)
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "api_keys.deps.last_used_update_failed key_prefix=%s error=%s",
            _display_prefix,
            exc,
        )

    # Step 9: load and return the Organisation
    result = await db.execute(
        select(Organization).where(Organization.id == api_key.org_id)
    )
    org = result.scalar_one_or_none()

    if org is None:
        # Defensive: the org was deleted after the key was issued (cascades should
        # clean up, but guard against race conditions or misconfigured migrations).
        logger.error(
            "api_keys.deps.org_missing key_prefix=%s org_id=%s",
            _display_prefix,
            api_key.org_id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="INVALID_API_KEY",
        )

    return org
