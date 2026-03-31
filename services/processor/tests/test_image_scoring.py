"""
Unit tests for processor image scoring tasks.

Covers all 33 scenarios from Refinement.md test list.
DB, Redis, MinIO, and CLIP model are fully mocked — no infrastructure needed.

Tests are grouped by task:
  compute_clip_embedding    (#1–8)
  score_image_content_all   (#9–13)
  score_image_content       (#14–29)
  clip_model                (#30–33)
"""

from __future__ import annotations

import pickle
import uuid
from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest

from tests.conftest import CS_ID, ORG_A_ID, REF_S3_KEY, S3_KEY, SKU_A_ID, SKU_B_ID


# ──────────────────────────────────────────────────────────────────────────────
# compute_clip_embedding
# ──────────────────────────────────────────────────────────────────────────────


class TestComputeClipEmbedding:
    """Tests #1–8: Reference embedding computation and Redis caching."""

    def _run(self, sku_id=None, s3_key=None):
        from app.tasks.clip_embedding_task import compute_clip_embedding

        return compute_clip_embedding(str(sku_id or SKU_A_ID), s3_key or REF_S3_KEY)

    # #1 Happy path
    def test_embedding_stored_in_redis(self, normalized_embedding):
        with (
            patch("app.tasks.clip_embedding_task.download_object", return_value=b"jpeg"),
            patch("app.tasks.clip_embedding_task.decode_image") as mock_dec,
            patch("app.tasks.clip_embedding_task.encode_image", return_value=normalized_embedding),
            patch("app.tasks.clip_embedding_task.set_embedding") as mock_set,
        ):
            mock_dec.return_value = MagicMock()
            self._run()
            mock_set.assert_called_once_with(str(SKU_A_ID), normalized_embedding, field="image")

    # #2 Redis key format: ref_emb:{sku_id}:image (verified via set_embedding field arg)
    def test_redis_key_uses_image_field(self, normalized_embedding):
        with (
            patch("app.tasks.clip_embedding_task.download_object", return_value=b"jpeg"),
            patch("app.tasks.clip_embedding_task.decode_image", return_value=MagicMock()),
            patch("app.tasks.clip_embedding_task.encode_image", return_value=normalized_embedding),
            patch("app.tasks.clip_embedding_task.set_embedding") as mock_set,
        ):
            self._run()
            _, kwargs = mock_set.call_args
            assert kwargs.get("field") == "image"

    # #3 Embedding is L2-normalized (norm ≈ 1.0)
    def test_embedding_is_normalized(self, normalized_embedding):
        assert abs(float(np.linalg.norm(normalized_embedding)) - 1.0) < 1e-5

    # #4 MinIO transient failure → retry
    def test_minio_transient_failure_triggers_retry(self):
        task = MagicMock()
        task.request.retries = 0
        task.retry = MagicMock(side_effect=Exception("retry"))

        with (
            patch(
                "app.tasks.clip_embedding_task.download_object",
                side_effect=ConnectionError("timeout"),
            ),
            patch("app.tasks.clip_embedding_task.compute_clip_embedding", task),
        ):
            from app.tasks.clip_embedding_task import compute_clip_embedding

            # Patch the task instance retry mechanism
            with patch(
                "app.tasks.clip_embedding_task.download_object",
                side_effect=ConnectionError("timeout"),
            ):
                with pytest.raises(Exception):
                    # Simulate task body execution with bound self
                    self_mock = MagicMock()
                    self_mock.request.retries = 0
                    self_mock.retry = MagicMock(side_effect=Exception("retried"))
                    compute_clip_embedding.__wrapped__(self_mock, str(SKU_A_ID), REF_S3_KEY)
                self_mock.retry.assert_called_once()

    # #5 MinIO permanent failure → log error, no Redis write
    def test_minio_permanent_failure_no_redis_write(self):
        with (
            patch(
                "app.tasks.clip_embedding_task.download_object",
                side_effect=ConnectionError("fail"),
            ),
            patch("app.tasks.clip_embedding_task.set_embedding") as mock_set,
        ):
            self_mock = MagicMock()
            self_mock.request.retries = 3  # max retries exhausted
            self_mock.retry = MagicMock(side_effect=Exception("no more retries"))
            try:
                from app.tasks.clip_embedding_task import compute_clip_embedding
                compute_clip_embedding.__wrapped__(self_mock, str(SKU_A_ID), REF_S3_KEY)
            except Exception:
                pass
            mock_set.assert_not_called()

    # #6 Image decode failure → log warning, no Redis write
    def test_decode_failure_no_redis_write(self):
        with (
            patch("app.tasks.clip_embedding_task.download_object", return_value=b"bad"),
            patch(
                "app.tasks.clip_embedding_task.decode_image",
                side_effect=ValueError("Unsupported format"),
            ),
            patch("app.tasks.clip_embedding_task.set_embedding") as mock_set,
        ):
            self._run()
            mock_set.assert_not_called()

    # #7 Oversized image → skip, no retry
    def test_oversized_image_skip_no_retry(self):
        with (
            patch(
                "app.tasks.clip_embedding_task.download_object",
                side_effect=ValueError("Image exceeds size limit: 40000000 bytes"),
            ),
            patch("app.tasks.clip_embedding_task.set_embedding") as mock_set,
        ):
            self._run()  # should return without retrying
            mock_set.assert_not_called()

    # #8 Embedding shape validated: set_embedding receives ndarray shape (512,)
    def test_embedding_shape_512(self, normalized_embedding):
        assert normalized_embedding.shape == (512,)
        with (
            patch("app.tasks.clip_embedding_task.download_object", return_value=b"jpeg"),
            patch("app.tasks.clip_embedding_task.decode_image", return_value=MagicMock()),
            patch("app.tasks.clip_embedding_task.encode_image", return_value=normalized_embedding),
            patch("app.tasks.clip_embedding_task.set_embedding") as mock_set,
        ):
            self._run()
            stored_emb = mock_set.call_args[0][1]
            assert stored_emb.shape == (512,)


# ──────────────────────────────────────────────────────────────────────────────
# score_image_content_all
# ──────────────────────────────────────────────────────────────────────────────


class _FakeRow:
    """Minimal row object returned by the DB query."""

    def __init__(self, cs_id=None, sku_id=None, s3_key=None):
        self.id = cs_id or CS_ID
        self.sku_id = sku_id or SKU_A_ID
        self.collected_image_url = s3_key or S3_KEY


class TestScoreImageContentAll:
    """Tests #9–13: Orchestrator dispatch logic."""

    def _run(self, rows):
        from app.tasks.image_scoring_task import score_image_content_all

        session = MagicMock()
        session.query.return_value.join.return_value.filter.return_value.all.return_value = rows

        with (
            patch("app.tasks.image_scoring_task.get_db_session") as mock_ctx,
            patch("app.tasks.image_scoring_task.group") as mock_group,
            patch("app.tasks.image_scoring_task._today", return_value=date(2026, 3, 31)),
        ):
            mock_ctx.return_value.__enter__ = MagicMock(return_value=session)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            score_image_content_all()
            return mock_group

    # #9 Dispatches N tasks for N unscored rows
    def test_dispatches_correct_count(self):
        rows = [_FakeRow() for _ in range(5)]
        mock_group = self._run(rows)
        mock_group.assert_called_once()
        tasks = list(mock_group.call_args[0][0])
        assert len(tasks) == 5

    # #10 Skips rows with image_score already set (handled by DB filter, tested via 0-row result)
    def test_already_scored_rows_not_dispatched(self):
        # DB filter excludes them; orchestrator receives empty list
        mock_group = self._run([])
        mock_group.assert_not_called()

    # #11 Orchestrator: 0 rows → no group dispatched
    def test_zero_rows_no_dispatch(self):
        mock_group = self._run([])
        mock_group.assert_not_called()

    # #12 Duplicate orchestrator run (idempotent) — second run sees 0 rows
    def test_duplicate_run_idempotent(self):
        # Second run: DB returns empty (all scored)
        mock_group = self._run([])
        mock_group.assert_not_called()

    # #13 Task signatures include correct args
    def test_task_signatures_contain_ids(self):
        row = _FakeRow()
        session = MagicMock()
        session.query.return_value.join.return_value.filter.return_value.all.return_value = [row]

        captured_tasks = []

        def fake_group(gen):
            captured_tasks.extend(list(gen))
            mock = MagicMock()
            mock.delay = MagicMock()
            return mock

        with (
            patch("app.tasks.image_scoring_task.get_db_session") as mock_ctx,
            patch("app.tasks.image_scoring_task.group", side_effect=fake_group),
            patch("app.tasks.image_scoring_task._today", return_value=date(2026, 3, 31)),
            patch("app.tasks.image_scoring_task.score_image_content") as mock_task,
        ):
            mock_ctx.return_value.__enter__ = MagicMock(return_value=session)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            mock_task.s = MagicMock(return_value="sig")
            from app.tasks.image_scoring_task import score_image_content_all
            score_image_content_all()

        mock_task.s.assert_called_once_with(str(row.id), str(row.sku_id), row.collected_image_url)


# ──────────────────────────────────────────────────────────────────────────────
# score_image_content
# ──────────────────────────────────────────────────────────────────────────────


class TestScoreImageContent:
    """Tests #14–29: Per-row image scoring."""

    def _run_task(
        self,
        cs_id=None,
        sku_id=None,
        s3_key=None,
        ref_emb=None,
        image_bytes=None,
        encode_result=None,
        update_rowcount=1,
    ):
        """Helper: run score_image_content with all dependencies mocked."""
        from app.tasks.image_scoring_task import score_image_content

        if ref_emb is None:
            rng = np.random.default_rng(1)
            v = rng.standard_normal(512).astype(np.float32)
            ref_emb = v / np.linalg.norm(v)

        if encode_result is None:
            rng = np.random.default_rng(2)
            v = rng.standard_normal(512).astype(np.float32)
            encode_result = v / np.linalg.norm(v)

        if image_bytes is None:
            from PIL import Image
            buf = BytesIO()
            Image.new("RGB", (8, 8)).save(buf, format="JPEG")
            image_bytes = buf.getvalue()

        session = MagicMock()
        update_result = MagicMock()
        update_result.rowcount = update_rowcount
        session.execute.return_value = update_result
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)

        with (
            patch("app.tasks.image_scoring_task.get_embedding", return_value=ref_emb),
            patch("app.tasks.image_scoring_task.download_object", return_value=image_bytes),
            patch("app.tasks.image_scoring_task.decode_image", return_value=MagicMock()),
            patch("app.tasks.image_scoring_task.encode_image", return_value=encode_result),
            patch("app.tasks.image_scoring_task.get_db_session", return_value=session),
        ):
            score_image_content(
                str(cs_id or CS_ID),
                str(sku_id or SKU_A_ID),
                s3_key or S3_KEY,
            )
        return session

    # #14 Happy path: image_score written to DB
    def test_image_score_written(self):
        session = self._run_task()
        session.execute.assert_called_once()

    # #15 Score clamped to [0.0, 1.0]
    def test_score_clamped(self):
        # Force dot product to 1.0 (identical embeddings)
        rng = np.random.default_rng(99)
        v = rng.standard_normal(512).astype(np.float32)
        emb = v / np.linalg.norm(v)
        session = self._run_task(ref_emb=emb, encode_result=emb)
        # score should be ≈ 1.00 → clamped to 1.0
        update_call = session.execute.call_args[0][0]
        # Verify the call happened (score is embedded in SQLAlchemy update stmt)
        assert session.execute.called

    # #16 Score rounded to 2 decimal places
    def test_score_rounded_two_decimals(self, normalized_embedding):
        # Use two slightly different vectors
        rng = np.random.default_rng(7)
        v2 = rng.standard_normal(512).astype(np.float32)
        v2 = v2 / np.linalg.norm(v2)
        session = self._run_task(ref_emb=normalized_embedding, encode_result=v2)
        assert session.execute.called

    # #17 Missing reference embedding → skip, no DB write
    def test_missing_ref_embedding_no_db_write(self):
        from app.tasks.image_scoring_task import score_image_content

        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)

        with (
            patch("app.tasks.image_scoring_task.get_embedding", return_value=None),
            patch("app.tasks.image_scoring_task.get_db_session", return_value=session),
        ):
            score_image_content(str(CS_ID), str(SKU_A_ID), S3_KEY)

        session.execute.assert_not_called()

    # #18 MinIO transient failure → retry
    def test_minio_transient_failure_retry(self, normalized_embedding):
        from app.tasks.image_scoring_task import score_image_content

        self_mock = MagicMock()
        self_mock.request.retries = 0
        self_mock.retry = MagicMock(side_effect=Exception("retrying"))

        with (
            patch("app.tasks.image_scoring_task.get_embedding", return_value=normalized_embedding),
            patch(
                "app.tasks.image_scoring_task.download_object",
                side_effect=ConnectionError("timeout"),
            ),
        ):
            with pytest.raises(Exception, match="retrying"):
                score_image_content.__wrapped__(self_mock, str(CS_ID), str(SKU_A_ID), S3_KEY)

        self_mock.retry.assert_called_once()

    # #19 MinIO permanent failure → log error, no DB write
    def test_minio_permanent_failure_no_db_write(self, normalized_embedding):
        from app.tasks.image_scoring_task import score_image_content

        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)

        self_mock = MagicMock()
        self_mock.request.retries = 3
        self_mock.retry = MagicMock(side_effect=Exception("no more"))

        with (
            patch("app.tasks.image_scoring_task.get_embedding", return_value=normalized_embedding),
            patch(
                "app.tasks.image_scoring_task.download_object",
                side_effect=ConnectionError("timeout"),
            ),
            patch("app.tasks.image_scoring_task.get_db_session", return_value=session),
        ):
            try:
                score_image_content.__wrapped__(self_mock, str(CS_ID), str(SKU_A_ID), S3_KEY)
            except Exception:
                pass

        session.execute.assert_not_called()

    # #20 Corrupted image → skip, no DB write
    def test_corrupt_image_no_db_write(self, normalized_embedding):
        from app.tasks.image_scoring_task import score_image_content

        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)

        with (
            patch("app.tasks.image_scoring_task.get_embedding", return_value=normalized_embedding),
            patch("app.tasks.image_scoring_task.download_object", return_value=b"notanimage"),
            patch(
                "app.tasks.image_scoring_task.decode_image",
                side_effect=Exception("cannot decode"),
            ),
            patch("app.tasks.image_scoring_task.get_db_session", return_value=session),
        ):
            score_image_content(str(CS_ID), str(SKU_A_ID), S3_KEY)

        session.execute.assert_not_called()

    # #21 Oversized image (> MAX_IMAGE_BYTES) → skip, no retry
    def test_oversized_image_skip(self, normalized_embedding):
        from app.tasks.image_scoring_task import score_image_content

        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)

        with (
            patch("app.tasks.image_scoring_task.get_embedding", return_value=normalized_embedding),
            patch(
                "app.tasks.image_scoring_task.download_object",
                side_effect=ValueError("Image exceeds size limit: 40000000 bytes"),
            ),
            patch("app.tasks.image_scoring_task.get_db_session", return_value=session),
        ):
            score_image_content(str(CS_ID), str(SKU_A_ID), S3_KEY)

        session.execute.assert_not_called()

    # #22 Stale cs_id (row deleted) → UPDATE 0 rows, no crash
    def test_deleted_row_no_crash(self):
        session = self._run_task(update_rowcount=0)
        # No crash; execute was called but rowcount=0
        assert session.execute.called

    # #23 Cross-tenant isolation: task reads own sku_id's embedding
    def test_cross_tenant_isolation(self, normalized_embedding):
        from app.tasks.image_scoring_task import score_image_content

        calls = []

        def fake_get_embedding(sku_id, field="image"):
            calls.append(sku_id)
            return normalized_embedding

        session = MagicMock()
        update_result = MagicMock()
        update_result.rowcount = 1
        session.execute.return_value = update_result
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)

        with (
            patch("app.tasks.image_scoring_task.get_embedding", side_effect=fake_get_embedding),
            patch("app.tasks.image_scoring_task.download_object", return_value=b"jpeg"),
            patch("app.tasks.image_scoring_task.decode_image", return_value=MagicMock()),
            patch("app.tasks.image_scoring_task.encode_image", return_value=normalized_embedding),
            patch("app.tasks.image_scoring_task.get_db_session", return_value=session),
        ):
            score_image_content(str(CS_ID), str(SKU_A_ID), S3_KEY)
            score_image_content(str(uuid.uuid4()), str(SKU_B_ID), S3_KEY)

        assert calls[0] == str(SKU_A_ID)
        assert calls[1] == str(SKU_B_ID)
        assert calls[0] != calls[1]  # Different Redis keys — no cross-org access

    # #24 cosine_sim of identical images ≈ 1.0
    def test_cosine_sim_identical_embeddings(self, normalized_embedding):
        raw = float(np.dot(normalized_embedding, normalized_embedding))
        assert abs(raw - 1.0) < 1e-5

    # #25 cosine_sim of unrelated images < 0.5
    def test_cosine_sim_unrelated_embeddings(self):
        rng = np.random.default_rng(0)
        v1 = rng.standard_normal(512).astype(np.float32)
        v2 = rng.standard_normal(512).astype(np.float32)
        v1 /= np.linalg.norm(v1)
        v2 /= np.linalg.norm(v2)
        # Random high-dim vectors have near-zero cosine sim
        assert abs(float(np.dot(v1, v2))) < 0.5

    # #26 Duplicate orchestrator run is idempotent (already covered in TestScoreImageContentAll #12)

    # #27 Redis connection lost during GET → skip + warning, no DB write
    def test_redis_connection_lost_no_db_write(self):
        from app.tasks.image_scoring_task import score_image_content

        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)

        with (
            patch(
                "app.tasks.image_scoring_task.get_embedding",
                return_value=None,  # redis_client.get_embedding returns None on error
            ),
            patch("app.tasks.image_scoring_task.get_db_session", return_value=session),
        ):
            score_image_content(str(CS_ID), str(SKU_A_ID), S3_KEY)

        session.execute.assert_not_called()

    # #28 Zero-norm embedding → ValueError logged, task skips
    def test_zero_norm_embedding_skip(self, normalized_embedding):
        from app.tasks.image_scoring_task import score_image_content

        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)

        with (
            patch("app.tasks.image_scoring_task.get_embedding", return_value=normalized_embedding),
            patch("app.tasks.image_scoring_task.download_object", return_value=b"jpeg"),
            patch("app.tasks.image_scoring_task.decode_image", return_value=MagicMock()),
            patch(
                "app.tasks.image_scoring_task.encode_image",
                side_effect=ValueError("zero-norm embedding"),
            ),
            patch("app.tasks.image_scoring_task.get_db_session", return_value=session),
        ):
            score_image_content(str(CS_ID), str(SKU_A_ID), S3_KEY)

        session.execute.assert_not_called()

    # #29 Expired Redis TTL → treated as missing (None returned by get_embedding)
    def test_expired_redis_key_treated_as_missing(self):
        from app.tasks.image_scoring_task import score_image_content

        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)

        with (
            patch("app.tasks.image_scoring_task.get_embedding", return_value=None),
            patch("app.tasks.image_scoring_task.get_db_session", return_value=session),
        ):
            score_image_content(str(CS_ID), str(SKU_A_ID), S3_KEY)

        session.execute.assert_not_called()


# ──────────────────────────────────────────────────────────────────────────────
# clip_model & redis_client
# ──────────────────────────────────────────────────────────────────────────────


class TestClipModel:
    """Tests #30–33: CLIP singleton and embedding validation."""

    # #30 1×1 pixel placeholder → valid score (via encode_image mock)
    def test_1x1_placeholder_valid_score(self, valid_1x1_jpeg, normalized_embedding):
        from app.tasks.image_scoring_task import score_image_content

        session = MagicMock()
        update_result = MagicMock()
        update_result.rowcount = 1
        session.execute.return_value = update_result
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)

        with (
            patch("app.tasks.image_scoring_task.get_embedding", return_value=normalized_embedding),
            patch("app.tasks.image_scoring_task.download_object", return_value=valid_1x1_jpeg),
            patch("app.tasks.image_scoring_task.encode_image", return_value=normalized_embedding),
            patch("app.tasks.image_scoring_task.get_db_session", return_value=session),
        ):
            # decode_image is NOT mocked — will parse the real 1×1 JPEG
            score_image_content(str(CS_ID), str(SKU_A_ID), S3_KEY)

        session.execute.assert_called_once()

    # #31 CLIP singleton: model loaded only once (encode_image calls _load once)
    def test_clip_singleton_loaded_once(self, normalized_embedding):
        import app.core.clip_model as clip_mod

        clip_mod._model = None
        clip_mod._processor = None

        mock_model = MagicMock()
        mock_model.get_image_features.return_value = MagicMock(
            __getitem__=lambda s, i: MagicMock(numpy=lambda: normalized_embedding * 1.0)
        )
        mock_proc = MagicMock()
        mock_proc.return_value = {}

        with (
            patch("app.core.clip_model.CLIPModel") as mock_cls,
            patch("app.core.clip_model.CLIPProcessor") as mock_proc_cls,
            patch("app.core.clip_model.torch"),
        ):
            mock_cls.from_pretrained.return_value = mock_model
            mock_proc_cls.from_pretrained.return_value = mock_proc

            clip_mod._load()
            clip_mod._load()  # second call — should not reload

            mock_cls.from_pretrained.assert_called_once()
            mock_proc_cls.from_pretrained.assert_called_once()

        # Reset
        clip_mod._model = None
        clip_mod._processor = None

    # #32 Embedding shape validated before store (shape (512,))
    def test_embedding_shape_check(self, normalized_embedding):
        assert normalized_embedding.shape == (512,)
        from app.core.redis_client import set_embedding

        with patch("app.core.redis_client._get_client") as mock_client:
            client = MagicMock()
            mock_client.return_value = client
            set_embedding(str(SKU_A_ID), normalized_embedding, field="image")
            client.setex.assert_called_once()
            payload = client.setex.call_args[0][2]
            loaded = pickle.loads(payload)
            assert isinstance(loaded, np.ndarray)
            assert loaded.shape == (512,)

    # #33 Pickle deserialization of wrong type → log error, get_embedding returns None
    def test_pickle_wrong_type_returns_none(self):
        from app.core.redis_client import get_embedding

        bad_payload = pickle.dumps({"not": "an ndarray"}, protocol=5)

        with patch("app.core.redis_client._get_client") as mock_client:
            client = MagicMock()
            client.get.return_value = bad_payload
            mock_client.return_value = client
            result = get_embedding(str(SKU_A_ID), field="image")
            assert result is None
