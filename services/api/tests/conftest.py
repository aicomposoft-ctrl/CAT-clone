"""
Shared pytest configuration for CAT API tests.
Sets asyncio mode and provides project-wide fixtures.
"""

import os

import pytest

# Point to test database (SQLite in-memory for unit/e2e, real Postgres for integration)
os.environ.setdefault("POSTGRES_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-key-at-least-32-chars-long!!")
os.environ.setdefault("APP_ENV", "development")


def pytest_configure(config):
    config.addinivalue_line("markers", "asyncio: mark test as async")
