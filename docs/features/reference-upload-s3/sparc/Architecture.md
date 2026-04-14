# Architecture — Reference Upload (S3)

**SPARC Phase 5: Architecture** | Feature: reference-upload-s3

---

## 1. Component Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  API SERVICE (FastAPI)                                           │
│                                                                  │
│  POST /skus/{id}/reference/image ──→ ReferenceService           │
│  PATCH /skus/{id}/reference/text  ──→ ReferenceService          │
│  GET  /skus/{id}/reference/image-url ──→ ReferenceService       │
│                       │                                          │
│        ┌──────────────┴──────────────┐                          │
│        ▼                             ▼                           │
│  MinioClient (aioboto3)       SKURepository (update ref fields)  │
│  └─ upload_object()           └─ update(sku, reference_image_url)│
│  └─ delete_object()           └─ update(sku, reference_*)        │
│  └─ presigned_url()                                              │
│        │                                                          │
│        ▼                                                          │
│  Celery .delay()                                                  │
│  └─ compute_clip_embedding.delay(sku_id, s3_key)                 │
│  └─ compute_text_embedding.delay(sku_id, "desc"|"comp", text)   │
└─────────────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
   MinIO (S3)                      Redis
   cat-references/                 ref_emb:{sku_id}:image
   org/{org_id}/sku/{sku_id}/      ref_emb:{sku_id}:desc
   reference.jpg                   ref_emb:{sku_id}:comp

         │
         ▼
   PROCESSOR SERVICE (Celery worker)
   └─ compute_clip_embedding()
      1. Download image from S3
      2. Load CLIP model (cached)
      3. Encode → embedding vector
      4. Pickle → Redis with 30d TTL
   └─ compute_text_embedding()
      1. Load multilingual-e5 (cached)
      2. Encode text → embedding
      3. Pickle → Redis with 30d TTL
```

---

## 2. New Files

```
services/api/app/catalog/
├── reference_service.py      # business logic for S3 + embedding trigger
├── reference_router.py       # FastAPI routes (mounted under /skus)
└── reference_schemas.py      # Pydantic request/response schemas

services/api/app/core/
└── minio_client.py           # async MinIO wrapper (aioboto3)

services/processor/tasks/
└── embedding_tasks.py        # Celery tasks: compute_clip_embedding, compute_text_embedding
```

---

## 3. MinIO Client Design

```python
# services/api/app/core/minio_client.py

class MinioClient:
    """Thin async wrapper over aioboto3 S3 client."""

    BUCKET = "cat-references"
    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
    MAGIC_BYTES = {
        b"\xff\xd8\xff": "image/jpeg",
        b"\x89PNG":      "image/png",
        b"RIFF":         "image/webp",  # WebP starts with RIFF
    }

    async def upload_reference_image(self, org_id, sku_id, content, ext) -> str:
        """Upload bytes to S3, return S3 key."""
        key = f"org/{org_id}/sku/{sku_id}/reference{ext}"
        await self._s3.put_object(Bucket=self.BUCKET, Key=key, Body=content)
        return key

    async def delete_object(self, key: str) -> None:
        await self._s3.delete_object(Bucket=self.BUCKET, Key=key)

    async def generate_presigned_url(self, key: str, expires: int = 3600) -> str:
        return await self._s3.generate_presigned_url(
            "get_object", Params={"Bucket": self.BUCKET, "Key": key}, ExpiresIn=expires
        )
```

---

## 4. Celery Tasks

```python
# services/processor/tasks/embedding_tasks.py

@celery_app.task(bind=True, max_retries=3)
def compute_clip_embedding(self, sku_id: str, s3_key: str):
    """
    Download reference image from S3, compute CLIP embedding, store in Redis.
    """
    try:
        image_bytes = download_from_s3(s3_key)
        embedding = clip_model.encode_image(image_bytes)  # numpy float32 array
        redis_client.setex(
            f"ref_emb:{sku_id}:image",
            2592000,  # 30 days
            pickle.dumps(embedding)
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


@celery_app.task(bind=True, max_retries=3)
def compute_text_embedding(self, sku_id: str, field: str, text: str):
    """
    Compute multilingual-e5 embedding for desc or comp, store in Redis.
    field: "desc" | "comp"
    """
    try:
        embedding = e5_model.encode(text)
        redis_client.setex(
            f"ref_emb:{sku_id}:{field}",
            2592000,
            pickle.dumps(embedding)
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
```

---

## 5. Redis Key Convention

| Key | Value | TTL |
|-----|-------|-----|
| `ref_emb:{sku_id}:image` | `pickle.dumps(np.ndarray shape=[512])` | 30 days |
| `ref_emb:{sku_id}:desc` | `pickle.dumps(np.ndarray shape=[768])` | 30 days |
| `ref_emb:{sku_id}:comp` | `pickle.dumps(np.ndarray shape=[768])` | 30 days |

CLIP output: 512-dim for ViT-B/32. multilingual-e5: 768-dim.

---

## 6. Security

- S3 bucket `cat-references` — private, no public access policy
- Images served only via presigned URLs (1 hour TTL)
- Magic bytes validation prevents disguised executables
- org_id verified before any S3 write (SKU must belong to caller's org)
- MinIO credentials never logged; sourced from env only

---

## 7. No DB Migration Required

`reference_image_url`, `reference_description`, `reference_composition` columns already exist in `skus` table (added in migration 0002). Only application logic is new.
