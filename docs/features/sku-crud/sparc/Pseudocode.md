# Pseudocode — SKU CRUD + Bulk Upload

**SPARC Phase 4: Pseudocode** | Feature: sku-crud

---

## 1. Data Structures

```
Brand {
  id: UUID
  org_id: UUID
  name: str (max 255)
  type: "client" | "competitor"
  created_at: datetime
}

SKU {
  id: UUID
  org_id: UUID
  brand_id: UUID
  article: str | None (max 100, unique per org where not null)
  rpc: str | None
  name: str (max 500, required)
  barcode: str | None
  category: str | None
  sub_category: str | None
  reference_image_url: str | None
  reference_description: str | None
  reference_composition: str | None
  is_active: bool = True
  created_at: datetime
  updated_at: datetime
}

Platform {
  id: UUID
  name: str
  type: "marketplace" | "darkstore" | "retailer"
  scraper_module: str | None
  schedule_cron: str
  is_active: bool
}

SKUPlatform {
  id: UUID
  sku_id: UUID
  platform_id: UUID
  external_id: str | None
  url: str | None
  is_monitored: bool = True
  created_at: datetime
}

BulkUploadReport {
  imported: int
  failed: int
  errors: list[{ row: int, field: str, reason: str }]
}
```

---

## 2. Algorithms

### Algorithm: create_sku

```
INPUT: db, org_id: UUID, data: SKUCreateRequest
OUTPUT: SKU

1. IF data.article is not None:
     existing = await SKURepository.get_by_org_article(db, org_id, data.article)
     IF existing is not None:
       RAISE DomainError("SKU_ARTICLE_DUPLICATE")

2. brand = await BrandRepository.get_by_id(db, data.brand_id)
   IF brand is None OR brand.org_id != org_id:
     RAISE DomainError("BRAND_NOT_FOUND")

3. sku = SKU(org_id=org_id, **data.model_dump())
   db.add(sku)
   await db.commit()
   await db.refresh(sku)

4. RETURN sku
```

---

### Algorithm: list_skus (cursor pagination)

```
INPUT: db, org_id: UUID, filters: SKUListFilters, limit: int, cursor: str | None
OUTPUT: SKUListResponse { items, total, next_cursor }

1. base_query = SELECT skus WHERE org_id = org_id

2. IF NOT filters.include_inactive:
     base_query = base_query WHERE is_active = TRUE

3. IF filters.brand_id:
     base_query = base_query WHERE brand_id = filters.brand_id

4. IF cursor is not None:
     decoded = decode_cursor(cursor)  # base64 → { created_at, id }
     base_query = base_query WHERE (created_at, id) < (decoded.created_at, decoded.id)

5. total = await count(base_query without cursor)

6. items = await fetch(base_query ORDER BY created_at DESC, id DESC LIMIT limit + 1)

7. IF len(items) > limit:
     next_cursor = encode_cursor(items[limit-1].created_at, items[limit-1].id)
     items = items[:limit]
   ELSE:
     next_cursor = None

8. RETURN { items, total, next_cursor }
```

---

### Algorithm: bulk_upload_skus

```
INPUT: db, org_id: UUID, file: UploadFile
OUTPUT: BulkUploadReport

1. content = await file.read()
   IF len(content) > 5_242_880:  # 5 MB
     RAISE ValidationError("FILE_TOO_LARGE")

   IF file.content_type not in ["text/csv", "application/octet-stream"]:
     IF NOT file.filename.endswith(".csv"):
       RAISE ValidationError("INVALID_FILE_TYPE")

2. text = content.decode("utf-8-sig")  # strip BOM if present
   delimiter = detect_delimiter(text)  # returns "," or ";"
   reader = csv.DictReader(text.splitlines(), delimiter=delimiter)

3. headers = {h.strip().lower() for h in reader.fieldnames or []}
   IF "name" not in headers:
     RAISE ValidationError("MISSING_REQUIRED_COLUMN: name")

4. rows = list(reader)
   IF len(rows) > 1000:
     RAISE ValidationError("CSV_TOO_LARGE")

5. errors = []
   valid_rows = []
   brand_cache = {}  # brand_name → brand_id (avoid N queries)

   FOR i, row IN enumerate(rows, start=2):  # row 1 = header
     row_errors = validate_row(row, i)
     IF row_errors:
       errors.extend(row_errors)
       CONTINUE

     brand_name = row.get("brand_name", "").strip()
     IF brand_name not in brand_cache:
       # get_or_create_by_name MUST use INSERT ... ON CONFLICT (org_id, name) DO NOTHING RETURNING id
       # to be race-safe under concurrent bulk uploads from the same org
       brand = await BrandRepository.get_or_create_by_name(db, org_id, brand_name)
       brand_cache[brand_name] = brand.id
     brand_id = brand_cache[brand_name]

     article = row.get("article", "").strip() or None
     IF article is not None:
       existing = await SKURepository.get_by_org_article(db, org_id, article)
       IF existing:
         errors.append({ row: i, field: "article", reason: "SKU_ARTICLE_DUPLICATE" })
         CONTINUE

     valid_rows.append(build_sku_dict(row, org_id, brand_id))

6. # Batch insert in chunks of 100
   # Wrap in try/except IntegrityError: concurrent duplicate inserts not caught by pre-check
   # will be caught here and reported as errors (do not crash the whole upload)
   imported = 0
   FOR chunk IN chunks(valid_rows, size=100):
     TRY:
       await SKURepository.bulk_create(db, chunk)
       imported += len(chunk)
     EXCEPT IntegrityError:
       # individual duplicate slipped through pre-check; fall back to row-by-row
       FOR row IN chunk:
         TRY:
           await SKURepository.bulk_create(db, [row])
           imported += 1
         EXCEPT IntegrityError:
           errors.append({ row: row["_row_num"], field: "article", reason: "SKU_ARTICLE_DUPLICATE" })

7. RETURN BulkUploadReport(
     imported=imported,
     failed=len(errors),
     errors=errors
   )


HELPER: validate_row(row, row_num) → list[RowError]
  errors = []
  IF not row.get("name", "").strip():
    errors.append({ row: row_num, field: "name", reason: "REQUIRED_FIELD" })
  name = row.get("name", "")
  IF len(name) > 500:
    errors.append({ row: row_num, field: "name", reason: "MAX_LENGTH_EXCEEDED" })
  RETURN errors


HELPER: detect_delimiter(text) → str  # returns "," or ";"
  first_line = text.split("\n")[0]
  commas = first_line.count(",")
  semicolons = first_line.count(";")
  RETURN ";" if semicolons > commas else ","
```

---

### Algorithm: delete_sku (soft delete)

```
INPUT: db, org_id: UUID, sku_id: UUID
OUTPUT: SKU

1. sku = await SKURepository.get_by_id_and_org(db, sku_id, org_id)
   IF sku is None:
     RAISE DomainError("SKU_NOT_FOUND")  # 404 — don't leak existence to other orgs

2. sku.is_active = False
   sku.updated_at = now_utc()
   await db.commit()
   await db.refresh(sku)

3. RETURN sku
```

---

### Algorithm: create_sku_platform

```
INPUT: db, org_id: UUID, data: SKUPlatformCreateRequest
OUTPUT: SKUPlatform

1. sku = await SKURepository.get_by_id_and_org(db, data.sku_id, org_id)
   IF sku is None:
     RAISE DomainError("SKU_NOT_FOUND")

2. platform = await PlatformRepository.get_by_id(db, data.platform_id)
   IF platform is None OR NOT platform.is_active:
     RAISE DomainError("PLATFORM_NOT_FOUND")

3. existing = await SKUPlatformRepository.get_by_sku_platform(db, data.sku_id, data.platform_id)
   IF existing is not None:
     RAISE DomainError("SKU_PLATFORM_DUPLICATE")

4. sp = SKUPlatform(sku_id=data.sku_id, platform_id=data.platform_id,
                     external_id=data.external_id, url=data.url)
   db.add(sp)
   await db.commit()
   await db.refresh(sp)

5. RETURN sp
```

---

## 3. API Response Schemas

### SKUResponse
```json
{
  "id": "uuid",
  "org_id": "uuid",
  "brand": { "id": "uuid", "name": "ИндиЛайт", "type": "client" },
  "article": "3927",
  "rpc": null,
  "name": "Индейка Индилайт Духовая",
  "barcode": "4600000123456",
  "category": "Мясо птицы",
  "sub_category": "Индейка",
  "is_active": true,
  "created_at": "2026-03-27T10:00:00Z",
  "updated_at": "2026-03-27T10:00:00Z"
}
```

### SKUListResponse
```json
{
  "items": [ <SKUResponse> ],
  "total": 150,
  "next_cursor": "base64string_or_null"
}
```

### BulkUploadResponse
```json
{
  "imported": 198,
  "failed": 2,
  "errors": [
    { "row": 5,  "field": "name", "reason": "REQUIRED_FIELD" },
    { "row": 47, "field": "name", "reason": "REQUIRED_FIELD" }
  ]
}
```

---

## 4. Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `SKU_ARTICLE_DUPLICATE` | 409 | Article already exists in this org |
| `SKU_NOT_FOUND` | 404 | SKU not found (or belongs to another org) |
| `BRAND_NOT_FOUND` | 404 | brand_id not found in this org |
| `BRAND_NAME_DUPLICATE` | 409 | Brand with same name already exists in this org |
| `SKU_PLATFORM_DUPLICATE` | 409 | SKU already linked to this platform |
| `PLATFORM_NOT_FOUND` | 404 | Platform not found or inactive |
| `CSV_TOO_LARGE` | 422 | More than 1000 rows |
| `FILE_TOO_LARGE` | 422 | File > 5 MB |
| `INVALID_FILE_TYPE` | 422 | Not a .csv file |
| `MISSING_REQUIRED_COLUMN` | 422 | CSV missing required header |
