"""
FastAPI dependencies for CAT API.

Provides:
  - get_db: yields AsyncSession per request
  - get_current_user: decodes JWT access token → returns authenticated User
  - require_role: factory that produces a dependency enforcing RBAC
"""

from collections.abc import AsyncGenerator
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.repository import UserRepository
from app.core.database import AsyncSessionLocal
from app.core.security import AuthError, decode_token

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
) -> User:
    """
    Decode Bearer access token and return the corresponding User.

    Raises HTTPException(401) for any invalid or expired token, or if the
    user no longer exists in the database.
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

    return user


def require_role(*roles: str):
    """
    Dependency factory for role-based access control.

    Usage::

        @router.delete("/skus/{id}")
        async def delete_sku(user: User = Depends(require_role("admin", "manager"))):
            ...

    Raises HTTPException(403) when the authenticated user's role is not in *roles*.
    """
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="INSUFFICIENT_PERMISSIONS",
            )
        return user

    return checker
