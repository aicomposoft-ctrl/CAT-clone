"""
pytest configuration for collector service tests.

Sets POSTGRES_URL and REDIS_URL so imports of app modules don't fail at
module load time (celery_app reads REDIS_URL at import).
"""

import os

os.environ.setdefault("POSTGRES_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "test")
os.environ.setdefault("MINIO_SECRET_KEY", "testtest")
os.environ.setdefault("MINIO_BUCKET", "cat-references-test")
