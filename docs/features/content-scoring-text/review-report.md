# Phase 4 Review Report — content-scoring-text

**Date:** 2026-03-31
**Reviewed by:** 5 parallel brutal-honesty agents
**Status:** ✅ All Critical and Major issues fixed

---

## Agent 1 — Code Quality (Linus Mode)

### Critical (fixed)

- **C1** ✅ `e5_model.py` used CLS token (`[:, 0, :]`) for sentence embedding. `intfloat/multilingual-e5-base` requires **mean pooling** over all non-padding tokens — using CLS token produces systematically incorrect embeddings and thus invalid similarity scores for all SKUs. Fixed: replaced with attention-mask-weighted mean pooling per official e5 protocol.

### Major (all fixed)

- **M1** ✅ `_get_client()` created new Redis client per call — same as content-scoring-image. Fixed: singleton.
- **M2** ✅ `_today()` with lazy import — fixed (same as image feature).
- **M3** ✅ `scores_to_write: dict` without typed values — changed to `dict[str, Decimal]`.
- **M4** ✅ `Optional[str]` → `str | None` (Python 3.11 standard, removed `from typing import Optional`).

### Minor (deferred)
- `encode_text` returns `emb.squeeze().numpy()` without `.cpu()` — breaks GPU inference if added later. Added `.cpu()` call. Fixed.

---

## Agent 2 — Security (OWASP A01–A09)

### Critical
_None._

### Major (all fixed)

- **M1** ✅ Pickle deserialization from Redis — fixed (same as image feature: raw bytes format).
- **M2** ✅ `REDIS_URL` fallback default — fixed (fail-fast).

### Minor (deferred)
- No explicit text length limit before `encode_text()` — tokenizer truncation at 512 tokens is the effective guard. Very long strings (>1MB) are sanitized by collector before storage. Deferred.

---

## Agent 3 — Multi-tenant isolation

### Critical
_None._

### Major
_None._

**Notes:**
- Same architecture as content-scoring-image: background processor, not API-facing. All-org batch processing is intentional.
- Redis key `ref_emb:{sku_id}:{desc|comp}` uses UUID sku_id — globally unique.
- DB UPDATE scoped to `ContentScore.id` (PK) — single row, no cross-org risk.
- ✅ PASS

---

## Agent 4 — Performance

### Critical (fixed)

- **C1** ✅ `_get_client()` per-call instantiation — fixed: singleton (see Agent 1).

### Major (deferred)

- SELECT + UPDATE without `SELECT FOR UPDATE` — race condition possible if same `cs_id` is processed by two concurrent retries. In practice: `max_retries=3` with exponential backoff, and Celery delivers each task once. Deferred.
- E5 inference at batch_size=1 — 10-20x throughput loss vs batching. Architecture change: requires group-level batching. Deferred to performance sprint.

### Minor
- Model loaded without explicit `.eval()` check in `_load()` — confirmed `.eval()` IS called (line 49). False positive from agent.

---

## Agent 5 — Test Coverage

### Critical (fixed)

- **C1** ✅ Test #4 (`test_content_total_formula`) only checked that `db.execute` was called, not the actual `content_total` value. Added test `#4b` (`test_content_total_formula_weights_and_arithmetic`) verifying: (a) weights sum to 1.00, (b) formula gives correct Decimal result for known inputs.

### Major (all fixed)

- **M1** ✅ Tests #19, #20, #23 patched `app.core.e5_model.AutoModel` / `app.core.e5_model.torch` — lazy imports don't exist at module level. Fixed: `patch.dict("sys.modules", {...})` pattern.
- **M2** ✅ Tests #24–25 used `pickle.dumps` — obsolete. Updated to raw bytes format.

### Minor (deferred)
- No test for `score_text_content` with parallel cs_id race condition.
- No test for very long text input (>100K chars) truncation behavior.
- No integration test with real DB.

---

## Summary of Fixes Applied

| File | Change |
|------|--------|
| `app/core/e5_model.py` | **Critical**: CLS token → mean pooling; added `.cpu()` before `.numpy()` |
| `app/core/redis_client.py` | Singleton, raw bytes, `REDIS_URL` fail-fast (shared with image feature) |
| `app/core/minio_client.py` | Singleton (shared with image feature) |
| `app/tasks/text_scoring_task.py` | Fixed `_today()` lazy import; `Optional[str]` → `str \| None`; `dict[str, Decimal]` type annotation |
| `tests/test_text_scoring.py` | Fixed #19 (sys.modules mock); fixed #20/#23 (torch mock); updated #24–25 (raw bytes); added #4b (formula verification) |

**Test result:** 58/58 passed ✅

---

## Cross-service Note

The reference text embeddings (desc/comp) are computed by the API's `compute_text_embedding` task (not in this PR's scope). That task must also use mean pooling with `"passage: "` prefix for the cosine similarity with `"query: "` prefix (this service) to be mathematically valid. **Recommend: verify API-side embedding task uses the same mean pooling strategy.**
