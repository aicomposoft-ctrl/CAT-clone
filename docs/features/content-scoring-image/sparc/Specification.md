# Specification — Content Scoring: Image (CLIP)

---

## User Stories

### US-1: Reference Embedding Computation
```
As a brand manager,
I want my reference image embedding to be computed automatically when I upload it,
So that image scoring happens without manual intervention.

Acceptance Criteria:
  Given a reference image has been uploaded via POST /api/v1/catalog/skus/{id}/reference-image
  When the upload succeeds and S3 key is returned
  Then a Celery task `compute_clip_embedding` is dispatched with (sku_id, s3_key)
  And within 60 seconds the embedding is stored in Redis at ref_emb:{sku_id}:image
  And the embedding has TTL = 30 days
  And if Redis is unavailable, the task retries up to 3 times with exponential backoff
```

### US-2: Daily Image Scoring
```
As a brand manager,
I want image scores to be calculated every morning automatically,
So that I see fresh data by the time I start work.

Acceptance Criteria:
  Given collector has finished scraping by ~05:30 UTC
  When the Celery Beat schedule triggers score_image_content_all at 06:00 UTC
  Then all content_scores rows where scored_at = today AND image_score IS NULL
       AND collected_image_url IS NOT NULL are queued for scoring
  And each row is scored in parallel (Celery group)
  And image_score is written to the DB within 10 minutes for 1000 SKUs (CPU)
```

### US-3: Per-row Image Scoring
```
As the platform,
I want each image score to be computed independently,
So that failures in one SKU do not block others.

Acceptance Criteria:
  Given a content_scores row with collected_image_url (S3 key) and sku_id
  When score_image_content task runs for this row
  Then it downloads the collected image from MinIO
  And loads the reference embedding from Redis (ref_emb:{sku_id}:image)
  And computes CLIP cosine similarity in range [0.0, 1.0]
  And UPDATEs content_scores.image_score for this row
  And if reference embedding is missing in Redis, logs warning and skips (no DB write)
  And if MinIO image download fails, retries up to 3 times, then logs error and skips
```

### US-4: Multi-tenant Isolation
```
As an org administrator,
I want image scores to be isolated per organization,
So that org A cannot access or influence org B's scores.

Acceptance Criteria:
  Given org A and org B each have SKUs with content_scores for today
  When score_image_content_all runs
  Then org A's tasks use only org A's reference embeddings (ref_emb:{sku_a_id}:image)
  And org B's tasks use only org B's reference embeddings
  And cross-org embedding lookup is architecturally impossible (sku_id is org-scoped)
  And DB update filters by content_score.id (primary key) — no cross-row risk
```

---

## Non-Functional Requirements

| Category | Requirement |
|----------|-------------|
| Latency | 1000 SKU scored in ≤ 10 min on 4-core CPU |
| Batch size | CLIP inference batch = 32 images (memory/speed tradeoff) |
| Concurrency | Celery group — parallel per-row tasks, up to `CELERYD_CONCURRENCY` workers |
| Model loading | CLIP model loaded once per worker process (cached at module level) |
| Redis TTL | Embedding cache TTL = 30 days (matches reference upload TTL) |
| Retry | max_retries=3, countdown=2^attempt |
| Failure mode | Per-row failure → skip, log warning. Orchestrator always completes. |
| Memory | CLIP ViT-B/32 = ~340 MB RAM per worker |
| Docker | `mcr.microsoft.com/playwright/python` NOT needed — use `python:3.11-slim` + torch CPU |

---

## Data Contracts

### Redis Keys
```
ref_emb:{sku_id}:image  →  bytes (pickle.dumps of np.ndarray shape [512])
                           TTL: 2592000 s (30 days)
```

### ContentScore fields used
```
content_scores.id                  — primary key (filter for UPDATE)
content_scores.sku_platform_id     — join to sku_platforms
content_scores.scored_at           — filter: = today
content_scores.collected_image_url — S3 key for collected image (input)
content_scores.image_score         — NUMERIC(5,2) updated by this feature (output)
```

### Celery task signatures
```python
# Task 1: called by API after reference upload
compute_clip_embedding.delay(sku_id: str, s3_key: str)

# Task 2: Celery Beat trigger — daily 06:00 UTC
score_image_content_all.delay()

# Task 3: per-row scoring
score_image_content.delay(content_score_id: str, sku_id: str, s3_key: str)
```

---

## Constraints

- CPU-only inference for MVP (no CUDA required)
- Single processor worker instance (model loaded once per process)
- HuggingFace model downloads to `/root/.cache/huggingface/` — must be mounted volume in Docker
- MinIO client reused from `app/core/minio_client.py` pattern
- No direct DB access from API service for scoring — processor owns `image_score` writes
