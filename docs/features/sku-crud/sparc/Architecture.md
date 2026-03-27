# Architecture — SKU CRUD + Bulk Upload

**SPARC Phase 5: Architecture** | Feature: sku-crud

---

## 1. Domain Placement

SKU CRUD is a pure data management domain within the existing `services/api` FastAPI monolith:

```
services/api/app/
├── core/           ← existing (db, config, deps, security)
├── auth/           ← existing (done)
└── catalog/        ← NEW (this feature)
    ├── __init__.py
    ├── models.py      # Brand, SKU, Platform, SKUPlatform ORM models
    ├── schemas.py     # Pydantic request/response schemas
    ├── repository.py  # DB queries (all filtered by org_id)
    ├── service.py     # Business logic (bulk upload, duplicate check)
    └── router.py      # FastAPI routes (brands, skus, platforms, sku-platforms)
```

---

## 2. Database Schema

```sql
-- Brands (tenant-scoped)
CREATE TABLE brands (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    name        VARCHAR(255) NOT NULL,
    type        VARCHAR(50) NOT NULL DEFAULT 'client',  -- client | competitor
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_brands_type CHECK (type IN ('client', 'competitor')),
    CONSTRAINT uq_brands_org_name UNIQUE (org_id, name)
);

-- SKUs (tenant-scoped)
CREATE TABLE skus (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    brand_id              UUID NOT NULL REFERENCES brands(id) ON DELETE RESTRICT,
    article               VARCHAR(100),
    rpc                   VARCHAR(100),
    name                  VARCHAR(500) NOT NULL,
    barcode               VARCHAR(50),
    category              VARCHAR(255),
    sub_category          VARCHAR(255),
    reference_image_url   TEXT,
    reference_description TEXT,
    reference_composition TEXT,
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_skus_org_article UNIQUE (org_id, article)  -- nullable article excluded by partial index
);
CREATE UNIQUE INDEX uq_skus_org_article_partial
    ON skus (org_id, article)
    WHERE article IS NOT NULL;

-- Platforms (global catalog, ops-managed)
CREATE TABLE platforms (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(100) NOT NULL UNIQUE,
    type            VARCHAR(50),    -- marketplace | darkstore | retailer
    scraper_module  VARCHAR(100),
    schedule_cron   VARCHAR(50) DEFAULT '0 2 * * *',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);

-- SKU × Platform mapping (tenant-scoped via sku → org)
CREATE TABLE sku_platforms (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sku_id      UUID NOT NULL REFERENCES skus(id) ON DELETE CASCADE,
    platform_id UUID NOT NULL REFERENCES platforms(id) ON DELETE RESTRICT,
    external_id VARCHAR(255),
    url         TEXT,
    is_monitored BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_sku_platforms UNIQUE (sku_id, platform_id)
);

-- Indexes
CREATE INDEX idx_brands_org_id      ON brands (org_id);
CREATE INDEX idx_skus_org_id        ON skus (org_id);
CREATE INDEX idx_skus_brand_id      ON skus (brand_id);
CREATE INDEX idx_skus_active        ON skus (org_id, is_active);
CREATE INDEX idx_sku_platforms_sku  ON sku_platforms (sku_id);
```

---

## 3. Alembic Migration

New migration: `infrastructure/postgres/migrations/0002_create_catalog_tables.py`

Upgrade order: organizations → brands → skus → platforms → sku_platforms
Downgrade order: reverse.

---

## 4. API Layer Design

### Router → Service → Repository

```
POST /api/v1/skus
  router.py       validates body via SKUCreateRequest Pydantic schema
  service.py      checks duplicate article, calls repo.create()
  repository.py   INSERT INTO skus (...) WHERE all values include org_id

POST /api/v1/skus/bulk-upload
  router.py       accepts UploadFile, validates content_type
  service.py      parse CSV → validate rows → batch insert → return report
  repository.py   bulk_create(db, rows: list[dict], org_id) in chunks of 100
```

### Pagination Design

Cursor-based pagination using `created_at + id` as a stable cursor:
```
GET /api/v1/skus?limit=50&cursor=<base64(created_at:id)>
Response: { items: [...], total: int, next_cursor: str | null }
```

Offset pagination is avoided — 10 000 SKUs with `OFFSET 9950` is slow.

### Bulk Upload Design

```
1. Read CSV bytes (max 5 MB)
2. Detect delimiter (comma vs semicolon)
3. Validate headers — abort if required headers missing
4. Iterate rows (max 1000):
   a. Validate each row → collect errors
   b. Resolve brand_name → brand_id (create brand if not exists)
   c. Accumulate valid rows
5. Bulk INSERT valid rows in chunks of 100 (single transaction per chunk)
6. Return: { imported: N, failed: M, errors: [...] }
```

---

## 5. File Structure to Create

```
services/api/app/catalog/
├── __init__.py
├── models.py       # Brand, SKU, Platform, SKUPlatform
├── schemas.py      # 12 Pydantic schemas
├── repository.py   # BrandRepository, SKURepository, PlatformRepository, SKUPlatformRepository
├── service.py      # create_sku, bulk_upload_skus, list_skus, update_sku, delete_sku, ...
└── router.py       # 11 endpoints

infrastructure/postgres/migrations/
└── 0002_create_catalog_tables.py

services/api/tests/
├── unit/
│   └── test_bulk_upload.py    # CSV parsing, validation logic
└── e2e/
    └── test_catalog_api.py    # Full HTTP stack tests
```

---

## 6. Key Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Article uniqueness | Partial UNIQUE index (org_id, article) WHERE article IS NOT NULL | article is optional; NULL must not conflict |
| Bulk insert | Chunked INSERT 100 rows/transaction | Avoids locking full table; rollback granularity |
| Brand auto-create on bulk | Yes — if brand_name not found, create with type="client" | Reduces friction for bulk import |
| Soft delete | is_active=false | Historical scores reference sku_id — hard delete breaks FK |
| Platform catalog | Shared across orgs, read-only via API | Scrapers are org-agnostic; platform config managed by ops |
| Pagination | Cursor-based | Stable under concurrent inserts; no OFFSET scan |
