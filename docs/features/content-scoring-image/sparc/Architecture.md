# Architecture — Content Scoring: Image (CLIP)

---

## Component Map

```
┌─────────────────────────────────────────────────────────────────────┐
│  API Service (services/api/)                                        │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  reference_service.py                                        │   │
│  │  _dispatch_clip_task(sku_id, s3_key)                         │   │
│  │    → compute_clip_embedding.delay(sku_id, s3_key)            │   │
│  └──────────────────────────┬───────────────────────────────────┘   │
└─────────────────────────────│───────────────────────────────────────┘
                              │ Celery task via Redis broker
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Processor Service (services/processor/)                            │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  app/tasks/clip_embedding_task.py                           │    │
│  │  compute_clip_embedding(sku_id, s3_key)                     │    │
│  │    1. Download image from MinIO                             │    │
│  │    2. CLIP.encode_image() → np.ndarray [512]               │    │
│  │    3. redis.set(ref_emb:{sku_id}:image, pickle(emb), ex=30d)│    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  app/tasks/image_scoring_task.py                            │    │
│  │  score_image_content_all()   ← Celery Beat 06:00 UTC        │    │
│  │    1. Query content_scores WHERE today, image_score IS NULL │    │
│  │    2. Celery group(score_image_content.s(id, sku_id, key))  │    │
│  │                                                             │    │
│  │  score_image_content(cs_id, sku_id, s3_key)                │    │
│  │    1. Download collected image from MinIO                   │    │
│  │    2. CLIP.encode_image() → np.ndarray [512]               │    │
│  │    3. redis.get(ref_emb:{sku_id}:image) → ref_emb          │    │
│  │    4. cosine_sim(collected_emb, ref_emb) → score [0..1]    │    │
│  │    5. UPDATE content_scores SET image_score=score           │    │
│  │       WHERE id = cs_id                                      │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  app/core/clip_model.py                                     │    │
│  │  Singleton: CLIPProcessor + CLIPModel loaded once per worker│    │
│  │  encode_image(pil_image) → np.ndarray [512], normalized    │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  app/core/db.py   — sync SQLAlchemy session (same as        │    │
│  │                     collector pattern)                      │    │
│  │  app/core/minio_client.py — MinIO download                  │    │
│  │  app/core/redis_client.py — Redis get/set for embeddings    │    │
│  └─────────────────────────────────────────────────────────────┘    │
└────────────────────────────────────┬────────────────────────────────┘
                                     │
              ┌──────────────────────┼───────────────────────┐
              ▼                      ▼                       ▼
         PostgreSQL              MinIO (S3)                Redis
    content_scores.image_score  org/{org}/sku/{sku}/     ref_emb:{sku_id}:image
    UPDATE by cs_id             platform/main.jpg        TTL 30d, pickle bytes
```

---

## File Structure

```
services/processor/
├── Dockerfile
├── requirements.txt
├── pytest.ini
├── app/
│   ├── __init__.py
│   ├── celery_app.py              # Celery app + Beat schedule
│   ├── core/
│   │   ├── __init__.py
│   │   ├── clip_model.py          # CLIP singleton loader
│   │   ├── db.py                  # Sync SQLAlchemy session factory
│   │   ├── minio_client.py        # MinIO download helper
│   │   └── redis_client.py        # Redis embedding cache client
│   ├── models.py                  # Sync ORM: ContentScore, SKU, SKUPlatform
│   └── tasks/
│       ├── __init__.py
│       ├── clip_embedding_task.py # compute_clip_embedding
│       └── image_scoring_task.py  # score_image_content_all + score_image_content
└── tests/
    ├── __init__.py
    ├── conftest.py
    └── test_image_scoring.py
```

---

## CLIP Model Details

| Property | Value |
|----------|-------|
| Model ID | `openai/clip-vit-base-patch32` |
| Embedding dim | 512 |
| Input | PIL Image (any size — preprocessed by CLIPProcessor) |
| Output | `np.ndarray` shape `[512]`, L2-normalized |
| RAM per worker | ~340 MB (CPU weights) |
| Inference time | ~80 ms/image CPU; batch of 32 ~1.5 s |
| Loading strategy | Module-level singleton, loaded on first call, cached per process |

```python
# app/core/clip_model.py — singleton pattern
from transformers import CLIPModel, CLIPProcessor
import torch, numpy as np
from PIL import Image

_model: CLIPModel | None = None
_processor: CLIPProcessor | None = None
_MODEL_ID = "openai/clip-vit-base-patch32"

def _load():
    global _model, _processor
    if _model is None:
        _processor = CLIPProcessor.from_pretrained(_MODEL_ID)
        _model = CLIPModel.from_pretrained(_MODEL_ID)
        _model.eval()

def encode_image(pil_image: Image.Image) -> np.ndarray:
    _load()
    inputs = _processor(images=pil_image, return_tensors="pt")
    with torch.no_grad():
        features = _model.get_image_features(**inputs)
    vec = features[0].numpy()
    return vec / np.linalg.norm(vec)  # L2 normalize
```

---

## Redis Embedding Cache

```
Key:   ref_emb:{sku_id}:image
Value: pickle.dumps(np.ndarray)   # binary blob, ~2 KB
TTL:   2592000 seconds (30 days)
```

**Cache invalidation:** `reference_service._invalidate_embedding(redis, sku_id, "image")` deletes the key on every reference re-upload. The next `compute_clip_embedding` task recomputes and stores the new value.

---

## Celery Beat Schedule (processor celery_app.py)

```python
app.conf.beat_schedule = {
    "score-image-content-daily": {
        "task": "processor.score_image_content_all",
        "schedule": crontab(hour=6, minute=0),   # 06:00 UTC daily
    },
}
```

**Timing rationale:**
- Collector finishes daily scraping by ~05:30 UTC (last scraper: Lenta at 05:00 + 30 min buffer)
- `score_image_content_all` starts at 06:00 UTC — guaranteed fresh data
- Text scoring (Sprint 3b) runs at 06:30 UTC — after image scoring completes for most SKUs

---

## Docker Service

```yaml
# docker-compose.yml addition
processor:
  build: ./services/processor
  env_file: .env
  depends_on: [redis, postgres, minio]
  volumes:
    - huggingface_cache:/root/.cache/huggingface  # model weights persist across restarts
  environment:
    - CELERY_WORKER_CONCURRENCY=2  # 2 workers × 340 MB = ~680 MB RAM
  command: celery -A app.celery_app worker -l info -c 2

processor-beat:
  build: ./services/processor
  env_file: .env
  depends_on: [redis, postgres]
  command: celery -A app.celery_app beat -l info
  deploy:
    replicas: 1  # Beat: EXACTLY one replica

volumes:
  huggingface_cache:
```

---

## Multi-Tenant Design

Tenant isolation is structural, not policy-based:

1. `score_image_content_all` queries `content_scores` joined through `sku_platforms → skus` — retrieves `sku_id` per row.
2. Redis key `ref_emb:{sku_id}:image` — `sku_id` is globally unique UUID, always scoped to one org.
3. UPDATE is by `content_scores.id` (PK) — single-row, no cross-org risk.
4. MinIO key `org/{org_id}/sku/{sku_id}/platform/main.jpg` — org_id in path prevents cross-tenant reads if bucket policy were ever misconfigured.
5. PostgreSQL RLS provides final backstop (application user, not superuser).

No explicit `org_id` WHERE clause needed in UPDATE because PK scoping is sufficient. The orchestrator query joins through `sku_id` which carries `org_id` implicitly.
