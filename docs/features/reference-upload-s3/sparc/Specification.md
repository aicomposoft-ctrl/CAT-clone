# Specification — Reference Upload (S3)

**SPARC Phase 3: Specification** | Feature: reference-upload-s3

---

## 1. User Stories

### US-R01: Reference Image Upload

```gherkin
Feature: Reference Upload

Scenario: Manager uploads reference image for a SKU
  Given I am authenticated as a manager
  And SKU with id X exists in my org
  When I POST /api/v1/skus/{X}/reference/image with a valid JPEG file (< 10 MB)
  Then the response is 202
  And response contains "presigned_url" (expires in 3600 seconds)
  And SKU reference_image_url is updated to the S3 key
  And a Celery task is enqueued to compute CLIP embedding

Scenario: Viewer cannot upload reference image
  Given I am authenticated as a viewer
  When I POST /api/v1/skus/{X}/reference/image
  Then the response is 403
  And detail is "INSUFFICIENT_PERMISSIONS"

Scenario: File exceeds 10 MB limit
  Given I upload a 12 MB JPEG
  When I POST /api/v1/skus/{X}/reference/image
  Then the response is 422
  And detail is "FILE_TOO_LARGE"

Scenario: Non-image file is rejected
  Given I upload a .pdf file
  When I POST /api/v1/skus/{X}/reference/image
  Then the response is 422
  And detail is "INVALID_IMAGE_TYPE"

Scenario: Manager uploads reference for another org's SKU
  Given SKU X belongs to org_B
  When org_A manager POSTs /api/v1/skus/{X}/reference/image
  Then the response is 404

Scenario: Second upload overwrites the first
  Given SKU X already has reference_image_url set
  When I POST /api/v1/skus/{X}/reference/image with a new image
  Then the old S3 object is deleted
  And reference_image_url is updated to the new key
  And CLIP embedding in Redis is invalidated and re-enqueued
```

### US-R02: Reference Text Upload

```gherkin
Scenario: Manager sets reference description and composition
  Given I am authenticated as a manager
  And SKU with id X exists in my org
  When I PATCH /api/v1/skus/{X}/reference/text with:
    | reference_description | "Индейка Индилайт бедро охл. 700г..." |
    | reference_composition | "Индейка 100%"                        |
  Then the response is 202
  And SKU reference_description and reference_composition are updated
  And Celery tasks are enqueued for desc and comp embeddings

Scenario: Viewer cannot set reference text
  Given I am authenticated as a viewer
  When I PATCH /api/v1/skus/{X}/reference/text
  Then the response is 403

Scenario: Description exceeds 2000 characters
  When I send reference_description with 2001 characters
  Then the response is 422

Scenario: Text update invalidates stale embeddings
  Given ref_emb:{X}:desc and ref_emb:{X}:comp exist in Redis
  When I PATCH /api/v1/skus/{X}/reference/text with new text
  Then Redis keys ref_emb:{X}:desc and ref_emb:{X}:comp are deleted
  And new embedding tasks are enqueued
```

### US-R03: Presigned URL for Viewing

```gherkin
Scenario: Manager gets presigned URL for reference image
  Given SKU X has reference_image_url set
  When I GET /api/v1/skus/{X}/reference/image-url
  Then the response is 200
  And response contains "presigned_url" (valid for 3600 seconds)
  And the URL is not publicly accessible without the signature

Scenario: SKU has no reference image
  Given SKU X has reference_image_url = null
  When I GET /api/v1/skus/{X}/reference/image-url
  Then the response is 404
  And detail is "REFERENCE_IMAGE_NOT_FOUND"
```

---

## 2. API Contracts

```
POST   /api/v1/skus/{sku_id}/reference/image      upload image → 202 + presigned_url
PATCH  /api/v1/skus/{sku_id}/reference/text       set description + composition → 202
GET    /api/v1/skus/{sku_id}/reference/image-url  get presigned URL → 200 + presigned_url
```

### RBAC
| Endpoint | admin | manager | viewer |
|----------|-------|---------|--------|
| POST image | ✅ | ✅ | ❌ |
| PATCH text | ✅ | ✅ | ❌ |
| GET presigned URL | ✅ | ✅ | ✅ |

### Request: POST /api/v1/skus/{sku_id}/reference/image
```
Content-Type: multipart/form-data
Body: file (UploadFile)
```

### Response 202
```json
{
  "sku_id": "uuid",
  "presigned_url": "https://minio:9000/cat-references/org/{org_id}/sku/{sku_id}/reference.jpg?X-Amz-...",
  "expires_in": 3600,
  "embedding_task_id": "celery-task-uuid"
}
```

### Request: PATCH /api/v1/skus/{sku_id}/reference/text
```json
{
  "reference_description": "...",
  "reference_composition": "..."
}
```

### Response 202
```json
{
  "sku_id": "uuid",
  "embedding_task_ids": {
    "description": "celery-task-uuid",
    "composition": "celery-task-uuid"
  }
}
```

---

## 3. S3 Key Schema

```
cat-references/
└── org/{org_id}/
    └── sku/{sku_id}/
        └── reference.{ext}    ← single reference image per SKU
```

Key stored in `skus.reference_image_url` as the full S3 path (not a presigned URL).
Presigned URLs are generated on demand with 1-hour expiry.

---

## 4. Redis Embedding Key Schema

```
ref_emb:{sku_id}:image   ← CLIP embedding (numpy array, serialised as bytes)
ref_emb:{sku_id}:desc    ← multilingual-e5 embedding
ref_emb:{sku_id}:comp    ← multilingual-e5 embedding
```

TTL: 30 days (2592000 seconds). Refreshed on every successful embedding computation.

---

## 5. Validation Rules

| Field | Rule |
|-------|------|
| Image file size | ≤ 10 MB |
| Image MIME | image/jpeg, image/png, image/webp |
| Image magic bytes | Must match MIME (FF D8 FF for JPEG, 89 50 4E 47 for PNG, 52 49 46 46 for WebP) |
| reference_description | max 2000 chars |
| reference_composition | max 1000 chars |

---

## 6. Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `FILE_TOO_LARGE` | 422 | Image > 10 MB |
| `INVALID_IMAGE_TYPE` | 422 | MIME not image/jpeg, png, webp |
| `INVALID_IMAGE_MAGIC` | 422 | Magic bytes don't match declared MIME |
| `SKU_NOT_FOUND` | 404 | SKU doesn't exist or belongs to another org |
| `REFERENCE_IMAGE_NOT_FOUND` | 404 | No reference_image_url set |
| `S3_UPLOAD_FAILED` | 503 | MinIO unavailable |
