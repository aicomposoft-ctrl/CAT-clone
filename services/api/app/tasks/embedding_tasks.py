"""
Celery tasks for computing reference embeddings.

Tasks:
  compute_clip_embedding  — downloads S3 image → CLIP ViT-B/32 → Redis
  compute_text_embedding  — encodes text → multilingual-e5-base → Redis

Both tasks:
  - Retry 3 times with exponential backoff on failure
  - Cache ML models in memory (not reloaded per task)
  - Write embeddings as pickle-serialised numpy arrays to Redis
  - Redis key TTL: 30 days

Models are lazy-loaded on first task execution inside the Celery worker.
"""

from __future__ import annotations

import logging
import os
import pickle
from functools import lru_cache
from io import BytesIO

logger = logging.getLogger(__name__)

_REDIS_TTL = 2592000  # 30 days


def _get_celery_app():
    """Return Celery app. Imported lazily to avoid import errors when Celery is not installed."""
    from celery import Celery
    broker = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    return Celery("cat_processor", broker=broker, backend=broker)


try:
    _celery_app = _get_celery_app()
except Exception:  # pragma: no cover
    _celery_app = None  # type: ignore[assignment]


@lru_cache(maxsize=1)
def _load_clip():
    """Load and cache CLIP model + processor. Called once per worker process."""
    from transformers import CLIPModel, CLIPProcessor
    model_name = "openai/clip-vit-base-patch32"
    processor = CLIPProcessor.from_pretrained(model_name)
    model = CLIPModel.from_pretrained(model_name)
    model.eval()
    return model, processor


@lru_cache(maxsize=1)
def _load_e5():
    """Load and cache multilingual-e5-base model. Called once per worker process."""
    from transformers import AutoModel, AutoTokenizer
    model_name = "intfloat/multilingual-e5-base"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    model.eval()
    return model, tokenizer


def _get_redis_client():
    import redis
    return redis.from_url(
        os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        decode_responses=False,
    )


def _download_from_s3(s3_key: str) -> bytes:
    import boto3
    s3 = boto3.client(
        "s3",
        endpoint_url=f"http://{os.environ['MINIO_ENDPOINT']}",
        aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
        aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
    )
    obj = s3.get_object(Bucket="cat-references", Key=s3_key)
    return obj["Body"].read()


if _celery_app is not None:

    @_celery_app.task(bind=True, max_retries=3, name="cat.compute_clip_embedding")
    def compute_clip_embedding(self, sku_id: str, s3_key: str) -> None:
        """
        Download reference image from MinIO, compute CLIP embedding, store in Redis.

        Redis key: ref_emb:{sku_id}:image  (30-day TTL)
        """
        import torch
        try:
            image_bytes = _download_from_s3(s3_key)
            from PIL import Image
            image = Image.open(BytesIO(image_bytes)).convert("RGB")

            model, processor = _load_clip()
            inputs = processor(images=image, return_tensors="pt")
            with torch.no_grad():
                features = model.get_image_features(**inputs)
                features = features / features.norm(dim=-1, keepdim=True)
                embedding_np = features.squeeze().numpy()  # shape [512]

            redis = _get_redis_client()
            redis.setex(f"ref_emb:{sku_id}:image", _REDIS_TTL, pickle.dumps(embedding_np))
            logger.info("CLIP embedding stored for sku %s", sku_id)

        except Exception as exc:
            logger.warning("CLIP task failed for sku %s (attempt %d): %s",
                           sku_id, self.request.retries + 1, exc)
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    @_celery_app.task(bind=True, max_retries=3, name="cat.compute_text_embedding")
    def compute_text_embedding(self, sku_id: str, field: str, text: str) -> None:
        """
        Compute multilingual-e5-base embedding for description or composition text.

        field: "desc" | "comp"
        Redis key: ref_emb:{sku_id}:{field}  (30-day TTL)
        """
        import torch
        try:
            # multilingual-e5 expects "passage: " prefix for document encoding
            prefixed = f"passage: {text}"
            model, tokenizer = _load_e5()
            inputs = tokenizer(
                prefixed, return_tensors="pt", truncation=True, max_length=512, padding=True
            )
            with torch.no_grad():
                outputs = model(**inputs)
                embedding = outputs.last_hidden_state[:, 0, :]  # CLS token
                embedding = embedding / embedding.norm(dim=-1, keepdim=True)
                embedding_np = embedding.squeeze().numpy()  # shape [768]

            redis = _get_redis_client()
            redis.setex(f"ref_emb:{sku_id}:{field}", _REDIS_TTL, pickle.dumps(embedding_np))
            logger.info("Text embedding stored for sku %s field %s", sku_id, field)

        except Exception as exc:
            logger.warning("Text embedding task failed for sku %s field %s: %s",
                           sku_id, field, exc)
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)

else:  # pragma: no cover

    def compute_clip_embedding(sku_id: str, s3_key: str) -> None:  # type: ignore[misc]
        logger.warning("Celery not configured — CLIP embedding skipped for sku %s", sku_id)

    def compute_text_embedding(sku_id: str, field: str, text: str) -> None:  # type: ignore[misc]
        logger.warning("Celery not configured — text embedding skipped for sku %s field %s", sku_id, field)
