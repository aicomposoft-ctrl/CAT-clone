# Refinement — Content Scoring: Image (CLIP)

---

## Edge Cases Matrix

| Scenario | Input | Expected Behaviour |
|----------|-------|--------------------|
| No reference image uploaded | `ref_emb:{sku_id}:image` absent in Redis | skip row, log warning, image_score stays NULL |
| Reference embedding expired (>30d) | Redis key TTL expired | same as missing — re-upload triggers recompute |
| Collected image corrupted (bad JPEG) | PIL.Image.open raises | log warning, skip, no DB write |
| Collected image is 1×1 pixel (placeholder) | Valid JPEG, valid CLIP input | score computed normally — low cosine sim expected |
| Score = NaN (zero-norm embedding) | `||vec|| = 0` | L2 norm guard: if norm < 1e-8, skip and log error |
| content_scores row deleted between dispatch and execution | UPDATE WHERE id=cs_id → 0 rows | log warning, no error (idempotent) |
| Duplicate orchestrator run (clock drift) | score_image_content_all runs twice | second run: 0 rows (image_score already filled) — no-op |
| MinIO key path changed (refactor) | s3_key stored in DB is stale | download 404 → retry 3× → skip. Alert if >5% miss rate. |
| CLIP model download blocked (no internet) | from_pretrained fails | worker crashes at startup — volume mount with pre-downloaded weights required |
| Celery worker OOM (large image) | PIL decode of 50 MB TIFF | PIL.Image.open size limit: raise if > 30 MB (configurable via MAX_IMAGE_BYTES env) |
| Redis connection lost during scoring | redis.get raises | log warning, skip (treat as missing embedding) |
| All 10k rows dispatched, some workers die | Celery group partial completion | surviving tasks complete; dead tasks re-queued by Celery broker visibility timeout |

---

## Test Scenarios

### Happy Path

```gherkin
Scenario: Reference embedding cached after upload
  Given a SKU with id=SKU-1 belonging to org=ORG-A
  And a reference image at S3 key "ref/ORG-A/SKU-1/image.jpg"
  When compute_clip_embedding("SKU-1", "ref/ORG-A/SKU-1/image.jpg") executes
  Then Redis key "ref_emb:SKU-1:image" is set
  And the value is a pickled numpy array of shape (512,)
  And TTL is 30 days

Scenario: Daily scoring writes image_score
  Given content_scores row CS-1 with scored_at=today, image_score=NULL
  And collected_image_url = "org/ORG-A/sku/SKU-1/wb/main.jpg"
  And Redis has ref_emb:SKU-1:image with L2-normalized embedding
  When score_image_content("CS-1", "SKU-1", "org/ORG-A/...") executes
  Then content_scores.image_score is set to a value in [0.0, 1.0]
  And the value is rounded to 2 decimal places

Scenario: Orchestrator dispatches correct count
  Given 5 content_scores rows for today with image_score=NULL
  And 3 rows already have image_score set
  When score_image_content_all runs
  Then exactly 5 score_image_content tasks are dispatched
```

### Error Paths

```gherkin
Scenario: Missing reference embedding — skip gracefully
  Given CS-1 has collected_image_url set
  And Redis has NO key "ref_emb:SKU-1:image"
  When score_image_content runs
  Then image_score remains NULL
  And a WARNING is logged
  And no retry is triggered

Scenario: MinIO transient failure — retry
  Given MinIO raises ConnectionError on first call
  When score_image_content runs
  Then self.retry() is called with countdown=1
  And on second attempt MinIO succeeds
  And image_score is written

Scenario: Corrupted image — skip without crash
  Given MinIO returns bytes that are not a valid image
  When score_image_content runs
  Then PIL.Image.open raises
  And image_score remains NULL
  And WARNING is logged

Scenario: Oversized image — rejected before decode
  Given MinIO returns 35 MB file (> MAX_IMAGE_BYTES=30 MB)
  When score_image_content runs
  Then download is aborted
  And WARNING is logged
  And no retry

Scenario: compute_clip_embedding — MinIO retry exhausted
  Given MinIO raises ConnectionError on all 3 attempts
  When compute_clip_embedding executes
  Then after 3 retries the task logs error and returns
  And Redis is NOT written
  And ref_emb:{sku_id}:image remains absent or stale
```

### Multi-Tenant

```gherkin
Scenario: Cross-tenant embedding isolation
  Given org A has SKU-A and org B has SKU-B
  And Redis has ref_emb:SKU-A:image and ref_emb:SKU-B:image
  When score_image_content runs for SKU-A's content_score
  Then it reads ref_emb:SKU-A:image (not SKU-B)
  And the DB UPDATE targets cs_id belonging to SKU-A only

Scenario: Orchestrator fetches all orgs but tasks stay isolated
  Given 3 orgs each with 100 content_scores for today
  When score_image_content_all runs
  Then 300 tasks are dispatched
  And each task independently resolves its own sku_id → Redis key
  And no task can access another org's embedding (UUID namespace)
```

---

## Test List (unit, numbered for review tracking)

| # | Test | Task |
|---|------|------|
| 1 | Happy path: embedding computed and stored in Redis | compute_clip_embedding |
| 2 | Redis key format: `ref_emb:{sku_id}:image` | compute_clip_embedding |
| 3 | Redis TTL = 2592000 s | compute_clip_embedding |
| 4 | MinIO transient failure → retry | compute_clip_embedding |
| 5 | MinIO permanent failure (max retries) → log error, no Redis write | compute_clip_embedding |
| 6 | Image decode failure → log warning, no Redis write | compute_clip_embedding |
| 7 | Embedding is L2-normalized (norm ≈ 1.0) | compute_clip_embedding |
| 8 | Orchestrator dispatches N tasks for N unscored rows | score_image_content_all |
| 9 | Orchestrator skips rows with image_score already set | score_image_content_all |
| 10 | Orchestrator skips rows with collected_image_url=NULL | score_image_content_all |
| 11 | Orchestrator: 0 rows → no group dispatched | score_image_content_all |
| 12 | Happy path: image_score written to DB | score_image_content |
| 13 | Score clamped to [0.0, 1.0] | score_image_content |
| 14 | Score rounded to 2 decimal places | score_image_content |
| 15 | Missing reference embedding → skip, log warning | score_image_content |
| 16 | MinIO transient failure → retry | score_image_content |
| 17 | MinIO permanent failure → log error, no DB write | score_image_content |
| 18 | Corrupted image bytes → skip, log warning | score_image_content |
| 19 | Oversized image (> MAX_IMAGE_BYTES) → skip, log warning | score_image_content |
| 20 | Stale cs_id (row deleted) → UPDATE 0 rows, log warning, no crash | score_image_content |
| 21 | Cross-tenant: task reads correct sku_id's embedding | score_image_content |
| 22 | encode_image returns normalized vector (norm ≈ 1.0) | clip_model |
| 23 | CLIP model loaded only once per process (singleton) | clip_model |
| 24 | cosine_sim of identical images ≈ 1.0 | score_image_content |
| 25 | cosine_sim of unrelated images < 0.5 | score_image_content |
| 26 | Duplicate orchestrator run (clock drift) → 0 tasks dispatched (idempotent) | score_image_content_all |
| 27 | Redis connection lost during ref_emb GET → skip + warning, no DB write | score_image_content |
| 28 | Zero-norm embedding (norm < 1e-8) → ValueError logged, task skips | clip_model / score_image_content |
| 29 | Expired Redis TTL → key absent, treated same as missing (skip + warning) | score_image_content |
| 30 | 1×1 pixel placeholder image → valid CLIP input, low cosine sim score computed | score_image_content |
| 31 | CLIP singleton: second task invocation does NOT reload model (call count = 1) | clip_model |
| 32 | Embedding shape validated before Redis store: assert ndarray.shape == (512,) | compute_clip_embedding |
| 33 | Pickle deserialization of wrong type (e.g. dict) → log error, skip task | score_image_content |

---

## Performance Considerations

### Model Loading
- Load CLIP once per Celery worker process at first task invocation
- Do NOT reload per task — 340 MB download + parse takes ~5 s
- `CELERY_WORKER_CONCURRENCY=2` → 2 processes × 340 MB = 680 MB total RAM

### Batch Sizing
- Current: 1 image per task (simplest, most fault-tolerant)
- Future optimisation (>10k SKU/day): batch tasks of 32 images using CLIP batch inference (~20× throughput gain)
- Tracking: follow-up ticket after Sprint 3

### MinIO Download
- Use streaming download with size limit before loading into RAM
- Max file size: `MAX_IMAGE_BYTES = int(os.environ.get("MAX_IMAGE_BYTES", 30_000_000))` (30 MB default)

### DB UPDATE
- Single-row UPDATE by PK — no index needed, no locks
- Session per task (same `get_db_session()` context manager pattern as collector)

---

## Security Notes

- MinIO key comes from `content_scores.collected_image_url` — stored by trusted collector service, not user input. No SSRF risk (not a URL, it's an S3 key).
- Redis pickle: embedding value is stored by processor itself — no untrusted pickle deserialization from external source.
- No user-supplied data enters the CLIP pipeline.
- `MAX_IMAGE_BYTES` prevents OOM from unexpectedly large files.
