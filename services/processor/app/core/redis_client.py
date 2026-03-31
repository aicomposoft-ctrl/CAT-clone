"""
Redis client for embedding cache operations in the processor service.

Provides get/set helpers for pickled numpy embedding vectors.
All keys follow the pattern: ref_emb:{sku_id}:{field}

Security (AC-SEC-2): pickle.loads is called only on values stored by this
service itself — Redis is internal infrastructure, not internet-exposed.
UnpicklingError is caught and treated as a missing key (corrupted cache).
"""

from __future__ import annotations

import logging
import os
import pickle

import numpy as np

logger = logging.getLogger(__name__)

# Valid embedding shapes per field:
#   image → CLIP ViT-B/32: (512,)
#   desc, comp → multilingual-e5-base: (768,)
_SHAPE_BY_FIELD: dict[str, tuple[int, ...]] = {
    "image": (512,),
    "desc": (768,),
    "comp": (768,),
}
_REDIS_TTL = 2592000  # 30 days


def _get_client():
    import redis

    return redis.from_url(
        os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        decode_responses=False,
    )


def get_embedding(sku_id: str, field: str = "image") -> np.ndarray | None:
    """
    Load a cached embedding from Redis.

    Returns:
        np.ndarray of shape (512,) if present and valid
        None if key is missing, expired, or deserialization fails

    Validates:
        - pickle.loads result is numpy.ndarray (AC-SEC-2)
        - shape is (512,) — unexpected shape is treated as corrupted
    """
    key = f"ref_emb:{sku_id}:{field}"
    try:
        raw = _get_client().get(key)
    except Exception as exc:
        logger.warning("Redis GET failed for key %s: %s", key, exc)
        return None

    if raw is None:
        return None

    try:
        obj = pickle.loads(raw)  # noqa: S301 — internal infra only, not user input
    except (pickle.UnpicklingError, Exception) as exc:
        logger.error("Pickle deserialization failed for key %s: %s", key, exc)
        return None

    if not isinstance(obj, np.ndarray):
        logger.error(
            "Unexpected type in Redis key %s: expected ndarray, got %s",
            key,
            type(obj).__name__,
        )
        return None

    expected_shape = _SHAPE_BY_FIELD.get(field, (512,))
    if obj.shape != expected_shape:
        logger.error(
            "Unexpected embedding shape for key %s: expected %s, got %s",
            key,
            expected_shape,
            obj.shape,
        )
        return None

    return obj


def set_embedding(sku_id: str, embedding: np.ndarray, field: str = "image") -> None:
    """
    Store a numpy embedding in Redis with 30-day TTL.

    Uses pickle protocol 5 for forward compatibility with Python 3.11+.

    Raises:
        Exception — Redis connection error (caller should retry)
    """
    key = f"ref_emb:{sku_id}:{field}"
    payload = pickle.dumps(embedding, protocol=5)
    _get_client().setex(key, _REDIS_TTL, payload)
    logger.debug("Embedding stored at %s (%d bytes)", key, len(payload))
