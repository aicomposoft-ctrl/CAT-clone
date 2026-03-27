# Pseudocode — Reference Upload (S3)

**SPARC Phase 4: Pseudocode** | Feature: reference-upload-s3

---

## 1. Data Structures

```
ReferenceImageUploadResponse {
  sku_id: UUID
  presigned_url: str
  expires_in: int  # seconds
  embedding_task_id: str
}

ReferenceTextRequest {
  reference_description: str | None  (max 2000 chars)
  reference_composition: str | None  (max 1000 chars)
}

ReferenceTextUploadResponse {
  sku_id: UUID
  embedding_task_ids: {
    description: str | None
    composition: str | None
  }
}

PresignedUrlResponse {
  sku_id: UUID
  presigned_url: str
  expires_in: int
}
```

---

## 2. Algorithms

### Algorithm: upload_reference_image

```
INPUT: db, minio, org_id: UUID, sku_id: UUID, file: UploadFile
OUTPUT: ReferenceImageUploadResponse

1. sku = await SKURepository.get_by_id_and_org(db, sku_id, org_id)
   IF sku is None:
     RAISE LookupError("SKU_NOT_FOUND")

2. content = await file.read()
   IF len(content) > 10_485_760:  # 10 MB
     RAISE ValueError("FILE_TOO_LARGE")

3. ext = Path(file.filename).suffix.lower()
   IF ext not in {".jpg", ".jpeg", ".png", ".webp"}:
     RAISE ValueError("INVALID_IMAGE_TYPE")

4. magic = content[:4]
   IF NOT is_valid_magic(magic, ext):
     RAISE ValueError("INVALID_IMAGE_MAGIC")

5. IF sku.reference_image_url is not None:
     await minio.delete_object(sku.reference_image_url)
     redis.delete(f"ref_emb:{sku_id}:image")

6. s3_key = await minio.upload_reference_image(org_id, sku_id, content, ext)
   await SKURepository.update(db, sku, reference_image_url=s3_key)

7. task = compute_clip_embedding.delay(str(sku_id), s3_key)

8. presigned_url = await minio.generate_presigned_url(s3_key, expires=3600)

9. RETURN ReferenceImageUploadResponse(
     sku_id=sku_id,
     presigned_url=presigned_url,
     expires_in=3600,
     embedding_task_id=task.id
   )


HELPER: is_valid_magic(magic: bytes, ext: str) → bool
  IF ext in {".jpg", ".jpeg"}:  RETURN magic[:3] == b"\xff\xd8\xff"
  IF ext == ".png":              RETURN magic[:4] == b"\x89PNG"
  IF ext == ".webp":             RETURN magic[:4] == b"RIFF"
  RETURN False
```

---

### Algorithm: upload_reference_text

```
INPUT: db, redis, org_id: UUID, sku_id: UUID, data: ReferenceTextRequest
OUTPUT: ReferenceTextUploadResponse

1. sku = await SKURepository.get_by_id_and_org(db, sku_id, org_id)
   IF sku is None:
     RAISE LookupError("SKU_NOT_FOUND")

2. updates = {}
   task_ids = {}

   IF data.reference_description is not None:
     IF len(data.reference_description) > 2000:
       RAISE ValueError("DESCRIPTION_TOO_LONG")
     updates["reference_description"] = data.reference_description
     redis.delete(f"ref_emb:{sku_id}:desc")
     task = compute_text_embedding.delay(str(sku_id), "desc", data.reference_description)
     task_ids["description"] = task.id

   IF data.reference_composition is not None:
     IF len(data.reference_composition) > 1000:
       RAISE ValueError("COMPOSITION_TOO_LONG")
     updates["reference_composition"] = data.reference_composition
     redis.delete(f"ref_emb:{sku_id}:comp")
     task = compute_text_embedding.delay(str(sku_id), "comp", data.reference_composition)
     task_ids["composition"] = task.id

3. IF updates:
     await SKURepository.update(db, sku, **updates)

4. RETURN ReferenceTextUploadResponse(sku_id=sku_id, embedding_task_ids=task_ids)
```

---

### Algorithm: get_presigned_url

```
INPUT: db, minio, org_id: UUID, sku_id: UUID
OUTPUT: PresignedUrlResponse

1. sku = await SKURepository.get_by_id_and_org(db, sku_id, org_id)
   IF sku is None:
     RAISE LookupError("SKU_NOT_FOUND")

2. IF sku.reference_image_url is None:
     RAISE LookupError("REFERENCE_IMAGE_NOT_FOUND")

3. presigned_url = await minio.generate_presigned_url(sku.reference_image_url, expires=3600)

4. RETURN PresignedUrlResponse(sku_id=sku_id, presigned_url=presigned_url, expires_in=3600)
```

---

### Algorithm: compute_clip_embedding (Celery task)

```
INPUT: sku_id: str, s3_key: str
SIDE EFFECT: writes to Redis

1. image_bytes = s3_client.get_object(Bucket="cat-references", Key=s3_key)["Body"].read()

2. image = PIL.Image.open(BytesIO(image_bytes)).convert("RGB")
   preprocess = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
   inputs = preprocess(images=image, return_tensors="pt")

3. WITH torch.no_grad():
     embedding = clip_model.get_image_features(**inputs)
     embedding = embedding / embedding.norm(dim=-1, keepdim=True)  # L2 normalise
     embedding_np = embedding.squeeze().numpy()  # shape [512]

4. redis_client.setex(
     f"ref_emb:{sku_id}:image",
     2592000,
     pickle.dumps(embedding_np)
   )
```

---

### Algorithm: compute_text_embedding (Celery task)

```
INPUT: sku_id: str, field: "desc" | "comp", text: str
SIDE EFFECT: writes to Redis

1. # multilingual-e5 expects "query: " or "passage: " prefix
   prefixed = f"passage: {text}"

2. inputs = e5_tokenizer(prefixed, return_tensors="pt", truncation=True, max_length=512)
   WITH torch.no_grad():
     outputs = e5_model(**inputs)
     embedding = outputs.last_hidden_state[:, 0, :]  # CLS token
     embedding = embedding / embedding.norm(dim=-1, keepdim=True)
     embedding_np = embedding.squeeze().numpy()  # shape [768]

3. redis_client.setex(
     f"ref_emb:{sku_id}:{field}",
     2592000,
     pickle.dumps(embedding_np)
   )
```

---

## 3. Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `SKU_NOT_FOUND` | 404 | SKU not found or cross-org |
| `REFERENCE_IMAGE_NOT_FOUND` | 404 | No image uploaded yet |
| `FILE_TOO_LARGE` | 422 | Image > 10 MB |
| `INVALID_IMAGE_TYPE` | 422 | Extension not jpg/png/webp |
| `INVALID_IMAGE_MAGIC` | 422 | Magic bytes mismatch |
| `DESCRIPTION_TOO_LONG` | 422 | > 2000 chars |
| `COMPOSITION_TOO_LONG` | 422 | > 1000 chars |
| `S3_UPLOAD_FAILED` | 503 | MinIO error |
