"""
Shared pytest fixtures for processor service tests.

All tests use fully mocked DB, Redis, MinIO, and CLIP model —
no real infrastructure required.
"""

from __future__ import annotations

import pickle
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

ORG_A_ID = uuid.uuid4()
ORG_B_ID = uuid.uuid4()
SKU_A_ID = uuid.uuid4()
SKU_B_ID = uuid.uuid4()
CS_ID = uuid.uuid4()
S3_KEY = f"org/{ORG_A_ID}/sku/{SKU_A_ID}/wb/main.jpg"
REF_S3_KEY = f"ref/{ORG_A_ID}/sku/{SKU_A_ID}/image.jpg"


@pytest.fixture
def normalized_embedding() -> np.ndarray:
    """Return a deterministic L2-normalized 512-dim embedding."""
    rng = np.random.default_rng(42)
    vec = rng.standard_normal(512).astype(np.float32)
    return vec / np.linalg.norm(vec)


@pytest.fixture
def ref_embedding_bytes(normalized_embedding) -> bytes:
    """Pickled reference embedding (protocol 5)."""
    return pickle.dumps(normalized_embedding, protocol=5)


@pytest.fixture
def mock_redis(ref_embedding_bytes):
    """Redis client mock with reference embedding pre-loaded."""
    client = MagicMock()
    client.get.return_value = ref_embedding_bytes
    client.setex.return_value = True
    return client


@pytest.fixture
def mock_redis_empty():
    """Redis client mock with no embedding stored."""
    client = MagicMock()
    client.get.return_value = None
    return client


@pytest.fixture
def valid_jpeg_bytes() -> bytes:
    """Minimal valid JPEG bytes via Pillow."""
    from io import BytesIO

    from PIL import Image

    img = Image.new("RGB", (64, 64), color=(128, 64, 32))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def valid_1x1_jpeg() -> bytes:
    """1×1 pixel JPEG — placeholder image."""
    from io import BytesIO

    from PIL import Image

    img = Image.new("RGB", (1, 1), color=(255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def mock_download_object(valid_jpeg_bytes):
    """Patch minio download to return valid JPEG bytes."""
    with patch("app.core.minio_client.download_object", return_value=valid_jpeg_bytes) as m:
        yield m


@pytest.fixture
def mock_encode_image(normalized_embedding):
    """Patch encode_image to return the fixture embedding."""
    with patch("app.core.clip_model.encode_image", return_value=normalized_embedding) as m:
        yield m


@pytest.fixture
def mock_db_session():
    """Mock get_db_session context manager."""
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    return session
