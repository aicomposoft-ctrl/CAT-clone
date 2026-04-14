"""
Unit tests for the sentiment scorer (app/sentiment.py).

All tests mock the HuggingFace pipeline — no model download required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import app.sentiment as sentiment_module
from app.sentiment import score_batch


def _reset_scorer():
    """Reset the singleton so the next call re-loads the model."""
    sentiment_module._scorer = None


class TestScoreBatch:

    def test_empty_string_returns_none_tuple(self):
        """Empty string → (None, None); model is never called."""
        _reset_scorer()
        with patch("transformers.pipeline") as mock_pipeline_cls:
            result = score_batch([""])
        assert result == [(None, None)]
        mock_pipeline_cls.assert_not_called()

    def test_whitespace_only_returns_none_tuple(self):
        """Whitespace-only text → (None, None)."""
        _reset_scorer()
        with patch("transformers.pipeline") as mock_pipeline_cls:
            result = score_batch(["   "])
        assert result == [(None, None)]
        mock_pipeline_cls.assert_not_called()

    def test_none_text_returns_none_tuple(self):
        """None text → (None, None)."""
        _reset_scorer()
        with patch("transformers.pipeline") as mock_pipeline_cls:
            result = score_batch([None])
        assert result == [(None, None)]
        mock_pipeline_cls.assert_not_called()

    def test_normal_text_returns_label_and_score(self):
        """Valid Russian text → correct label and rounded score."""
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = [[{"label": "POSITIVE", "score": 0.9423}]]

        sentiment_module._scorer = mock_pipeline
        result = score_batch(["Отличный продукт!"])

        assert len(result) == 1
        label, score = result[0]
        assert label == "positive"
        assert score == 0.942  # rounded to 3 decimal places

    def test_negative_label_mapped_correctly(self):
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = [[{"label": "NEGATIVE", "score": 0.88}]]
        sentiment_module._scorer = mock_pipeline

        label, score = score_batch(["Ужасное качество!"])[0]
        assert label == "negative"

    def test_neutral_label_mapped_correctly(self):
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = [[{"label": "NEUTRAL", "score": 0.72}]]
        sentiment_module._scorer = mock_pipeline

        label, score = score_batch(["Нормально, ничего особенного"])[0]
        assert label == "neutral"

    def test_mixed_empty_and_valid_preserves_positions(self):
        """Empty texts get (None, None); valid texts get scored; positions are preserved."""
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = [[{"label": "NEGATIVE", "score": 0.88}]]
        sentiment_module._scorer = mock_pipeline

        result = score_batch(["", "Плохое качество", ""])

        assert result[0] == (None, None)
        assert result[1] == ("negative", 0.88)
        assert result[2] == (None, None)

    def test_batch_of_exactly_32_processed(self):
        """Exactly one batch of 32 texts processed without splitting."""
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = [[{"label": "POSITIVE", "score": 0.9}]] * 32
        sentiment_module._scorer = mock_pipeline

        texts = ["Хорошо"] * 32
        results = score_batch(texts)

        assert len(results) == 32
        assert all(label == "positive" for label, _ in results)
        # Should be called once with batch_size=32
        mock_pipeline.assert_called_once()

    def test_batch_of_33_splits_into_two_calls(self):
        """33 texts → 2 pipeline calls (32 + 1)."""
        mock_pipeline = MagicMock()
        # Return correct number of results for each call
        mock_pipeline.side_effect = [
            [[{"label": "POSITIVE", "score": 0.9}]] * 32,
            [[{"label": "POSITIVE", "score": 0.9}]],
        ]
        sentiment_module._scorer = mock_pipeline

        texts = ["Хорошо"] * 33
        results = score_batch(texts)

        assert len(results) == 33
        assert mock_pipeline.call_count == 2

    def test_model_load_failure_raises_runtime_error(self):
        """If model can't load, _get_scorer raises RuntimeError (Celery retries on this)."""
        _reset_scorer()
        with patch("transformers.pipeline", side_effect=OSError("model not found")):
            with pytest.raises(RuntimeError, match="Failed to load sentiment model"):
                sentiment_module._get_scorer()

    def test_scorer_singleton_loaded_once(self):
        """Second call to _get_scorer reuses existing instance — no double load."""
        _reset_scorer()
        mock_pipeline = MagicMock()
        with patch("transformers.pipeline", return_value=mock_pipeline) as mock_cls:
            sentiment_module._get_scorer()
            sentiment_module._get_scorer()

        mock_cls.assert_called_once()
