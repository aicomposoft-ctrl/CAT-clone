"""
Multilingual-E5-base model singleton for the processor service.

Loads intfloat/multilingual-e5-base once per worker process and caches it.
Used for encoding collected product text (description, composition).

Model: intfloat/multilingual-e5-base
  Input:  str (prepended with "query: " prefix per e5 protocol)
  Output: np.ndarray shape (768,), L2-normalized
  RAM:    ~1.1 GB per worker (CPU weights)

E5 query-document protocol:
  Reference texts (stored as embeddings): encoded with "passage: " prefix
    → done by API's compute_text_embedding task
  Collected texts (scored here):          encoded with "query: " prefix
    → this module

Pooling strategy:
  multilingual-e5-base uses MEAN pooling over all non-padding tokens.
  CLS token is NOT a valid sentence embedding for this model family.
  Mean pooling is applied with attention_mask to exclude padding tokens.

Thread safety:
  _load() is NOT thread-safe on first call. Celery prefork workers are
  single-threaded per process — safe. Do NOT use with gevent/eventlet.
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_ID = "intfloat/multilingual-e5-base"

_model = None
_tokenizer = None


def _load() -> None:
    """Load E5 model + tokenizer into module-level singletons (once per process)."""
    global _model, _tokenizer
    if _model is not None:
        return
    from transformers import AutoModel, AutoTokenizer

    logger.info("Loading E5 model %s …", _MODEL_ID)
    _tokenizer = AutoTokenizer.from_pretrained(_MODEL_ID)
    _model = AutoModel.from_pretrained(_MODEL_ID)
    _model.eval()
    logger.info("E5 model loaded")


def encode_reference_text(text: str) -> np.ndarray:
    """
    Encode a reference text (description / composition) with "passage: " prefix.

    Used when computing reference embeddings to store in Redis.
    Collected texts are encoded with "query: " prefix (see encode_text below) —
    the asymmetric query/passage encoding is required by the e5 protocol.

    Returns np.ndarray of shape (768,), L2-normalized.
    Raises ValueError if embedding has near-zero norm.
    """
    import torch

    _load()

    prefixed = "passage: " + text
    inputs = _tokenizer(
        prefixed,
        return_tensors="pt",
        truncation=True,
        max_length=512,
        padding=True,
    )
    with torch.no_grad():
        outputs = _model(**inputs)
        token_embeddings = outputs.last_hidden_state
        attention_mask = inputs["attention_mask"]
        mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        emb = torch.sum(token_embeddings * mask_expanded, dim=1) / torch.clamp(
            mask_expanded.sum(dim=1), min=1e-9
        )
        emb = emb / emb.norm(dim=-1, keepdim=True)

    vec: np.ndarray = emb.squeeze().cpu().numpy()
    norm = float(np.linalg.norm(vec))
    if norm < 1e-8:
        raise ValueError(
            f"E5 produced near-zero embedding for reference text (norm={norm:.2e})"
        )
    return vec


def encode_text(text: str) -> np.ndarray:
    """
    Encode text with multilingual-e5-base.

    Prepends "query: " prefix (e5 query-document protocol — collected texts
    are queries; reference texts were encoded as "passage: " by the API).

    Args:
        text: raw product text (description or composition)

    Returns:
        np.ndarray of shape (768,), L2-normalized.

    Raises:
        ValueError: if the resulting embedding has near-zero norm (< 1e-8)
    """
    import torch

    _load()

    prefixed = "query: " + text
    inputs = _tokenizer(
        prefixed,
        return_tensors="pt",
        truncation=True,
        max_length=512,
        padding=True,
    )
    with torch.no_grad():
        outputs = _model(**inputs)
        # Mean pooling over all non-padding tokens (multilingual-e5-base protocol).
        # CLS token alone is NOT a valid sentence embedding for this model.
        token_embeddings = outputs.last_hidden_state  # shape [1, seq_len, 768]
        attention_mask = inputs["attention_mask"]  # shape [1, seq_len]
        mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        emb = torch.sum(token_embeddings * mask_expanded, dim=1) / torch.clamp(
            mask_expanded.sum(dim=1), min=1e-9
        )  # shape [1, 768]
        emb = emb / emb.norm(dim=-1, keepdim=True)  # L2 normalize

    vec: np.ndarray = emb.squeeze().cpu().numpy()  # shape (768,)

    norm = float(np.linalg.norm(vec))
    if norm < 1e-8:
        raise ValueError(
            f"E5 produced a near-zero embedding (norm={norm:.2e}) — "
            "text may be degenerate or model malfunction"
        )

    return vec
