"""
Async MinIO/S3 client wrapper for CAT API.

Uses aioboto3 under the hood. Provides typed helpers for reference image operations.

Security rules:
  - Bucket is always private (no public access)
  - Images served only via presigned URLs (max 1 hour TTL)
  - Credentials sourced from environment only — never hardcoded
  - S3 key always starts with org/{org_id}/ — verified by callers before deletion
"""

from __future__ import annotations

import logging
import os
from uuid import UUID

logger = logging.getLogger(__name__)

_BUCKET = "cat-references"
_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _validate_image_magic(content: bytes, ext: str) -> bool:
    """
    Verify that file magic bytes match the declared extension.

    JPEG: FF D8 FF  (bytes 0-2)
    PNG:  89 50 4E 47  (bytes 0-3, i.e. \\x89PNG)
    WebP: 52 49 46 46 ?? ?? ?? ?? 57 45 42 50  (RIFF....WEBP)
          — bytes 0-3 must be RIFF AND bytes 8-11 must be WEBP

    A RIFF check alone is insufficient: WAV and AVI files also start with RIFF.
    """
    if ext in {".jpg", ".jpeg"}:
        return content[:3] == b"\xff\xd8\xff"
    if ext == ".png":
        return len(content) >= 8 and content[:8] == b"\x89PNG\r\n\x1a\n"
    if ext == ".webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    return False


class MinioClient:
    """
    Thin async wrapper over aioboto3 S3 operations needed for reference uploads.

    Usage (FastAPI dependency)::

        async def get_minio() -> MinioClient:
            return MinioClient.from_env()

    All public methods are async and safe to call from FastAPI handlers.
    """

    BUCKET = _BUCKET
    ALLOWED_EXTENSIONS = _ALLOWED_EXTENSIONS
    MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
    PRESIGNED_TTL = 3600  # 1 hour
    ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

    def __init__(self, endpoint: str, access_key: str, secret_key: str) -> None:
        self._endpoint = endpoint
        self._access_key = access_key
        self._secret_key = secret_key

    @classmethod
    def from_env(cls) -> "MinioClient":
        return cls(
            endpoint=os.environ["MINIO_ENDPOINT"],
            access_key=os.environ["MINIO_ACCESS_KEY"],
            secret_key=os.environ["MINIO_SECRET_KEY"],
        )

    def _make_client(self):
        """Create an aioboto3 S3 client (context manager)."""
        try:
            import aioboto3
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("aioboto3 is required for MinIO operations") from exc

        session = aioboto3.Session()
        return session.client(
            "s3",
            endpoint_url=f"http://{self._endpoint}",
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
        )

    def validate_image(self, content: bytes, filename: str, content_type: str) -> tuple[str, str]:
        """
        Validate image upload. Returns (extension, mime_type) on success.
        Raises ValueError with error code on failure.
        """
        from pathlib import Path

        if len(content) > self.MAX_FILE_BYTES:
            raise ValueError("FILE_TOO_LARGE")

        # Content-Type allowlist (first-pass defense-in-depth)
        if content_type and content_type not in self.ALLOWED_CONTENT_TYPES:
            raise ValueError("INVALID_IMAGE_TYPE")

        ext = Path(filename).suffix.lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise ValueError("INVALID_IMAGE_TYPE")

        if not _validate_image_magic(content, ext):
            raise ValueError("INVALID_IMAGE_MAGIC")

        return ext, content_type or "image/jpeg"

    @staticmethod
    def make_s3_key(org_id: UUID, sku_id: UUID, ext: str) -> str:
        """Construct canonical S3 key for a reference image."""
        return f"org/{org_id}/sku/{sku_id}/reference{ext}"

    async def upload(self, s3_key: str, content: bytes, content_type: str) -> None:
        """Upload bytes to MinIO. Raises RuntimeError if upload fails."""
        try:
            async with self._make_client() as s3:
                await s3.put_object(
                    Bucket=self.BUCKET,
                    Key=s3_key,
                    Body=content,
                    ContentType=content_type,
                )
        except Exception as exc:
            logger.error("MinIO upload failed for key %s: %s", s3_key, exc)
            raise RuntimeError("S3_UPLOAD_FAILED") from exc

    async def delete(self, s3_key: str, org_id: UUID) -> None:
        """
        Delete an object from MinIO.

        org_id is required — asserts the key belongs to that org's prefix to
        prevent accidental cross-org deletion. Callers must always pass org_id.
        """
        expected_prefix = f"org/{org_id}/"
        if not s3_key.startswith(expected_prefix):
            raise PermissionError(
                f"S3 key {s3_key!r} does not belong to org {org_id} — deletion refused"
            )
        try:
            async with self._make_client() as s3:
                await s3.delete_object(Bucket=self.BUCKET, Key=s3_key)
        except Exception as exc:
            logger.warning("MinIO delete failed for key %s: %s", s3_key, exc)
            # Non-fatal: stale key in S3 is not a security issue

    async def presign(self, s3_key: str, expires: int = PRESIGNED_TTL) -> str:
        """Generate a presigned GET URL. Raises RuntimeError if MinIO is unavailable."""
        try:
            async with self._make_client() as s3:
                url = await s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.BUCKET, "Key": s3_key},
                    ExpiresIn=expires,
                )
            return url
        except Exception as exc:
            logger.error("MinIO presign failed for key %s: %s", s3_key, exc)
            raise RuntimeError("S3_PRESIGN_FAILED") from exc
