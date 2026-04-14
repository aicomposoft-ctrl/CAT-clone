"""
MinIO (S3-compatible) client for the processor service.

Downloads object content by S3 key. Enforces MAX_IMAGE_BYTES size limit
before loading the full response into RAM to prevent OOM on large files.

Credentials loaded from environment variables (AC-SEC-4):
  MINIO_ENDPOINT   — e.g. "minio:9000"
  MINIO_ACCESS_KEY — access key
  MINIO_SECRET_KEY — secret key
  MINIO_BUCKET     — bucket name (default: "cat-data")

MAX_IMAGE_BYTES env var controls the file size limit (default 30 MB).

Singleton: _s3_client is initialized once per worker process on first
download_object call to avoid boto3 client creation overhead per task.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_DEFAULT_BUCKET = "cat-data"
_MAX_IMAGE_BYTES = int(os.environ.get("MAX_IMAGE_BYTES", 30_000_000))

_s3_client = None


def _get_s3_client():
    """Return the module-level boto3 S3 singleton (lazy init, one client per process)."""
    global _s3_client
    if _s3_client is None:
        import boto3

        _s3_client = boto3.client(
            "s3",
            endpoint_url=f"http://{os.environ['MINIO_ENDPOINT']}",
            aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
            aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
        )
    return _s3_client


def download_object(s3_key: str, bucket: str | None = None) -> bytes:
    """
    Download an object from MinIO and return its content as bytes.

    Enforces MAX_IMAGE_BYTES: raises ValueError if Content-Length exceeds
    the limit before reading the body (prevents OOM on large files).

    Raises:
        ValueError      — file exceeds MAX_IMAGE_BYTES
        ClientError     — S3/MinIO error (e.g. NoSuchKey → 404)
        Exception       — network or boto3 error (caller should retry)
    """
    client = _get_s3_client()
    bucket = bucket or os.environ.get("MINIO_BUCKET", _DEFAULT_BUCKET)

    # Head request to check size before streaming body
    head = client.head_object(Bucket=bucket, Key=s3_key)
    content_length = head.get("ContentLength", 0)
    if content_length > _MAX_IMAGE_BYTES:
        raise ValueError(
            f"Image exceeds size limit: {content_length} bytes "
            f"(MAX_IMAGE_BYTES={_MAX_IMAGE_BYTES}) for key={s3_key!r}"
        )

    obj = client.get_object(Bucket=bucket, Key=s3_key)
    return obj["Body"].read()
