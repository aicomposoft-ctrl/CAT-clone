# Snippet: Pytest Async DB Session with Rollback
# Category: Snippet | Language: Python (pytest + SQLAlchemy async)
# Maturity: 🔴 Alpha | Extracted: 2026-03-27 from CAT project
#
# When to Use:
#   Integration tests that need real DB queries but must not persist data
#   between tests. Wraps each test in a transaction and rolls back after.
#
# When NOT to Use:
#   - Unit tests (mock the repository instead — no DB needed)
#   - Tests that explicitly test commit behavior (use separate test DB + truncate)
#   - Tests requiring multiple concurrent sessions (rollback fixture is single-session)
#
# Prerequisites: pytest-asyncio, SQLAlchemy async, PostgreSQL or SQLite
# Dependencies: pytest, pytest-asyncio, sqlalchemy[asyncio], asyncpg

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from typing import AsyncGenerator

# Configure with your test DB URL
TEST_DATABASE_URL = "postgresql+asyncpg://test_user:test_pass@localhost:5432/test_db"


@pytest.fixture(scope="session")
def engine():
    """Session-scoped engine. NullPool prevents connection reuse between tests."""
    return create_async_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,
        echo=False,
    )


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Per-test async session wrapped in a transaction that rolls back after each test.
    All queries in the test see committed data but nothing persists.
    """
    async with engine.connect() as conn:
        await conn.begin()
        async with AsyncSession(bind=conn, expire_on_commit=False) as session:
            yield session
        await conn.rollback()


# --- Usage in tests ---
#
# @pytest.mark.asyncio
# async def test_create_item(db_session: AsyncSession):
#     item = Item(name="test", org_id=TEST_ORG_ID)
#     db_session.add(item)
#     await db_session.flush()  # assigns ID without committing
#     assert item.id is not None
#     # rollback happens automatically after test
#
#
# --- Multi-tenant isolation test template ---
#
# @pytest.mark.asyncio
# async def test_org_isolation(db_session: AsyncSession):
#     """Verify org_b cannot see org_a's data."""
#     ORG_A = uuid4()
#     ORG_B = uuid4()
#
#     item = Item(name="secret", org_id=ORG_A)
#     db_session.add(item)
#     await db_session.flush()
#
#     results = await item_repo.list(db_session, org_id=ORG_B)
#     assert len(results) == 0, "Cross-tenant data leakage detected!"
