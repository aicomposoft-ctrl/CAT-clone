"""
Redis client for embedding cache operations in the processor service.

Provides get/set helpers for raw numpy embedding vectors.
All keys follow the pattern: ref_emb:{sku_id}:{field}

Serialization: raw float32 bytes via numpy.tobytes() / numpy.frombuffer().
This avoids pickle.loads() which is a potential RCE vector if Redis is
compromised. Embedding shape is validated against expected dimensions.

Singleton: _redis_client is initialized once per worker process on first
get_embedding/set_embedding call. REDIS_URL must be set in environment —
missing = KeyError at startup (fail-fast per secrets policy).
"""

from __future__ import annotations

import logging
import os

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

_redis_client = None


def _get_client():
    """Return the module-level Redis singleton (lazy init, one pool per process)."""
    global _redis_client
    if _redis_client is None:
        import redis

        _redis_client = redis.from_url(
            os.environ["REDIS_URL"],  # fail-fast: KeyError if missing
            decode_responses=False,
        )
    return _redis_client


def get_embedding(sku_id: str, field: str = "image") -> np.ndarray | None:
    """
    Load a cached embedding from Redis.

    Returns:
        np.ndarray of expected shape if present and valid.
        None if key is missing, expired, or deserialization fails.

    Validates:
        - Result is a numpy.ndarray of expected dtype/shape
    """
    key = f"ref_emb:{sku_id}:{field}"
    try:
        raw = _get_client().get(key)
    except Exception as exc:
        logger.warning("Redis GET failed for key %s: %s", key, exc)
        return None

    if raw is None:
        return None

    expected_shape = _SHAPE_BY_FIELD.get(field, (512,))
    try:
        vec = np.frombuffer(raw, dtype=np.float32)
    except Exception as exc:
        logger.error("Cannot decode embedding for key %s: %s", key, exc)
        return None

    if vec.shape != expected_shape:
        logger.error(
            "Unexpected embedding shape for key %s: expected %s, got %s",
            key,
            expected_shape,
            vec.shape,
        )
        return None

    return vec


def set_embedding(sku_id: str, embedding: np.ndarray, field: str = "image") -> None:
    """
    Store a numpy embedding in Redis with 30-day TTL.

    Serialized as raw float32 bytes (numpy.tobytes) — no pickle.

    Raises:
        Exception — Redis connection error (caller should retry)
    """
    key = f"ref_emb:{sku_id}:{field}"
    payload = embedding.astype(np.float32).tobytes()
    _get_client().setex(key, _REDIS_TTL, payload)
    logger.debug("Embedding stored at %s (%d bytes)", key, len(payload))
