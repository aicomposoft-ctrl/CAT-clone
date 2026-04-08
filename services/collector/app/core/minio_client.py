"""
MinIO (S3-compatible) client for the collector service.

Handles upload of scraped product images. Credentials from env vars.
Bucket is auto-created on first use if it doesn't exist.

Singleton: one boto3 client per Celery worker process.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_BUCKET = os.environ.get("MINIO_BUCKET", "cat-data")
_s3 = None


def _get_s3():
    global _s3
    if _s3 is None:
        import boto3
        _s3 = boto3.client(
            "s3",
            endpoint_url=f"http://{os.environ['MINIO_ENDPOINT']}",
            aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
            aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
        )
        _ensure_bucket(_s3)
    return _s3


def _ensure_bucket(client) -> None:
    try:
        client.head_bucket(Bucket=_BUCKET)
    except Exception:
        try:
            client.create_bucket(Bucket=_BUCKET)
            logger.info("Created MinIO bucket: %s", _BUCKET)
        except Exception as e:
            logger.warning("Could not create bucket %s: %s", _BUCKET, e)


class MinioClient:
    def upload(self, s3_key: str, data: bytes, content_type: str = "image/jpeg") -> None:
        """Upload bytes to MinIO under the given S3 key."""
        import io
        client = _get_s3()
        client.put_object(
            Bucket=_BUCKET,
            Key=s3_key,
            Body=io.BytesIO(data),
            ContentType=content_type,
            ContentLength=len(data),
        )
        logger.debug("Uploaded %d bytes → s3://%s/%s", len(data), _BUCKET, s3_key)
