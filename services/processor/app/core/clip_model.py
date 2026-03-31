"""
CLIP model singleton for the processor service.

Loads openai/clip-vit-base-patch32 once per worker process and caches it.
Subsequent calls to encode_image() reuse the loaded model without re-downloading.

Model: openai/clip-vit-base-patch32
  Input:  PIL.Image (any size — CLIPProcessor handles resize/normalize)
  Output: np.ndarray shape (512,), L2-normalized (cosine sim = dot product)
  RAM:    ~340 MB per worker (CPU weights)

Security (AC-SEC-5):
  Zero-norm guard: if ||vec|| < 1e-8 (degenerate embedding), raises ValueError.
  This prevents division-by-zero and downstream NaN in cosine similarity.

Thread safety:
  _load() is NOT thread-safe on first call. Celery prefork workers are
  single-threaded per process — safe. Do NOT use with gevent/eventlet.
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from PIL import Image as PILImage

logger = logging.getLogger(__name__)

_MODEL_ID = "openai/clip-vit-base-patch32"

_model = None
_processor = None


def _load() -> None:
    """Load CLIP model + processor into module-level singletons (once per process)."""
    global _model, _processor
    if _model is not None:
        return
    from transformers import CLIPModel, CLIPProcessor

    logger.info("Loading CLIP model %s …", _MODEL_ID)
    _processor = CLIPProcessor.from_pretrained(_MODEL_ID)
    _model = CLIPModel.from_pretrained(_MODEL_ID)
    _model.eval()
    logger.info("CLIP model loaded")


def encode_image(pil_image: "PILImage.Image") -> np.ndarray:
    """
    Compute a CLIP image embedding for a PIL image.

    Args:
        pil_image: PIL.Image in any mode (converted to RGB internally)

    Returns:
        np.ndarray of shape (512,), L2-normalized.

    Raises:
        ValueError: if the resulting embedding has near-zero norm (< 1e-8)
    """
    import torch

    _load()

    inputs = _processor(images=pil_image, return_tensors="pt")
    with torch.no_grad():
        features = _model.get_image_features(**inputs)  # shape [1, 512]

    vec: np.ndarray = features[0].numpy()  # shape (512,)

    norm = float(np.linalg.norm(vec))
    if norm < 1e-8:
        raise ValueError(
            f"CLIP produced a near-zero embedding (norm={norm:.2e}) — "
            "image may be degenerate or model malfunction"
        )

    return vec / norm  # L2-normalize


def decode_image(image_bytes: bytes) -> "PILImage.Image":
    """
    Decode raw image bytes into a PIL RGB image.

    Validates format against allowed types (JPEG, PNG, WEBP) per AC-SEC-3.

    Raises:
        ValueError: unsupported format
        Exception:  PIL decode error (corrupted image)
    """
    from PIL import Image

    _ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

    image = Image.open(BytesIO(image_bytes))
    if image.format not in _ALLOWED_FORMATS:
        raise ValueError(
            f"Unsupported image format: {image.format!r}. "
            f"Allowed: {_ALLOWED_FORMATS}"
        )
    return image.convert("RGB")
