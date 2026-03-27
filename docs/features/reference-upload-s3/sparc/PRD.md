# PRD — Reference Upload (S3)

**Feature:** Reference Upload (S3)
**Priority:** P0 | **Sprint:** 1 #3 | **Story Points:** 5
**Status:** Planning

---

## 1. Problem Statement

Content scoring (CLIP image similarity + multilingual-e5 text similarity) requires reference materials per SKU as the "golden standard" to compare against collected marketplace content. Without uploaded reference images and texts, the scoring pipeline has no baseline — all content scores will be zero or undefined.

Currently:
- `skus` table has `reference_image_url`, `reference_description`, `reference_composition` columns but they are always NULL.
- No endpoint exists to upload a reference image to MinIO/S3.
- No endpoint exists to set reference text (description + composition).
- No mechanism exists to pre-compute and cache CLIP/e5 embeddings at upload time.

**Impact:** The entire content scoring feature (Sprint 3) is blocked without reference materials.

---

## 2. Target Users

| Persona | Role | Need |
|---------|------|------|
| Brand Manager | Configures catalog | Upload reference photo and text per SKU |
| Trade Marketing | Validates scoring | Ensure reference image matches product packaging |
| System Admin | Manages org | Bulk-set reference texts via API during onboarding |

---

## 3. Core Requirements

### Must Have (Sprint 1 #3)
- Upload a reference image (JPEG/PNG/WebP, max 10 MB) for a SKU → stored in MinIO with private access
- Set reference description + composition text per SKU (via PATCH)
- Trigger async CLIP embedding computation after image upload (Celery task)
- Trigger async multilingual-e5 embedding computation after text upload (Celery task)
- Store computed embeddings in Redis with key `ref_emb:{sku_id}:image`, `:desc`, `:comp`
- Return presigned URL (1 hour TTL) for viewing uploaded image

### Should Have
- Overwrite existing reference (new upload replaces old file in S3)
- Invalidate stale embedding from Redis when reference is updated
- Validate image magic bytes (not just MIME type/extension)

### Won't Have (this sprint)
- Bulk reference image upload (per-SKU only)
- Video references
- Reference text import from CSV

---

## 4. Success Metrics

| Metric | Target |
|--------|--------|
| Upload latency (p95) | < 3 s for 5 MB image |
| Embedding computed within | 60 s after upload |
| Cache hit rate for embeddings | > 95% during nightly scoring runs |
| S3 storage: no public URLs | 100% compliance |

---

## 5. Constraints

- MinIO credentials from env: `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`
- Bucket: `cat-references` — private, no public access
- Embedding computation is async (Celery) — endpoint returns 202 on upload
- Redis TTL for embeddings: 30 days (refreshed on re-upload)
- Multi-tenant: SKU org_id verified before any write
- RBAC: admin + manager can upload; viewer read-only (presigned URL only)
