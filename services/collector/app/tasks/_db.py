"""
Synchronous SQLAlchemy session factory for Celery workers.

Celery workers use sync sessions (not async). The connection string
strips the asyncpg driver suffix added for the FastAPI API service.

Example:
  POSTGRES_URL = "postgresql+asyncpg://user:pass@host/db"
  → Celery uses "postgresql://user:pass@host/db"
"""

from __future__ import annotations

import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_engine = None
_SessionLocal = None


def _get_engine():
    global _engine
    if _engine is None:
        url = os.environ["POSTGRES_URL"].replace("+asyncpg", "")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def _get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=_get_engine(), autocommit=False, autoflush=False)
    return _SessionLocal


@contextmanager
def get_db_session():
    """Yield a sync SQLAlchemy session with automatic rollback on error."""
    factory = _get_session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
