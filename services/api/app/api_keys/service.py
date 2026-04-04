"""
API key service layer — business logic for key generation, creation, listing, revocation.

Design rules:
- generate_api_key() is a pure function — no DB, no side effects. Fully unit-testable.
- create_api_key() constructs the ORM model and delegates persistence to the repository.
- revoke_api_key() raises HTTP 404 for both "not found" and "wrong org" to prevent
  key enumeration (Pseudocode.md § revoke_api_key, Architecture.md § 10).
- The raw key is returned ONCE in APIKeyCreateResponse.key and never stored.
- All service functions receive db: AsyncSession from the FastAPI dependency injection.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api_keys.models import APIKey
from app.api_keys.repository import APIKeyRepository
from app.api_keys.schemas import (
    APIKeyCreateRequest,
    APIKeyCreateResponse,
    APIKeyListItem,
    APIKeyListResponse,
)
from app.auth.models import User

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Key generation (pure function — no DB)
# ---------------------------------------------------------------------------


def generate_api_key(env: str = "live") -> tuple[str, str, str]:
    """
    Generate a new API key tuple.

    Returns:
        (full_key, key_prefix, key_hash)

        full_key:   cat_{env}_{raw}  — returned to the user once, never stored.
                    Example: "cat_live_xK9mN2abcdefghijklmno..."
        key_prefix: raw[:8]           — first 8 chars of the raw portion, stored
                    for display in the management UI (never enough to brute-force).
        key_hash:   SHA-256 hex of full_key — the only value stored in the DB.
                    A DB breach does not yield usable keys.

    Args:
        env: "live" or "test". Used as the second segment of the key prefix.
             Prod keys use "live"; sandbox/CI keys use "test".
    """
    raw = secrets.token_urlsafe(30)          # 40-char url-safe random string
    full_key = f"cat_{env}_{raw}"
    key_prefix = raw[:8]
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    return full_key, key_prefix, key_hash


# ---------------------------------------------------------------------------
# Service functions
# ---------------------------------------------------------------------------


async def create_api_key(
    db: AsyncSession,
    request: APIKeyCreateRequest,
    current_user: User,
) -> APIKeyCreateResponse:
    """
    Create a new API key for the authenticated user's organisation.

    Generates the key, stores only the hash, and returns the full key
    in the response exactly once. Subsequent GET /api-keys responses
    show only the prefix.

    Args:
        db:           Async DB session (from FastAPI dependency injection).
        request:      Validated create request (name, optional expires_at).
        current_user: Authenticated user (must be admin or manager — enforced
                      by require_role() in the router before this is called).

    Returns:
        APIKeyCreateResponse with the full plaintext key in the `key` field.
    """
    full_key, key_prefix, key_hash = generate_api_key("live")

    api_key = APIKey(
        org_id=current_user.org_id,
        name=request.name,
        key_prefix=key_prefix,
        key_hash=key_hash,
        created_by=current_user.id,
        expires_at=request.expires_at,
    )

    saved = await APIKeyRepository.create(db, api_key)

    logger.info(
        "api_keys.service.created org_id=%s prefix=%s created_by=%s",
        current_user.org_id,
        key_prefix,
        current_user.id,
    )

    return APIKeyCreateResponse(
        id=saved.id,
        name=saved.name,
        key=full_key,           # ONLY time the full key is returned
        key_prefix=key_prefix,
        expires_at=saved.expires_at,
        created_at=saved.created_at,
    )


async def list_api_keys(
    db: AsyncSession,
    current_user: User,
) -> APIKeyListResponse:
    """
    Return all API keys for the authenticated user's organisation.

    Includes revoked keys so users can audit the full key history.
    The raw key is never included — only key_prefix for display.

    Args:
        db:           Async DB session.
        current_user: Authenticated user (admin or manager — enforced by router).

    Returns:
        APIKeyListResponse with items list and total count.
    """
    keys = await APIKeyRepository.list_by_org(db, current_user.org_id)
    items = [APIKeyListItem.model_validate(k) for k in keys]
    return APIKeyListResponse(items=items, total=len(items))


async def revoke_api_key(
    db: AsyncSession,
    key_id: UUID,
    current_user: User,
) -> None:
    """
    Revoke an API key by setting revoked=True.

    Raises HTTP 404 for both "not found" and "wrong org" cases — returning
    403 for wrong-org would allow enumeration of valid key UUIDs across orgs.
    (Pseudocode.md § revoke_api_key, validation-report.md M1 anti-enumeration note)

    Args:
        db:           Async DB session.
        key_id:       UUID of the key to revoke.
        current_user: Authenticated user. Only keys belonging to this user's
                      org can be revoked (enforced by get_by_id_and_org filter).

    Raises:
        HTTPException(404): Key not found or belongs to a different organisation.
    """
    api_key = await APIKeyRepository.get_by_id_and_org(
        db,
        key_id=key_id,
        org_id=current_user.org_id,
    )

    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API_KEY_NOT_FOUND",
        )

    api_key.revoked = True
    await db.commit()

    logger.info(
        "api_keys.service.revoked key_id=%s org_id=%s revoked_by=%s",
        key_id,
        current_user.org_id,
        current_user.id,
    )
