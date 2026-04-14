# Refinement — Reference Upload (S3)

**SPARC Phase 6: Refinement** | Feature: reference-upload-s3

---

## 1. Open Questions & Decisions

### Q1: Sync vs Async embedding computation
**Decision:** Async (Celery task). Image upload returns 202 immediately.
**Rationale:** CLIP encoding on CPU takes 2-5 seconds. Holding the HTTP connection open would degrade UX and risk nginx timeouts for large files.
**Risk:** Embedding may not be ready immediately after upload. Content scoring pipeline checks Redis before computing; if cache miss, it computes on-the-fly (slower path).

### Q2: What if MinIO is temporarily unavailable?
**Decision:** Return 503 `S3_UPLOAD_FAILED` immediately. No retry at API layer.
**Rationale:** Image data must not be lost silently. Client should retry explicitly. MinIO unavailability is an ops incident.

### Q3: Overwrite behaviour — keep old file or delete?
**Decision:** Delete old S3 object before uploading new one.
**Rationale:** Prevents unbounded storage growth. Old embeddings are stale anyway.

### Q4: Multiple images per SKU?
**Decision:** Single reference image per SKU (one S3 key, overwrite pattern).
**Rationale:** CLIP scoring uses one canonical image. Multi-angle is a future feature.

### Q5: Embedding dimension consistency
- CLIP ViT-B/32: 512 dimensions
- multilingual-e5-large: 1024 dimensions (but we use `intfloat/multilingual-e5-base`: 768)
**Decision:** Use `intfloat/multilingual-e5-base` (768-dim) for description and composition.

---

## 2. Edge Cases

| Case | Handling |
|------|---------|
| Upload fails mid-stream | `aioboto3` raises exception → service catches → 503, old file unchanged |
| Redis unavailable during delete | Log warning, continue (stale embedding will be overwritten by next task) |
| Celery task fails permanently (3 retries) | Embedding stays stale/missing. Content scorer falls back to live computation. |
| SKU soft-deleted (is_active=False) | Upload still allowed (manager may want to prep before re-activating) |
| Same file uploaded twice | Normal overwrite; new Celery task enqueued (idempotent from caller's perspective) |
| WebP file disguised as JPEG | Magic byte check catches this: RIFF ≠ FF D8 FF |

---

## 3. Performance Considerations

- **aioboto3** for async S3 operations — avoid blocking the FastAPI event loop
- **Streaming upload:** read file content once, pass bytes directly — do not write to disk
- **Redis delete + DB update** happen before Celery task dispatch — ensures consistency even if Celery is temporarily down
- **CLIP model** is cached in processor memory — not reloaded per task. `@lru_cache` on model factory.

---

## 4. Testing Strategy

| Test Type | What to Test |
|-----------|-------------|
| Unit | `is_valid_magic()`, `ReferenceService` methods with mocked MinIO + Celery |
| E2E | Image upload → 202, presigned URL returned; cross-org 404; viewer 403 |
| E2E | Text upload → 202, DB fields updated, Celery task called |
| E2E | Overwrite: second upload deletes first embedding from Redis |
| Integration | Celery task: compute_clip_embedding writes correct key to Redis |

**MinIO in tests:** Use `unittest.mock.AsyncMock` for `MinioClient` methods. Do not connect to real MinIO in E2E tests.

---

## 5. Dependency on Other Features

| Dependency | Type | Notes |
|-----------|------|-------|
| SKU CRUD (sku-crud) | Hard | SKU must exist before upload |
| Celery + Redis infrastructure | Hard | Already configured in docker-compose |
| Processor service (ML models) | Soft | Tasks will fail gracefully if processor is down |
| Content Scoring (Sprint 3) | Consumer | This feature is a prerequisite |
