"""
Auth router for CAT API.

Endpoints:
  POST /login    — authenticate user, return access + refresh tokens
  POST /refresh  — exchange valid refresh token for new access token
  POST /logout   — revoke refresh token (idempotent)
  GET  /me       — return current user info

All business logic is delegated to auth_service. This module only:
  - validates HTTP request shapes (via Pydantic schemas)
  - calls service methods
  - maps domain exceptions to HTTP exceptions
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service as auth_service
from app.auth.models import User
from app.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RefreshResponse,
    TokenResponse,
    UserInfo,
)
from app.core.security import AuthError, LockoutError
from app.core.deps import get_current_user, get_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Authenticate with email + password.

    Returns access token (15 min) and refresh token (7 days).
    Locks account after 5 consecutive failed attempts.
    """
    try:
        return await auth_service.authenticate_user(db, body.email, body.password)
    except LockoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="ACCOUNT_LOCKED",
            headers={"X-Lockout-Until": exc.lockout_until.isoformat()},
        ) from exc
    except AuthError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="INVALID_CREDENTIALS",
        )


@router.post("/refresh", response_model=RefreshResponse, status_code=status.HTTP_200_OK)
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> RefreshResponse:
    """
    Exchange a valid (non-expired, non-revoked) refresh token for a new access token.

    The refresh token itself is NOT rotated — it remains valid until its 7-day expiry
    or until explicit logout.
    """
    try:
        return await auth_service.refresh_access_token(db, body.refresh_token)
    except AuthError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="INVALID_REFRESH_TOKEN",
        )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    body: LogoutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Revoke the provided refresh token.

    Idempotent — succeeds even if the token is already revoked or not found.
    Requires a valid access token to prevent unauthenticated token revocation.
    """
    await auth_service.revoke_refresh_token(db, body.refresh_token)
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserInfo, status_code=status.HTTP_200_OK)
async def me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserInfo:
    """Return profile info for the currently authenticated user."""
    return await auth_service.get_user_info(db, current_user)
