# Pseudocode — Content Scoring: Image (CLIP)

---

## Data Structures

```python
# Redis embedding value
EmbeddingCache = {
    key: f"ref_emb:{sku_id}:image",  # str
    value: pickle.dumps(np.ndarray),  # bytes, shape [512], L2-normalized
    ttl: 2592000,                     # seconds
}

# Orchestrator query result row
ScoringRow = {
    cs_id:    UUID,   # content_scores.id — used for UPDATE
    sku_id:   UUID,   # from sku_platforms.sku_id → skus.id
    s3_key:   str,    # content_scores.collected_image_url (MinIO key)
}
```

---

## Algorithm 1: compute_clip_embedding

```
TASK compute_clip_embedding(sku_id: str, s3_key: str) → None
  max_retries=3, bind=True

  INPUT: sku_id — UUID string of SKU
         s3_key — MinIO key for reference image (e.g. "ref/{org_id}/sku/{sku_id}/image.jpg")

  STEP 1: download_image
    bytes ← minio.download(s3_key)
    IF download fails:
      IF attempt < max_retries: self.retry(countdown=2^attempt)
      ELSE: log.error("MinIO download failed"); RETURN

  STEP 2: decode_image
    pil_image ← PIL.Image.open(BytesIO(bytes)).convert("RGB")
    IF decode fails:
      log.warning("Cannot decode image for sku_id={}".format(sku_id)); RETURN

  STEP 3: encode
    embedding ← clip_model.encode_image(pil_image)
    # embedding: np.ndarray shape [512], L2-normalized

  STEP 4: cache_in_redis
    redis_key ← f"ref_emb:{sku_id}:image"
    redis.set(redis_key, pickle.dumps(embedding), ex=2592000)
    IF redis fails:
      IF attempt < max_retries: self.retry(countdown=2^attempt)
      ELSE: log.error("Redis write failed for sku_id={}".format(sku_id)); RETURN

  STEP 5: log success
    log.info("compute_clip_embedding done sku_id={}".format(sku_id))

  COMPLEXITY: O(1) — single image
  SIDE EFFECTS: Redis write
```

---

## Algorithm 2: score_image_content_all (orchestrator)

```
TASK score_image_content_all() → None
  # Celery Beat: daily 06:00 UTC

  STEP 1: query_today_unscored
    today ← date.today()
    rows ← DB.query(
      ContentScore.id,
      SKUPlatform.sku_id,
      ContentScore.collected_image_url
    ).join(SKUPlatform)
     .filter(
       ContentScore.scored_at == today,
       ContentScore.image_score IS NULL,
       ContentScore.collected_image_url IS NOT NULL,
     ).all()

    log.info("score_image_content_all: {} rows to score".format(len(rows)))

  STEP 2: dispatch_group
    IF len(rows) == 0: RETURN

    group(
      score_image_content.s(str(row.cs_id), str(row.sku_id), row.s3_key)
      FOR row IN rows
    ).delay()

    log.info("score_image_content_all: dispatched {} tasks".format(len(rows)))

  COMPLEXITY: O(N) query, O(1) dispatch per row
  NOTE: N can be 10k–100k rows; query selects only 3 columns (flat, no ORM inflation)
```

---

## Algorithm 3: score_image_content (per-row)

```
TASK score_image_content(cs_id: str, sku_id: str, s3_key: str) → None
  max_retries=3, bind=True

  INPUT: cs_id   — content_scores.id (PK for UPDATE)
         sku_id  — skus.id (for Redis key lookup)
         s3_key  — MinIO key for collected image

  STEP 1: load_reference_embedding
    redis_key ← f"ref_emb:{sku_id}:image"
    raw ← redis.get(redis_key)
    IF raw IS None:
      log.warning("No reference embedding for sku_id={} — skip".format(sku_id))
      RETURN  # no DB write — score stays NULL, re-queued tomorrow
    ref_emb ← pickle.loads(raw)  # np.ndarray [512]

  STEP 2: download_collected_image
    bytes ← minio.download(s3_key)
    IF download fails:
      IF attempt < max_retries: self.retry(countdown=2^attempt)
      ELSE: log.error("MinIO download failed cs_id={}".format(cs_id)); RETURN

  STEP 3: decode_image
    pil_image ← PIL.Image.open(BytesIO(bytes)).convert("RGB")
    IF decode fails:
      log.warning("Cannot decode collected image cs_id={}".format(cs_id))
      RETURN

  STEP 4: encode_collected
    collected_emb ← clip_model.encode_image(pil_image)  # np.ndarray [512], normalized

  STEP 5: cosine_similarity
    # Both vectors are L2-normalized → cosine_sim = dot product
    score ← float(np.dot(collected_emb, ref_emb))
    score ← max(0.0, min(1.0, score))  # clamp to [0, 1]

  STEP 6: update_db
    DB.execute(
      UPDATE content_scores
      SET image_score = round(score, 2)
      WHERE id = UUID(cs_id)
    )
    DB.commit()

  STEP 7: log
    log.info("score_image_content: done cs_id={} score={:.3f}".format(cs_id, score))

  COMPLEXITY: O(d) where d=512 (dot product)
  SIDE EFFECTS: DB UPDATE (single row by PK)
```

---

## Algorithm 4: encode_image (CLIP singleton)

```
MODULE clip_model

  _model ← None  # CLIPModel | None, module-level
  _processor ← None  # CLIPProcessor | None, module-level

  FUNCTION _load_if_needed():
    IF _model IS None:
      _processor ← CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
      _model ← CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
      _model.eval()  # inference mode — no gradient tracking
      log.info("CLIP model loaded")

  FUNCTION encode_image(pil_image: PIL.Image) → np.ndarray:
    _load_if_needed()
    inputs ← _processor(images=pil_image, return_tensors="pt")
    WITH torch.no_grad():
      features ← _model.get_image_features(**inputs)
    vec ← features[0].numpy()  # shape [512]
    RETURN vec / ||vec||_2      # L2 normalize

  NOTE: _load_if_needed() is NOT thread-safe on first call.
        Celery workers are single-threaded per process — safe.
        If gevent pool is used, wrap with threading.Lock.
```

---

## Error Handling Matrix

| Error | Task | Action |
|-------|------|--------|
| MinIO download fails (transient) | compute_clip_embedding | retry (max 3, backoff) |
| MinIO download fails (permanent) | compute_clip_embedding | log.error, skip |
| Image decode fails | compute_clip_embedding | log.warning, skip (bad file) |
| Redis write fails | compute_clip_embedding | retry (max 3, backoff) |
| DB query fails | score_image_content_all | exception propagates (Beat retries next day) |
| Reference embedding missing | score_image_content | log.warning, skip (no DB write) |
| MinIO download fails (transient) | score_image_content | retry (max 3, backoff) |
| Image decode fails | score_image_content | log.warning, skip |
| DB UPDATE fails | score_image_content | retry (max 3, backoff) |
| CLIP model OOM | score_image_content | log.error, task fails — worker restarts |

---

## API Contract (existing — no new endpoints)

The API contract is defined by `reference_service._dispatch_clip_task`:

```python
# Already implemented in services/api/app/catalog/reference_service.py
# Processor must register this task name:
@celery_app.task(name="processor.compute_clip_embedding", bind=True, max_retries=3)
def compute_clip_embedding(self, sku_id: str, s3_key: str) -> None: ...
```

The task name `"processor.compute_clip_embedding"` must match exactly what the API dispatches.

Check `reference_service.py` line: `from app.tasks.embedding_tasks import compute_clip_embedding`
→ The API imports from `app.tasks.embedding_tasks` — this module must exist in processor OR the API must use `.delay()` with the string name. Verify during implementation and align.
