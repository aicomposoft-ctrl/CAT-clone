"""
Database engine, session factory, and base model for CAT API.

DATABASE_URL is sourced from Settings (pydantic-settings), which reads POSTGRES_URL
from the environment. validate_required_secrets() in main.py ensures the service
exits immediately if POSTGRES_URL is absent — no silent fallbacks.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

_settings = get_settings()
_db_url = _settings.POSTGRES_URL

# SQLite (used in tests) does not support pool_size/max_overflow.
# Production PostgreSQL deployments get a 30-connection pool.
_pool_kwargs: dict = (
    {"pool_size": 10, "max_overflow": 20}
    if not _db_url.startswith("sqlite")
    else {}
)

engine = create_async_engine(
    _db_url,
    pool_pre_ping=True,  # detect stale connections before use
    echo=False,
    **_pool_kwargs,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # avoid lazy-load errors after commit in async context
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    """Shared declarative base for all SQLAlchemy ORM models."""
    pass



