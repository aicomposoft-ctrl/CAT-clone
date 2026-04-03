# Architecture: Excel Export — Content Scores

**Feature:** `excel-export-content`
**Date:** 2026-04-02

---

## Position in the System

The feature lives entirely within `services/api/app/reports/`. It is a **read-only, synchronous-in-request** export: the API worker queries PostgreSQL, builds an Excel workbook in memory, and streams the bytes back to the caller within the same HTTP request. No Celery tasks, no MinIO uploads, no background jobs.

```
Client
  │
  │  GET /api/v1/reports/content-export?date_from=...&date_to=...
  ▼
Nginx (SSL termination)
  │
  ▼
FastAPI API service
  │
  ├─ app/reports/router.py       ← HTTP layer (auth, validation, response)
  ├─ app/reports/service.py      ← Excel generation (openpyxl, BytesIO)
  └─ app/reports/repository.py   ← DB query (async SQLAlchemy)
         │
         ▼
      PostgreSQL
        content_scores ─ sku_platforms ─ skus ─ brands
                                    └───────── platforms
```

---

## Module Responsibilities

| Module | Responsibility | Knows About |
|--------|---------------|-------------|
| `router.py` | Receives HTTP request, validates JWT, validates date range, calls service, returns Response | FastAPI, service |
| `service.py` | Calls repository, calls `_build_workbook()`, serialises workbook to BytesIO bytes | repository, openpyxl |
| `repository.py` | Executes SQL JOIN query, returns flat `ContentScoreRow` dataclasses | SQLAlchemy, catalog models |
| `models.py` | Read-only ORM mapping of `content_scores` table for JOIN queries | SQLAlchemy Base |

---

## Data Model (Read-Only)

`models.py` defines `ContentScoreRead` — a read-only SQLAlchemy mapping to the `content_scores` table. It is never written to from the reports module. All score columns (`image_score`, `description_score`, `composition_score`, `content_total`) and `in_stock`/`warehouse_qty` are `Optional` to handle rows where the ML processor has not yet run.

```
ContentScoreRead (content_scores)
  id                 UUID PK
  sku_platform_id    UUID FK → sku_platforms.id
  scored_at          Date
  collected_title    String(500) nullable
  image_score        Numeric(5,2) nullable
  description_score  Numeric(5,2) nullable
  composition_score  Numeric(5,2) nullable
  content_total      Numeric(5,2) nullable
  in_stock           Boolean nullable
  warehouse_qty      Integer nullable
  created_at         DateTime(tz)
```

---

## JOIN Chain (Content Export)

```
content_scores
  INNER JOIN sku_platforms  ON content_scores.sku_platform_id = sku_platforms.id
  INNER JOIN skus            ON sku_platforms.sku_id = skus.id
                               WHERE skus.org_id = :org_id          ← tenant isolation
  INNER JOIN brands          ON skus.brand_id = brands.id
  INNER JOIN platforms       ON sku_platforms.platform_id = platforms.id
  WHERE content_scores.scored_at BETWEEN :date_from AND :date_to
  [AND sku_platforms.platform_id = :platform_id]                    ← optional filter
  ORDER BY brands.name, skus.article NULLS LAST, platforms.name, content_scores.scored_at
```

Projected columns: `brand_name`, `sku_article`, `sku_name`, `platform_name`, `scored_at`, `image_score`, `description_score`, `composition_score`, `content_total`.

---

## Multi-Tenant Isolation Mechanism

`content_scores` has **no `org_id` column**. Isolation is enforced by joining through the ownership chain:

```
content_scores → sku_platforms → skus (WHERE skus.org_id = :org_id)
```

The `org_id` value is always sourced from `current_user.org_id` (JWT claim), never from the request query parameters. PostgreSQL RLS policies on the `skus` table provide a second layer of enforcement.

---

## BytesIO Streaming (No Disk I/O)

```python
buf = io.BytesIO()
wb.save(buf)      # openpyxl writes to the buffer
buf.seek(0)
return buf.read() # caller receives raw bytes
```

The workbook is never written to the filesystem. FastAPI returns the bytes directly via `Response(content=xlsx_bytes, media_type=...)`. This makes the feature compatible with read-only container filesystems and avoids cleanup concerns.

---

## Excel Generation Pipeline

```
ContentScoreRow[] (from repository)
  │
  ▼  _build_workbook(rows, date_from, date_to)
     │
     ├─ Create Workbook + active sheet "Content Scores"
     ├─ Merge A1:I1 → period sub-header
     ├─ Write column headers in row 2 (fill, font, width, freeze panes, auto-filter)
     └─ For each row (starting row 3):
           ├─ Write 9 cell values
           └─ If content_total is not NULL: apply PatternFill to columns 6–9
  │
  ▼
Workbook → BytesIO → bytes
```

---

## Column Width Implementation

Column widths are set explicitly via `ws.column_dimensions[get_column_letter(col_idx)].width = width` during header row construction. This is required because openpyxl does not support auto-sizing. Widths are defined in `_COLUMNS` as the third element of each tuple.

---

## File Locations

| File | Path |
|------|------|
| ORM models | `services/api/app/reports/models.py` |
| DB query | `services/api/app/reports/repository.py` |
| Excel generation | `services/api/app/reports/service.py` |
| HTTP routes | `services/api/app/reports/router.py` |
| E2E tests | `services/api/tests/e2e/test_reports_api.py` |

---

## Dependencies

| Dependency | Purpose |
|-----------|---------|
| `openpyxl` | Excel workbook creation (no xlrd/xlwt needed) |
| `sqlalchemy.ext.asyncio.AsyncSession` | Non-blocking DB queries |
| `fastapi.responses.Response` | Binary response with custom headers |
| `app.auth.models.User` | JWT-decoded user (provides `org_id`) |
| `app.core.deps.get_current_user` | JWT verification dependency |
| `app.catalog.models` | `SKU`, `SKUPlatform`, `Brand`, `Platform` for JOIN |
