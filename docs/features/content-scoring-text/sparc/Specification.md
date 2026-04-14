# Specification — Content Scoring: Text (multilingual-e5)

---

## User Stories

### US-1: Daily Text Scoring
```
As a brand manager,
I want description and composition scores calculated automatically every morning,
So that I see the full content quality picture (text + image) by the time I start work.

Acceptance Criteria:
  Given image scoring completed at ~06:00–06:20 UTC
  When Celery Beat triggers score_text_content_all at 06:30 UTC
  Then the orchestrator queries content_scores WHERE:
       scored_at = today() AND collected_description IS NOT NULL
       AND (description_score IS NULL OR composition_score IS NULL)
  And dispatches one score_text_content task per matching row via Celery group
  And ≥ 99% of matching rows have description_score set within 5 minutes
       (verifiable: SELECT COUNT(*) ... WHERE description_score IS NULL → ~0)
  And if 0 rows match, no group is dispatched
```

### US-2: Per-row Text Scoring + content_total
```
As the platform,
I want each row's text scores and content_total computed atomically,
So that partial writes never produce misleading aggregated metrics.

Acceptance Criteria — description_score:
  Given a content_scores row with collected_description IS NOT NULL
  When score_text_content task runs
  Then it encodes collected_description with multilingual-e5-base (prefix "query: ")
  And loads ref_emb:{sku_id}:desc from Redis (768-dim ndarray)
  And computes cosine similarity = dot(collected_emb, ref_emb) [both L2-normalized]
  And writes description_score = clamp(score, 0.0, 1.0).round(2) to content_scores
  And if ref_emb:{sku_id}:desc missing in Redis: log warning, skip desc scoring
  And if collected_description is empty string after strip(): log warning, skip desc scoring

Acceptance Criteria — composition_score:
  Given a content_scores row with collected_composition IS NOT NULL
  When score_text_content task runs for the same row
  Then it encodes collected_composition with the same model (prefix "query: ")
  And loads ref_emb:{sku_id}:comp from Redis
  And writes composition_score = clamp(score, 0.0, 1.0).round(2)
  And if collected_composition IS NULL: skip composition scoring (description still scored)
  And if ref_emb:{sku_id}:comp missing: log warning, skip comp scoring

Acceptance Criteria — content_total:
  Given a content_scores row after text scoring completes
  When image_score IS NOT NULL AND description_score IS NOT NULL
       AND composition_score IS NOT NULL
  Then content_total = round(0.40*image_score + 0.35*description_score
       + 0.25*composition_score, 2) is written in the SAME DB transaction
  When any of the three scores is NULL
  Then content_total remains NULL (not written)

Acceptance Criteria — isolation:
  Given org A sku_id=SKU-A and org B sku_id=SKU-B
  When score_text_content_all runs
  Then SKU-A's task reads only ref_emb:{SKU-A}:desc and ref_emb:{SKU-A}:comp
  And DB UPDATE is scoped to content_scores.id (PK) — no cross-org write
```

---

## Non-Functional Requirements

| Category | Requirement |
|----------|-------------|
| Latency | 1000 SKU scored in ≤ 5 min (text only — no MinIO download) |
| Model | `intfloat/multilingual-e5-base`, dim=768 |
| Prefix | "query: " prepended to collected text (e5 query-document protocol) |
| Truncation | max_length=512 tokens (e5 context limit) |
| Redis shape | (768,) — separate validation from CLIP (512,) |
| Retry | max_retries=3, countdown=2^attempt (for Redis/DB transient errors) |
| Failure mode | Skip failed field, do NOT skip the other field (desc/comp independent) |
| Memory | ~1.1 GB RAM per worker (e5-base larger than CLIP) |
| Concurrency | CELERYD_CONCURRENCY=1 for processor (CLIP=340MB + e5=1.1GB ≈ 1.4GB total) |

---

## Data Contracts

### Redis Keys (written by API's compute_text_embedding task)
```
ref_emb:{sku_id}:desc  →  pickle.dumps(np.ndarray shape [768], protocol=5)
ref_emb:{sku_id}:comp  →  pickle.dumps(np.ndarray shape [768], protocol=5)
TTL: 2592000 s (30 days)
```

### ContentScore fields used
```
content_scores.id                   — PK (UPDATE target)
content_scores.sku_platform_id      — join to sku_platforms
content_scores.scored_at            — filter: = today
content_scores.collected_description — text input (nullable)
content_scores.collected_composition — text input (nullable)
content_scores.image_score          — read for content_total check
content_scores.description_score    — NUMERIC(5,2) written by this feature
content_scores.composition_score    — NUMERIC(5,2) written by this feature
content_scores.content_total        — NUMERIC(5,2) computed if all 3 present
```

### Celery task signatures
```python
# Beat trigger — daily 06:30 UTC
score_text_content_all.delay()

# Per-row (dispatched by orchestrator)
score_text_content.delay(
    content_score_id: str,   # content_scores.id
    sku_id: str,             # for Redis key lookup
    description: str | None, # collected_description
    composition: str | None,  # collected_composition
)
```

---

## Constraints

- E5 model: `intfloat/multilingual-e5-base` (same as already loaded in `embedding_tasks.py`)
- Text already in DB — NO MinIO download (unlike image scoring)
- `content_total` formula weights are hardcoded (no config table for MVP)
- composition may be NULL for many SKUs — graceful skip required
- Model loaded as singleton (same pattern as clip_model.py)
