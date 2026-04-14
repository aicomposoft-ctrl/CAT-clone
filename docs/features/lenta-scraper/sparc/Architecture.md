# Architecture: Lenta Scraper

## Overview

The Lenta scraper follows the identical architecture as the Samocat scraper
(Sprint 2). Five Celery tasks + one scraper class + one set of unit tests.
No new infrastructure components required.

## File Layout

```
services/collector/
├── app/
│   ├── scrapers/
│   │   └── lenta.py                   # LentaScraper(BaseScraper) + helpers
│   └── tasks/
│       ├── lenta_content_task.py      # collect_lenta_content Celery task
│       ├── lenta_price_task.py        # collect_lenta_price Celery task
│       ├── lenta_stock_task.py        # collect_lenta_stock Celery task
│       ├── lenta_reviews_task.py      # collect_lenta_reviews Celery task
│       └── lenta_orchestrator.py      # collect_lenta_content_all +
│                                      # collect_lenta_prices_all
└── tests/
    └── test_lenta_tasks.py            # 60+ unit tests (mocked HTTP + DB)
```

`celery_app.py` `include` list gets 5 new entries.

## Component Diagram

```
Celery Beat
  ├── lenta.collect_content_all  (daily 05:00 UTC — offset from Samocat 04:00)
  │     └── group(content + stock + reviews per sku_platform_id) × N
  └── lenta.collect_prices_all   (every 4h, offset +1h from Samocat)
        └── group(price per sku_platform_id) × N

Worker Pool (prefork, asyncio.run per task)
  ├── lenta.collect_content   → LentaScraper.collect_content()
  │                           → MinIO upload (non-fatal)
  │                           → content_scores upsert (full-row)
  ├── lenta.collect_price     → LentaScraper.collect_price()
  │                           → price_snapshots INSERT
  ├── lenta.collect_stock     → LentaScraper.collect_stock()
  │                           → content_scores upsert (partial-row)
  └── lenta.collect_reviews   → LentaScraper.collect_reviews()
                              → reviews bulk upsert

LentaScraper(BaseScraper)
  ├── _fetch_product()         → GET /api/v1/products/{article_id}
  │   (shared by content/price/stock — single HTTP call)
  └── collect_reviews()        → GET /api/v1/products/{article_id}/reviews
```

## Lenta API Design

### Single Product Endpoint

`GET https://lenta.com/api/v1/products/{article_id}`

```json
{
  "id": "12345",
  "name": "Молоко Простоквашино 3.2% 930мл",
  "description": "Натуральное пастеризованное молоко...",
  "composition": "Молоко нормализованное пастеризованное",
  "images": [
    { "url": "https://lenta.com/images/products/12345/main.jpg" }
  ],
  "price": 15990,
  "originalPrice": 19990,
  "discountPercent": 20,
  "promoLabel": "Акция",
  "inStock": true,
  "availableQuantity": 120
}
```

- Prices in **kopeks** (integer) → divide by 100 → Decimal RUB.
- `originalPrice` absent → use `price` for original_price.
- `discountPercent` absent → 0.
- `availableQuantity` may be integer or string → defensive cast.

### Reviews Endpoint

`GET https://lenta.com/api/v1/products/{article_id}/reviews?page=1&limit=50`

```json
{
  "reviews": [
    {
      "id": "rev-abc123",
      "text": "Отличное молоко, свежее",
      "rating": 5,
      "createdAt": "2026-03-15T10:00:00Z"
    }
  ]
}
```

- 404 → return `[]` (product may have no reviews endpoint).
- `id` field → `external_review_id`, capped at 200 chars.

## Security Design

### SSRF Guard

```python
_LT_IMAGE_CDN_RE = re.compile(
    r"^https://lenta\.com/images/[A-Za-z0-9/_\-\.]+\.(jpg|jpeg|png|webp)$"
)
```

- Validated at three layers: `collect_content()`, `_download_image_async()`.
- Non-matching URLs: discarded + logged (without URL value).

### Input Validation

- `_parse_product_id()` (shared with Samocat): rejects non-numeric IDs before HTTP.
- All text via `sanitize()` (strips HTML, caps length).
- `external_review_id`: `[:200].strip()`.

## DB Write Pattern

### content_scores (full-row upsert via content task)
```
INSERT ... ON CONFLICT (sku_platform_id, scored_at) DO UPDATE SET
  collected_title, collected_description, collected_composition, collected_image_url
```

### content_scores (partial-row upsert via stock task)
```
INSERT ... ON CONFLICT (sku_platform_id, scored_at) DO UPDATE SET
  in_stock, warehouse_qty
  -- content fields INTENTIONALLY ABSENT
```

### price_snapshots (append-only INSERT)
```
INSERT INTO price_snapshots (...) VALUES (...)
-- No ON CONFLICT — every price tick is a new row
```

### reviews (bulk upsert)
```
INSERT INTO reviews (...) VALUES (list)
ON CONFLICT (sku_platform_id, external_review_id) DO UPDATE SET
  review_text, rating, review_date
```

## Celery Task Schedule (Celery Beat)

| Task name | Cron | Offset rationale |
|-----------|------|------------------|
| `lenta.collect_content_all` | `0 5 * * *` | 05:00 UTC — 1h after Samocat |
| `lenta.collect_prices_all` | `0 3,7,11,15,19,23 * * *` | Offset from Samocat/Ozon |

## Multi-Tenant Isolation

- Orchestrator: cross-org ID query (read-only, safe — same rationale as WB/Ozon/Samocat).
- Each task: Session 1 reads `(sp_id, sku_id, external_id, org_id)` as primitives.
- S3 key: `org/{org_id}/sku/{sku_id}/lenta/main.jpg`.
- DB writes keyed on `sku_platform_id` → FK chain → org isolation + RLS backstop.
