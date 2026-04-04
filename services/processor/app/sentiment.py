"""
Sentiment scorer for Russian review text.

Model: blanchefort/rubert-base-cased-sentiment (HuggingFace)
  - Input: Russian review text (max 512 tokens, truncation on overflow)
  - Output: label ("positive" | "neutral" | "negative") + score (0.000-1.000)
  - Batch size: 32 (optimal for CPU inference throughput)

Language assumption:
  Reviews on Russian FMCG platforms (WB, Ozon, Samokat, etc.) are ≥90% Russian.
  For multi-language review sets, switch to xlm-roberta-base.

Singleton pattern:
  _SCORER is loaded once per process on first call (~2-5s warmup). Subsequent
  calls reuse the loaded model — amortized cost is negligible across batches.

Pre-download in Docker:
  RUN python -c "from transformers import pipeline; pipeline('text-classification', model='blanchefort/rubert-base-cased-sentiment')"
"""

from __future__ import annotations

import logging
from typing import Sequence

logger = logging.getLogger(__name__)

_MODEL_NAME = "blanchefort/rubert-base-cased-sentiment"
_LABEL_MAP = {
    "POSITIVE": "positive",
    "NEGATIVE": "negative",
    "NEUTRAL": "neutral",
}
_BATCH_SIZE = 32

# Module-level singleton — loaded lazily, reused for all batches in this process.
_scorer = None


def _get_scorer():
    """
    Lazy singleton: load the HuggingFace pipeline once per process.

    Raises RuntimeError if the model cannot be loaded (e.g. model files missing).
    The Celery task catches RuntimeError and retries with exponential backoff.
    """
    global _scorer
    if _scorer is None:
        try:
            from transformers import pipeline
            logger.info("Loading sentiment model: %s", _MODEL_NAME)
            _scorer = pipeline(
                "text-classification",
                model=_MODEL_NAME,
                truncation=True,
                max_length=512,
                top_k=1,
                device=-1,  # CPU; change to device=0 for GPU
            )
            logger.info("Sentiment model loaded successfully")
        except Exception as exc:
            raise RuntimeError(f"Failed to load sentiment model: {exc}") from exc
    return _scorer


def score_batch(texts: Sequence[str]) -> list[tuple[str | None, float | None]]:
    """
    Score a list of texts. Returns [(label, score), ...] parallel to input.

    Empty, NULL, or whitespace-only texts return (None, None) — caller must handle.
    Non-empty texts are scored in sub-batches of _BATCH_SIZE.

    Args:
        texts: sequence of review texts (may contain empty strings or None values)

    Returns:
        list of (label, score) tuples, same length as input.
        label: "positive" | "neutral" | "negative" | None
        score: float in [0.0, 1.0] | None

    Raises:
        RuntimeError: if the model is unavailable (triggers Celery retry)
    """
    # Partition into (index, text) for non-empty texts only — before loading model
    valid_indices: list[int] = []
    valid_texts: list[str] = []
    results: list[tuple[str | None, float | None]] = [(None, None)] * len(texts)

    for i, text in enumerate(texts):
        if text and text.strip():
            valid_indices.append(i)
            valid_texts.append(text)

    if not valid_texts:
        return results  # no valid texts — model never loaded

    scorer = _get_scorer()

    # Process in sub-batches of _BATCH_SIZE
    scored: list[tuple[str, float]] = []
    for start in range(0, len(valid_texts), _BATCH_SIZE):
        batch = valid_texts[start : start + _BATCH_SIZE]
        preds = scorer(batch, batch_size=_BATCH_SIZE)
        for pred in preds:
            top = pred[0]  # top_k=1 returns list with one dict
            label = _LABEL_MAP[top["label"]]
            score = round(top["score"], 3)
            scored.append((label, score))

    # Merge back into result list
    for idx, result in zip(valid_indices, scored):
        results[idx] = result

    return results
