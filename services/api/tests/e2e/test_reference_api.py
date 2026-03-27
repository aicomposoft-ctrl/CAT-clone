"""
E2E tests for reference upload endpoints.

Covers BDD scenarios from Specification.md (+ validation report additions):
  US-R01: Reference Image Upload
  US-R02: Reference Text Upload
  US-R03: Presigned URL for Viewing

MinioClient is mocked via dependency_overrides — no real MinIO needed.
"""

from __future__ import annotations

import io
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.models import Organization, User
from app.catalog.models import Brand, SKU
from app.core.database import Base
from app.core.deps import get_db
from app.core.minio_client import MinioClient
from app.core.security import create_access_token, hash_password
from app.main import app
from app.catalog.reference_router import _get_minio

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def engine():
    e = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield e
    await e.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    async with engine.connect() as conn:
        await conn.begin()
        factory = async_sessionmaker(bind=conn, expire_on_commit=False, class_=AsyncSession)
        async with factory() as session:
            yield session
        await conn.rollback()


def _make_mock_minio(presign_url: str = "https://minio/presigned?sig=abc") -> MagicMock:
    """Return a MinioClient mock with default happy-path behaviour."""
    mock = MagicMock(spec=MinioClient)
    mock.validate_image.return_value = (".jpg", "image/jpeg")
    mock.upload = AsyncMock(return_value=None)
    mock.delete = AsyncMock(return_value=None)
    mock.presign = AsyncMock(return_value=presign_url)
    mock.make_s3_key = MinioClient.make_s3_key  # static, use real impl
    return mock


@pytest_asyncio.fixture
async def client(db_session):
    mock_minio = _make_mock_minio()

    async def _db():
        yield db_session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[_get_minio] = lambda: mock_minio

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, mock_minio

    app.dependency_overrides.clear()


# ── DB helpers ─────────────────────────────────────────────────────────────────

async def _org(db: AsyncSession) -> Organization:
    org = Organization(id=uuid.uuid4(), name="Org", slug=f"o-{uuid.uuid4().hex[:6]}", plan="basic")
    db.add(org)
    await db.flush()
    return org


async def _user(db: AsyncSession, org_id: uuid.UUID, role: str = "manager") -> User:
    u = User(
        id=uuid.uuid4(), org_id=org_id,
        email=f"u-{uuid.uuid4().hex[:6]}@test.ru",
        password_hash=hash_password("Pass1!"),
        role=role,
    )
    db.add(u)
    await db.flush()
    return u


def _auth(user: User) -> dict:
    token = create_access_token(user.id, user.org_id, user.role)
    return {"Authorization": f"Bearer {token}"}


async def _brand(db: AsyncSession, org_id: uuid.UUID) -> Brand:
    b = Brand(id=uuid.uuid4(), org_id=org_id, name="Brand", type="client")
    db.add(b)
    await db.flush()
    return b


async def _sku(
    db: AsyncSession, org_id: uuid.UUID, brand_id: uuid.UUID,
    ref_image: str | None = None,
) -> SKU:
    s = SKU(
        id=uuid.uuid4(), org_id=org_id, brand_id=brand_id,
        name="Test SKU", is_active=True, reference_image_url=ref_image,
    )
    db.add(s)
    await db.flush()
    return s


def _jpeg_bytes(size: int = 100) -> bytes:
    """Minimal valid JPEG magic bytes + padding."""
    return b"\xff\xd8\xff" + b"\x00" * size


# ── US-R01: Image Upload ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_image_202(client, db_session):
    c, minio = client
    org = await _org(db_session)
    user = await _user(db_session, org.id)
    brand = await _brand(db_session, org.id)
    sku = await _sku(db_session, org.id, brand.id)

    resp = await c.post(
        f"/api/v1/skus/{sku.id}/reference/image",
        files={"file": ("photo.jpg", io.BytesIO(_jpeg_bytes()), "image/jpeg")},
        headers=_auth(user),
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "presigned_url" in data
    assert data["expires_in"] == 3600
    minio.upload.assert_called_once()


@pytest.mark.asyncio
async def test_upload_image_viewer_403(client, db_session):
    c, _ = client
    org = await _org(db_session)
    viewer = await _user(db_session, org.id, role="viewer")
    brand = await _brand(db_session, org.id)
    sku = await _sku(db_session, org.id, brand.id)

    resp = await c.post(
        f"/api/v1/skus/{sku.id}/reference/image",
        files={"file": ("photo.jpg", io.BytesIO(_jpeg_bytes()), "image/jpeg")},
        headers=_auth(viewer),
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "INSUFFICIENT_PERMISSIONS"


@pytest.mark.asyncio
async def test_upload_image_cross_org_404(client, db_session):
    c, _ = client
    org_a = await _org(db_session)
    org_b = await _org(db_session)
    user_a = await _user(db_session, org_a.id)
    brand_b = await _brand(db_session, org_b.id)
    sku_b = await _sku(db_session, org_b.id, brand_b.id)

    resp = await c.post(
        f"/api/v1/skus/{sku_b.id}/reference/image",
        files={"file": ("photo.jpg", io.BytesIO(_jpeg_bytes()), "image/jpeg")},
        headers=_auth(user_a),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upload_image_too_large_422(client, db_session):
    c, minio = client
    org = await _org(db_session)
    user = await _user(db_session, org.id)
    brand = await _brand(db_session, org.id)
    sku = await _sku(db_session, org.id, brand.id)

    # Make validate_image raise FILE_TOO_LARGE
    minio.validate_image.side_effect = ValueError("FILE_TOO_LARGE")

    resp = await c.post(
        f"/api/v1/skus/{sku.id}/reference/image",
        files={"file": ("big.jpg", io.BytesIO(b"\xff\xd8\xff" + b"x" * 100), "image/jpeg")},
        headers=_auth(user),
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "FILE_TOO_LARGE"


@pytest.mark.asyncio
async def test_upload_image_invalid_type_422(client, db_session):
    c, minio = client
    org = await _org(db_session)
    user = await _user(db_session, org.id)
    brand = await _brand(db_session, org.id)
    sku = await _sku(db_session, org.id, brand.id)

    minio.validate_image.side_effect = ValueError("INVALID_IMAGE_TYPE")

    resp = await c.post(
        f"/api/v1/skus/{sku.id}/reference/image",
        files={"file": ("doc.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        headers=_auth(user),
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "INVALID_IMAGE_TYPE"


@pytest.mark.asyncio
async def test_upload_image_invalid_magic_422(client, db_session):
    c, minio = client
    org = await _org(db_session)
    user = await _user(db_session, org.id)
    brand = await _brand(db_session, org.id)
    sku = await _sku(db_session, org.id, brand.id)

    minio.validate_image.side_effect = ValueError("INVALID_IMAGE_MAGIC")

    resp = await c.post(
        f"/api/v1/skus/{sku.id}/reference/image",
        files={"file": ("evil.jpg", io.BytesIO(b"RIFF\x00\x00\x00\x00AVI "), "image/jpeg")},
        headers=_auth(user),
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "INVALID_IMAGE_MAGIC"


@pytest.mark.asyncio
async def test_upload_image_overwrites_old(client, db_session):
    c, minio = client
    org = await _org(db_session)
    user = await _user(db_session, org.id)
    brand = await _brand(db_session, org.id)
    sku = await _sku(db_session, org.id, brand.id,
                     ref_image=f"org/{org.id}/sku/{uuid.uuid4()}/reference.png")

    # Override make_s3_key on mock to be the real static method
    minio.make_s3_key = MinioClient.make_s3_key

    resp = await c.post(
        f"/api/v1/skus/{sku.id}/reference/image",
        files={"file": ("new.jpg", io.BytesIO(_jpeg_bytes()), "image/jpeg")},
        headers=_auth(user),
    )
    assert resp.status_code == 202
    minio.delete.assert_called_once()


@pytest.mark.asyncio
async def test_upload_image_s3_fail_503(client, db_session):
    c, minio = client
    org = await _org(db_session)
    user = await _user(db_session, org.id)
    brand = await _brand(db_session, org.id)
    sku = await _sku(db_session, org.id, brand.id)

    minio.upload.side_effect = RuntimeError("S3_UPLOAD_FAILED")

    resp = await c.post(
        f"/api/v1/skus/{sku.id}/reference/image",
        files={"file": ("photo.jpg", io.BytesIO(_jpeg_bytes()), "image/jpeg")},
        headers=_auth(user),
    )
    assert resp.status_code == 503


# ── US-R02: Text Upload ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_text_202(client, db_session):
    c, _ = client
    org = await _org(db_session)
    user = await _user(db_session, org.id)
    brand = await _brand(db_session, org.id)
    sku = await _sku(db_session, org.id, brand.id)

    resp = await c.patch(
        f"/api/v1/skus/{sku.id}/reference/text",
        json={"reference_description": "Индейка охл.", "reference_composition": "Индейка 100%"},
        headers=_auth(user),
    )
    assert resp.status_code == 202
    assert resp.json()["sku_id"] == str(sku.id)


@pytest.mark.asyncio
async def test_upload_text_viewer_403(client, db_session):
    c, _ = client
    org = await _org(db_session)
    viewer = await _user(db_session, org.id, role="viewer")
    brand = await _brand(db_session, org.id)
    sku = await _sku(db_session, org.id, brand.id)

    resp = await c.patch(
        f"/api/v1/skus/{sku.id}/reference/text",
        json={"reference_description": "Test"},
        headers=_auth(viewer),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_upload_text_cross_org_404(client, db_session):
    c, _ = client
    org_a = await _org(db_session)
    org_b = await _org(db_session)
    user_a = await _user(db_session, org_a.id)
    brand_b = await _brand(db_session, org_b.id)
    sku_b = await _sku(db_session, org_b.id, brand_b.id)

    resp = await c.patch(
        f"/api/v1/skus/{sku_b.id}/reference/text",
        json={"reference_description": "Hack"},
        headers=_auth(user_a),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upload_text_description_too_long_422(client, db_session):
    c, _ = client
    org = await _org(db_session)
    user = await _user(db_session, org.id)
    brand = await _brand(db_session, org.id)
    sku = await _sku(db_session, org.id, brand.id)

    resp = await c.patch(
        f"/api/v1/skus/{sku.id}/reference/text",
        json={"reference_description": "x" * 2001},
        headers=_auth(user),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload_text_composition_too_long_422(client, db_session):
    c, _ = client
    org = await _org(db_session)
    user = await _user(db_session, org.id)
    brand = await _brand(db_session, org.id)
    sku = await _sku(db_session, org.id, brand.id)

    resp = await c.patch(
        f"/api/v1/skus/{sku.id}/reference/text",
        json={"reference_composition": "x" * 1001},
        headers=_auth(user),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload_text_partial_description_only(client, db_session):
    c, _ = client
    org = await _org(db_session)
    user = await _user(db_session, org.id)
    brand = await _brand(db_session, org.id)
    sku = await _sku(db_session, org.id, brand.id)

    resp = await c.patch(
        f"/api/v1/skus/{sku.id}/reference/text",
        json={"reference_description": "Only description"},
        headers=_auth(user),
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "composition" not in data["embedding_task_ids"]


# ── US-R03: Presigned URL ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_presigned_url_manager_200(client, db_session):
    c, minio = client
    org = await _org(db_session)
    user = await _user(db_session, org.id)
    brand = await _brand(db_session, org.id)
    sku = await _sku(db_session, org.id, brand.id,
                     ref_image=f"org/{org.id}/sku/{uuid.uuid4()}/reference.jpg")

    resp = await c.get(f"/api/v1/skus/{sku.id}/reference/image-url", headers=_auth(user))
    assert resp.status_code == 200
    data = resp.json()
    assert "presigned_url" in data
    assert data["expires_in"] == 3600


@pytest.mark.asyncio
async def test_get_presigned_url_viewer_200(client, db_session):
    """Viewer is allowed to GET presigned URL (read-only access)."""
    c, _ = client
    org = await _org(db_session)
    viewer = await _user(db_session, org.id, role="viewer")
    brand = await _brand(db_session, org.id)
    sku = await _sku(db_session, org.id, brand.id,
                     ref_image=f"org/{org.id}/sku/{uuid.uuid4()}/reference.jpg")

    resp = await c.get(f"/api/v1/skus/{sku.id}/reference/image-url", headers=_auth(viewer))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_presigned_url_no_image_404(client, db_session):
    c, _ = client
    org = await _org(db_session)
    user = await _user(db_session, org.id)
    brand = await _brand(db_session, org.id)
    sku = await _sku(db_session, org.id, brand.id)  # no ref_image

    resp = await c.get(f"/api/v1/skus/{sku.id}/reference/image-url", headers=_auth(user))
    assert resp.status_code == 404
    assert resp.json()["detail"] == "REFERENCE_IMAGE_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_presigned_url_cross_org_404(client, db_session):
    c, _ = client
    org_a = await _org(db_session)
    org_b = await _org(db_session)
    user_a = await _user(db_session, org_a.id)
    brand_b = await _brand(db_session, org_b.id)
    sku_b = await _sku(db_session, org_b.id, brand_b.id,
                       ref_image=f"org/{org_b.id}/sku/{uuid.uuid4()}/reference.jpg")

    resp = await c.get(f"/api/v1/skus/{sku_b.id}/reference/image-url", headers=_auth(user_a))
    assert resp.status_code == 404


# ── Magic bytes unit tests ─────────────────────────────────────────────────────

def test_validate_image_magic_jpeg():
    from app.core.minio_client import _validate_image_magic
    assert _validate_image_magic(b"\xff\xd8\xff\xe0", ".jpg") is True
    assert _validate_image_magic(b"\xff\xd8\xff\xe0", ".jpeg") is True
    assert _validate_image_magic(b"RIFF....WEBP", ".jpg") is False


def test_validate_image_magic_png():
    from app.core.minio_client import _validate_image_magic
    assert _validate_image_magic(b"\x89PNG\r\n\x1a\n", ".png") is True
    assert _validate_image_magic(b"\xff\xd8\xff", ".png") is False


def test_validate_image_magic_webp_valid():
    from app.core.minio_client import _validate_image_magic
    content = b"RIFF\x00\x00\x00\x00WEBP"
    assert _validate_image_magic(content, ".webp") is True


def test_validate_image_magic_webp_riff_not_webp():
    """WAV / AVI files start with RIFF but must NOT pass WebP check."""
    from app.core.minio_client import _validate_image_magic
    wav_content = b"RIFF\x00\x00\x00\x00WAVE"
    avi_content = b"RIFF\x00\x00\x00\x00AVI "
    assert _validate_image_magic(wav_content, ".webp") is False
    assert _validate_image_magic(avi_content, ".webp") is False
