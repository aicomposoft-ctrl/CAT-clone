"""
Unit tests for the score_pending_reviews Celery task (app/tasks/sentiment_task.py).

All tests use mocked DB and mocked score_batch — no real PostgreSQL or model required.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_row(review_id=None, review_text="Хорошо"):
    """Build a MagicMock row with id and review_text attributes."""
    row = MagicMock()
    row.id = review_id or uuid.uuid4()
    row.review_text = review_text
    return row


def _make_db_session(fetchall_return=None):
    """Build a mock db session that supports execute().fetchall() and execute() updates."""
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    fetch_result = MagicMock()
    fetch_result.fetchall.return_value = fetchall_return or []
    session.execute.return_value = fetch_result
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestScorePendingReviews:

    def _run_task(self, db_mock, score_batch_mock):
        """Run the task with mocked DB and score_batch."""
        with patch("app.tasks.sentiment_task.get_db_session", return_value=db_mock), \
             patch("app.tasks.sentiment_task.score_batch", side_effect=score_batch_mock):
            from app.tasks.sentiment_task import score_pending_reviews
            return score_pending_reviews()

    def test_no_pending_reviews_returns_zero_counts(self):
        """When sentiment IS NULL returns 0 rows, task returns {"scored": 0, "skipped": 0}."""
        db = _make_db_session(fetchall_return=[])
        result = self._run_task(db, lambda texts: [])
        assert result == {"scored": 0, "skipped": 0}

    def test_scores_all_valid_reviews(self):
        """50 reviews with non-empty text → all 50 scored."""
        rows = [_make_row(review_text=f"Отзыв {i}") for i in range(50)]
        db = _make_db_session(fetchall_return=rows)
        score_results = [("positive", 0.9)] * 50

        result = self._run_task(db, lambda texts: score_results[:len(texts)])
        assert result["scored"] == 50
        assert result["skipped"] == 0

    def test_skips_empty_text_reviews(self):
        """Reviews with empty text return (None, None) from score_batch → skipped."""
        rows = [
            _make_row(review_text="Хорошо"),
            _make_row(review_text=""),
            _make_row(review_text="   "),
        ]
        db = _make_db_session(fetchall_return=rows)

        def fake_score_batch(texts):
            return [
                ("positive", 0.9) if t and t.strip() else (None, None)
                for t in texts
            ]

        result = self._run_task(db, fake_score_batch)
        assert result["scored"] == 1
        assert result["skipped"] == 2

    def test_idempotent_on_already_scored_reviews(self):
        """
        If all reviews already have sentiment (WHERE sentiment IS NULL returns 0 rows),
        running the task again returns {"scored": 0, "skipped": 0} without any DB updates.
        """
        db = _make_db_session(fetchall_return=[])
        result = self._run_task(db, lambda texts: [])
        assert result == {"scored": 0, "skipped": 0}
        # The UPDATE branch is never reached — only the SELECT was executed
        # (execute is called once for SELECT; no second call for UPDATE)
        assert db.__enter__.return_value.execute.call_count == 1

    def test_mixed_valid_and_empty_updates_only_valid(self):
        """UPDATE only runs for reviews with non-null labels; skipped reviews not included."""
        rid1, rid2 = uuid.uuid4(), uuid.uuid4()
        rows = [
            _make_row(review_id=rid1, review_text="Плохо"),
            _make_row(review_id=rid2, review_text=""),
        ]
        db = _make_db_session(fetchall_return=rows)
        captured_updates = []

        def fake_score_batch(texts):
            return [("negative", 0.85), (None, None)]

        with patch("app.tasks.sentiment_task.get_db_session", return_value=db), \
             patch("app.tasks.sentiment_task.score_batch", side_effect=fake_score_batch):
            from app.tasks.sentiment_task import score_pending_reviews
            result = score_pending_reviews()

        assert result == {"scored": 1, "skipped": 1}


class TestScorePendingReviewsRetry:

    def test_runtime_error_triggers_celery_retry(self):
        """RuntimeError (model unavailable) → task.retry() called with exponential backoff."""
        rows = [_make_row(review_text="Хороший продукт")]
        db = _make_db_session(fetchall_return=rows)

        mock_task = MagicMock()
        mock_task.request.retries = 0
        mock_task.max_retries = 3
        mock_task.retry.side_effect = Exception("retry called")

        with patch("app.tasks.sentiment_task.get_db_session", return_value=db), \
             patch("app.tasks.sentiment_task.score_batch", side_effect=RuntimeError("model unavailable")):
            from app.tasks.sentiment_task import score_pending_reviews

            # Simulate bound task by calling with the self parameter
            with pytest.raises(Exception, match="retry called"):
                score_pending_reviews.__wrapped__(mock_task, batch_limit=1000)

        mock_task.retry.assert_called_once()
        _, kwargs = mock_task.retry.call_args
        assert kwargs["countdown"] == 60  # base: 60s * 2^0

    def test_exponential_backoff_on_second_retry(self):
        """Second retry uses countdown=120 (60 * 2^1)."""
        rows = [_make_row(review_text="Хороший продукт")]
        db = _make_db_session(fetchall_return=rows)

        mock_task = MagicMock()
        mock_task.request.retries = 1  # second attempt
        mock_task.max_retries = 3
        mock_task.retry.side_effect = Exception("retry called")

        with patch("app.tasks.sentiment_task.get_db_session", return_value=db), \
             patch("app.tasks.sentiment_task.score_batch", side_effect=RuntimeError("model unavailable")):
            from app.tasks.sentiment_task import score_pending_reviews

            with pytest.raises(Exception, match="retry called"):
                score_pending_reviews.__wrapped__(mock_task, batch_limit=1000)

        _, kwargs = mock_task.retry.call_args
        assert kwargs["countdown"] == 120  # 60 * 2^1
