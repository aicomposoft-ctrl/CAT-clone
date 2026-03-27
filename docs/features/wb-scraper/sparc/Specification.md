# Specification — Wildberries Scraper

**SPARC Phase 3: Specification** | Feature: wb-scraper

---

## 1. User Stories

### US-W01: Content Collection

```gherkin
Feature: WB Scraper

Scenario: Celery task collects content for a WB SKU
  Given sku_platform record exists with platform="Wildberries" and external_id="12345678"
  When collect_wb_content task runs for that sku_platform
  Then a content_scores row is upserted for today's date
  And collected_title is set (max 500 chars, HTML stripped)
  And collected_image_url is set to an S3 key (downloaded image) or null if download fails
  And collected_description is sanitised (HTML stripped, max 5000 chars)
  And collected_composition is set (or null if not present)

Scenario: SKU has no external_id set
  Given sku_platform has external_id = null
  When collect_wb_content task runs
  Then the task raises SkipTask("NO_NM_ID") and no DB write occurs

Scenario: WB returns 429 Too Many Requests
  Given WB API returns 429
  When collect_wb_content is called
  Then the task retries with exponential backoff (1s, 2s, 4s)
  And after 3 retries the task is marked as failed with "RATE_LIMITED"

Scenario: Product not found on WB (404 or deleted)
  Given nm_id does not exist or product is deleted
  When collect_wb_content is called
  Then task records failure reason "NOT_FOUND" and does not create a content_scores row

Scenario: WB returns unexpected response structure
  Given WB card API returns valid JSON but without expected "data.products" key
  When collect_wb_content is called
  Then task records failure reason "PARSE_ERROR" and does not create a content_scores row

Scenario: Cross-org isolation — task only writes to correct org's data
  Given sku_platform_A belongs to org_A and sku_platform_B belongs to org_B
  When collect_wb_content runs for sku_platform_A
  Then only org_A's content_scores row is written
  And org_B's data is not affected
```

### US-W02: Price Collection

```gherkin
Scenario: Celery task collects current price
  Given sku_platform with external_id="12345678"
  When collect_wb_price task runs
  Then a price_snapshots row is inserted
  And price is a positive Decimal
  And original_price >= price (discount_pct computed correctly)
  And collected_at is within 5 seconds of now

Scenario: Product has no active discount
  Given product has no active promotion
  When collect_wb_price task runs
  Then price_snapshots row has discount_pct = 0 and promo_label = null
  And price == original_price

Scenario: WB returns 429 on price endpoint
  Given WB card API returns 429
  When collect_wb_price task runs
  Then task retries with exponential backoff (max 3 times)
  And marks failure "RATE_LIMITED"

Scenario: Price endpoint unavailable
  Given card API returns 503
  When collect_wb_price task runs
  Then task retries 3 times then marks failure "API_UNAVAILABLE"
```

### US-W03: Stock / Availability Collection

```gherkin
Scenario: Celery task collects stock availability
  Given sku_platform with external_id="12345678"
  When collect_wb_stock task runs
  Then a stock record is upserted in content_scores (in_stock flag used for distribution reporting)
  And in_stock = true if total warehouse quantity > 0

Scenario: Product is out of stock
  Given WB shows "Нет в наличии"
  When collect_wb_stock task runs
  Then in_stock = false is recorded

Scenario: SKU is not sold in any warehouse
  Given total_qty = 0 across all warehouses
  When collect_wb_stock task runs
  Then in_stock = false

Scenario: Stock API unavailable
  Given WB card API returns 503
  When collect_wb_stock task runs
  Then task retries 3 times then marks failure "API_UNAVAILABLE"
  And no stock row is written

Scenario: Stock task does not create partial content_scores row
  Given collect_wb_stock runs before collect_wb_content for today
  When stock task upserts stock data
  Then content fields (collected_description, collected_image_url) remain null
  And the row is not passed to ML scoring until content fields are populated
```

### US-W04: Review Collection

```gherkin
Scenario: Celery task collects last 50 reviews
  Given sku_platform with external_id="12345678" and 60 existing reviews on WB
  When collect_wb_reviews task runs
  Then up to 50 newest reviews are collected
  And each review row has external_review_id set (for deduplication)
  And duplicate reviews (same external_review_id) are skipped (INSERT IGNORE / ON CONFLICT DO NOTHING)
  And rating is an integer 1–5

Scenario: SKU has no reviews yet
  Given product has 0 reviews on WB
  When collect_wb_reviews task runs
  Then task completes successfully with 0 rows inserted

Scenario: Review text contains HTML
  Given review text contains "<b>Отлично!</b>"
  When reviews are collected
  Then stored review_text is "Отлично!" (HTML stripped)
```

---

## 2. Data Flow

```
Celery Beat (daily 02:00)
  └─ collect_wb_content_all()  ← orchestrator task
       └─ for each sku_platform WHERE platform="Wildberries":
            collect_wb_content.delay(sku_platform_id)
            collect_wb_stock.delay(sku_platform_id)
            collect_wb_reviews.delay(sku_platform_id)

Celery Beat (every 4h)
  └─ collect_wb_prices_all()
       └─ for each sku_platform WHERE platform="Wildberries":
            collect_wb_price.delay(sku_platform_id)
```

---

## 3. API Contracts (internal Celery tasks)

```python
collect_wb_content(sku_platform_id: str) -> None
collect_wb_price(sku_platform_id: str)   -> None
collect_wb_stock(sku_platform_id: str)   -> None
collect_wb_reviews(sku_platform_id: str) -> None

collect_wb_content_all()  -> None   # orchestrator
collect_wb_prices_all()   -> None   # orchestrator
```

---

## 4. Output Schemas (DB rows written)

### content_scores (upsert on sku_platform_id + scored_at)
```
scored_at:              today's date
collected_title:        str max 500 chars, HTML stripped
collected_image_url:    "org/{org_id}/sku/{sku_id}/wb/main.jpg" (S3 key) or null
collected_description:  str max 5000 chars, HTML stripped
collected_composition:  str max 2000 chars, HTML stripped, or null
in_stock:               bool (from stock task, default null until stock task runs)
warehouse_qty:          int (total units across all warehouses)
```

**Note:** `content_scores` row may be partially populated — content task and stock task both upsert the same row for the day. ML scoring pipeline must check that `collected_description IS NOT NULL` before scoring.

### price_snapshots (insert)
```
price:          Decimal(10,2)
original_price: Decimal(10,2)
discount_pct:   Decimal(5,2) = (original_price - price) / original_price * 100
promo_label:    str max 255 or null
collected_at:   datetime UTC
```

### reviews (insert on conflict do nothing)
```
review_text:         str max 5000 chars
rating:              1–5
review_date:         date from WB response
external_review_id:  str (WB's internal review ID)
```

---

## 5. Error Codes

| Code | Meaning |
|------|---------|
| `NO_NM_ID` | sku_platform.external_id is null — skip silently |
| `NOT_FOUND` | Product not found on WB (deleted or invalid nm_id) |
| `RATE_LIMITED` | 429 persists after max retries |
| `API_UNAVAILABLE` | 503/connection error after max retries |
| `PARSE_ERROR` | Unexpected response structure |
