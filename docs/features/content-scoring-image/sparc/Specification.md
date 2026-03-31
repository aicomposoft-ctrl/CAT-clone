# Specification — Content Scoring: Image (CLIP)

> **Revision 2** — validation fixes applied: US-4 merged into US-3 ACs, security ACs added, US-2 testability improved.

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
  Then a Celery task compute_clip_embedding is dispatched with (sku_id, s3_key)
  And within 60 seconds the embedding is stored in Redis at ref_emb:{sku_id}:image
  And the embedding has TTL = 30 days (2592000 seconds)
  And the stored value is pickle.dumps(np.ndarray) with shape (512,) and L2 norm ≈ 1.0
  And if Redis is unavailable, the task retries up to 3 times with exponential backoff
       (countdown = 2^attempt seconds)
  And if MinIO download fails transiently, the task retries (max 3) then logs error and stops
```

### US-2: Daily Image Scoring
```
As a brand manager,
I want image scores to be calculated every morning automatically,
So that I see fresh data by the time I start work.

Acceptance Criteria:
  Given collector has finished scraping (last scraper Lenta ends at 05:00 UTC + ~30 min)
  When the Celery Beat schedule triggers score_image_content_all at 06:00 UTC
  Then the orchestrator queries content_scores WHERE:
       scored_at = today() AND image_score IS NULL AND collected_image_url IS NOT NULL
  And dispatches one score_image_content task per matching row via Celery group
  And upon task group completion, ≥ 99% of matching rows have image_score set
       (verifiable by: SELECT COUNT(*) FROM content_scores WHERE scored_at=today AND
        image_score IS NULL AND collected_image_url IS NOT NULL → expected 0 or near 0)
  And the full batch of 1000 SKUs completes within 10 minutes on a 4-core CPU host
       with CELERY_WORKER_CONCURRENCY=2 (verified in load test with fixture data)
  And if 0 rows match, no group is dispatched and a log.info records "0 rows to score"
```

### US-3: Per-row Image Scoring (with Isolation Guarantee)
```
As the platform,
I want each image score to be computed independently and scoped to a single organization,
So that failures in one SKU do not block others and cross-org data leakage is impossible.

Acceptance Criteria — Scoring:
  Given a content_scores row with collected_image_url (MinIO S3 key) and associated sku_id
  When score_image_content(cs_id, sku_id, s3_key) task runs
  Then it downloads the collected image from MinIO (max 30 MB; abort + warn if exceeded)
  And image bytes are decoded via PIL; MIME type verified against [jpeg, png, webp] magic bytes
  And the reference embedding is loaded from Redis key ref_emb:{sku_id}:image
  And cosine similarity is computed as dot(collected_emb, ref_emb) (both L2-normalized)
  And score is clamped to [0.0, 1.0] and rounded to 2 decimal places
  And content_scores.image_score is SET to the score WHERE id = cs_id (single-row UPDATE)
  And if reference embedding missing in Redis: log warning, skip, no DB write (score stays NULL)
  And if MinIO download fails transiently: retry up to 3 times (countdown=2^attempt), then skip
  And if image decode fails (corrupted/unsupported format): log warning, skip, no DB write
  And if image > MAX_IMAGE_BYTES (default 30 MB): log warning, skip immediately (no retry)
  And if cs_id not found in DB (deleted race): log warning, no crash (UPDATE 0 rows is OK)

Acceptance Criteria — Isolation:
  Given org A has SKU-A and org B has SKU-B, each with content_scores for today
  When score_image_content_all runs
  Then each task independently resolves its own sku_id → ref_emb:{sku_id}:image
  And org A's task cannot access ref_emb:{sku_b_id}:image
       (sku_id UUID uniqueness guarantees namespace isolation — no policy enforcement needed)
  And DB UPDATE is scoped to content_scores.id (PK): no other org's row can be affected
  And MinIO key includes org_id in path (org/{org_id}/sku/{sku_id}/platform/main.jpg)
       preventing cross-org reads even under misconfigured bucket policy
  And a cross-tenant isolation test MUST be present:
       given 2 orgs × 1 SKU each, verify no embedding key collision and no DB cross-write

Acceptance Criteria — Security:
  AC-SEC-1: Image size guard
    Given score_image_content downloads image from MinIO
    When bytes received exceed MAX_IMAGE_BYTES (env var, default 30_000_000)
    Then download is aborted immediately
    And task logs warning "Image exceeds size limit: {size} bytes for cs_id={cs_id}"
    And image_score is NOT written

  AC-SEC-2: Pickle deserialization safety
    Given score_image_content loads ref_emb:{sku_id}:image from Redis
    When pickle.loads(raw) is called
    Then only numpy.ndarray objects of shape (512,) are accepted
    And if deserialized object is not ndarray: log error, skip task (no DB write)
    And pickle.UnpicklingError is caught explicitly and treated as missing embedding
    Note: Redis is internal infra only, not internet-exposed — primary attack vector is
          compromised Redis instance, mitigated by REDIS_PASSWORD and network policy

  AC-SEC-3: Image format validation
    Given image bytes are loaded via PIL.Image.open()
    When format is identified
    Then only JPEG, PNG, WEBP formats are processed (verified by PIL format attribute)
    And decode failures MUST NOT expose MinIO keys or S3 paths in log messages
    And PIL.Image.open result is .convert("RGB") before passing to CLIP

  AC-SEC-4: Secret management
    Given processor service starts
    When connections to Redis, MinIO, PostgreSQL are initialised
    Then all credentials load from environment variables: REDIS_URL (with password),
         MINIO_ACCESS_KEY, MINIO_SECRET_KEY, POSTGRES_URL
    And if any required credential is absent, startup fails with sys.exit(1)
    And credentials MUST NEVER appear in task log output or error messages

  AC-SEC-5: L2 norm guard
    Given encode_image computes CLIP embedding
    When numpy.linalg.norm(vec) < 1e-8 (degenerate zero vector)
    Then raise ValueError("zero-norm embedding") — task logs error and skips
    And no division-by-zero occurs in cosine similarity computation
```

---

## Non-Functional Requirements

| Category | Requirement |
|----------|-------------|
| Latency | 1000 SKU scored in ≤ 10 min on 4-core CPU, CONCURRENCY=2 |
| Concurrency | Celery group — parallel per-row tasks |
| Model loading | CLIP loaded once per worker process (singleton) |
| Redis TTL | 30 days (2592000 s) |
| Retry | max_retries=3, countdown=2^attempt |
| Failure mode | Per-row failure → skip + log warning. Orchestrator always completes. |
| Memory | ~340 MB RAM per worker (CLIP ViT-B/32 CPU weights) |
| Image size limit | MAX_IMAGE_BYTES env var, default 30_000_000 (30 MB) |
| Docker base | `python:3.11-slim` + torch CPU (NOT playwright image) |

---

## Data Contracts

### Redis Keys
```
ref_emb:{sku_id}:image  →  bytes = pickle.dumps(np.ndarray, protocol=5)
                           shape: (512,), dtype: float32, L2-normalized
                           TTL: 2592000 s (30 days)
```

### ContentScore fields used
```
content_scores.id                  — PK (target of UPDATE, scope of task)
content_scores.sku_platform_id     — join to sku_platforms → sku_id
content_scores.scored_at           — filter: = today
content_scores.collected_image_url — MinIO S3 key for collected image (input)
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
- `CELERYD_CONCURRENCY=2` — processor worker (2 processes × ~340 MB = ~680 MB total)
- HuggingFace model pre-downloaded to mounted volume `/root/.cache/huggingface/` in Docker
- MinIO client pattern reused from collector's `app/core/minio_client.py`
- Processor owns `image_score` writes — API service does not write to this field
- `pickle.protocol=5` for forward compatibility across Python 3.11+
