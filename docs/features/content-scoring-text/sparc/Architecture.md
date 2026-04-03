# Architecture — Content Scoring: Text (multilingual-e5)

**SPARC Phase 5: Architecture** | Feature: content-scoring-text

---

## 1. Component Overview

```
services/processor/
├── app/
│   ├── core/
│   │   ├── clip_model.py        # CLIP singleton (already exists)
│   │   └── e5_model.py          # NEW: E5 singleton (intfloat/multilingual-e5-base)
│   └── tasks/
│       ├── image_scoring_task.py    # already exists
│       ├── text_scoring_task.py     # NEW: score_text_content (per-row)
│       └── text_orchestrator.py     # NEW: score_text_content_all (Beat trigger)

services/api/
└── app/
    └── tasks/
        └── embedding_tasks.py       # already exists: compute_text_embedding writes Redis
```

No new DB tables. No new Alembic migration. Reads and writes `content_scores` (existing table).

---

## 2. E5 Model Singleton

```python
# services/processor/app/core/e5_model.py

from sentence_transformers import SentenceTransformer
import numpy as np
import threading

_model: SentenceTransformer | None = None
_lock = threading.Lock()

def get_e5_model() -> SentenceTransformer:
    """
    Lazy-loaded singleton. Thread-safe via double-checked locking.
    Model: intfloat/multilingual-e5-base (dim=768).
    Already downloaded to HuggingFace cache by embedding_tasks.py on first run.
    Memory: ~1.1 GB. Loaded once per worker process.
    """
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                _model = SentenceTransformer("intfloat/multilingual-e5-base")
    return _model
```

**Pattern:** Identical to `clip_model.py` singleton. Ensures model loads once per Celery worker process, not once per task.

**Memory constraint:** CLIP (340 MB) + E5 (1.1 GB) = ~1.4 GB total. `CELERYD_CONCURRENCY=1` for the processor service — no concurrent workers within the same process.

---

## 3. Redis Key Contract

Reference embeddings are stored by `compute_text_embedding` (in `services/api/app/tasks/embedding_tasks.py`) when a SKU's reference texts are uploaded:

```
ref_emb:{sku_id}:desc  →  pickle.dumps(np.ndarray shape=(768,), protocol=5)
ref_emb:{sku_id}:comp  →  pickle.dumps(np.ndarray shape=(768,), protocol=5)
TTL: 2592000 s (30 days)
```

The scoring task reads these keys. If a key is missing (TTL expired or reference not yet uploaded), the field is skipped with a warning log — it is NOT an error.

**Shape validation:** After `pickle.loads()`, verify `emb.shape == (768,)`. If shape is `(512,)` (CLIP embedding accidentally stored), log error and skip — do not compute cosine similarity with wrong-dim vectors.

---

## 4. Cosine Similarity Computation

```python
def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Both inputs must be L2-normalized before calling.
    dot product of unit vectors = cosine similarity in [-1, 1].
    Clamped to [0.0, 1.0] for business use (negative similarity = 0).
    """
    sim = float(np.dot(a, b))
    return max(0.0, min(1.0, round(sim, 2)))
```

**E5 prefix protocol:** `intfloat/multilingual-e5-base` requires "query: " prefix for query-side encoding. Reference embeddings are stored with "passage: " prefix (handled by `embedding_tasks.py`). The scoring task uses "query: " prefix:

```python
query_emb = model.encode(
    f"query: {text}",
    normalize_embeddings=True,  # returns L2-normalized vector
    convert_to_numpy=True,
    max_length=512,             # e5-base context limit
)
```

---

## 5. Celery Task Design

### score_text_content (per-row task)

```python
# services/processor/app/tasks/text_scoring_task.py

@celery_app.task(bind=True, max_retries=3, name="processor.score_text_content")
def score_text_content(
    self,
    content_score_id: str,
    sku_id: str,
    description: str | None,
    composition: str | None,
):
    """
    1. Load E5 model singleton.
    2. Encode description (if not None/empty) → cosine sim with ref_emb:{sku_id}:desc.
    3. Encode composition (if not None/empty) → cosine sim with ref_emb:{sku_id}:comp.
    4. Compute content_total if image_score IS NOT NULL (re-read from DB).
    5. Single UPDATE: description_score, composition_score, content_total atomically.
    Retry on Redis connection error or DB transient error (countdown=2**retries).
    """
```

**Retry scope:** `max_retries=3, countdown=2**self.request.retries`. Only retries on `redis.exceptions.ConnectionError` and `sqlalchemy.exc.OperationalError`. Does NOT retry on missing Redis key (expected condition, not an error).

**Independence of description and composition:** Each field is scored independently. If `ref_emb:{sku_id}:desc` is missing, composition scoring still proceeds. The DB UPDATE writes whatever was computed.

### score_text_content_all (orchestrator)

```python
# services/processor/app/tasks/text_orchestrator.py

@celery_app.task(name="processor.score_text_content_all")
def score_text_content_all():
    """
    Queries content_scores WHERE:
      scored_at = today()
      AND collected_description IS NOT NULL
      AND (description_score IS NULL OR composition_score IS NULL)

    Dispatches score_text_content.delay() for each row via Celery group.
    Passes (id, sku_platform_id → sku_id lookup, description, composition) as primitives.
    """
```

**No org_id filtering in orchestrator:** Same safe cross-org pattern as image scoring. The per-row task uses `content_scores.id` (PK) for the UPDATE — structurally scoped to exactly one row, one tenant.

**Celery Beat schedule:** `06:30 UTC` (30 minutes after image scoring completes at ~06:00–06:20).

---

## 6. DB Interaction

### Read (orchestrator)

```sql
SELECT
    cs.id,
    sp.sku_id,
    cs.collected_description,
    cs.collected_composition
FROM content_scores cs
JOIN sku_platforms sp ON sp.id = cs.sku_platform_id
WHERE DATE(cs.scored_at) = CURRENT_DATE
  AND cs.collected_description IS NOT NULL
  AND (cs.description_score IS NULL OR cs.composition_score IS NULL);
```

### Read (per-task: image_score for content_total)

```sql
SELECT image_score FROM content_scores WHERE id = :content_score_id;
```

### Write (per-task: atomic update)

```sql
UPDATE content_scores
SET
    description_score = :desc_score,   -- NULL if skipped
    composition_score = :comp_score,   -- NULL if skipped
    content_total     = :total          -- NULL if any component missing
WHERE id = :content_score_id;
```

Single UPDATE, single transaction. No partial writes.

---

## 7. content_total Formula

```python
def _compute_total(
    image_score: float | None,
    description_score: float | None,
    composition_score: float | None,
) -> float | None:
    if image_score is None or description_score is None or composition_score is None:
        return None
    return round(0.40 * image_score + 0.35 * description_score + 0.25 * composition_score, 2)
```

Weights are **hardcoded** (no config table). Future weight changes require code change + recompute job (v2.0 feature).

---

## 8. File Structure

```
services/processor/app/
├── core/
│   ├── clip_model.py           # existing
│   └── e5_model.py             # NEW
└── tasks/
    ├── image_scoring_task.py   # existing
    ├── text_scoring_task.py    # NEW: score_text_content
    └── text_orchestrator.py    # NEW: score_text_content_all
```

No changes to `services/api/`. `embedding_tasks.py` already populates Redis — no modification needed.

---

## 9. Key Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Model loading | Singleton per worker process | 1.1 GB — must not reload per task |
| Prefix | "query: " on collected text | e5 query-document asymmetric embedding protocol |
| Redis key format | `ref_emb:{sku_id}:desc` | Matches existing `embedding_tasks.py` convention |
| content_total write | Same transaction as text scores | Prevents partial state (2 of 3 written, total missing) |
| Composition skip | Graceful — description still scored | Many SKUs have no composition text |
| Orchestrator scope | All orgs, today's unscored rows | Same safe pattern as image scoring orchestrator |
| Concurrency | CELERYD_CONCURRENCY=1 | CLIP + E5 combined memory constraint |
| Max text length | 512 tokens (truncate) | E5 context limit; longer text truncated by model internally |
