# Specification — Ozon Scraper

**SPARC Phase 3: Specification** | Feature: ozon-scraper

---

## 1. User Stories

### US-O01: Content Collection

```gherkin
Feature: Ozon Scraper

Scenario: Celery task collects content for an Ozon SKU
  Given sku_platform record exists with platform="Ozon" and external_id="123456789"
  When collect_ozon_content task runs for that sku_platform
  Then a content_scores row is upserted for today's date
  And collected_title is set (max 500 chars, HTML stripped)
  And collected_description is set (max 5000 chars, HTML stripped)
  And collected_image_url is set to an S3 key (downloaded image) or null if download fails
  And collected_composition is set from characteristics if available (or null)

Scenario: SKU has no external_id set
  Given sku_platform has external_id = null
  When collect_ozon_content task runs
  Then the task returns without DB write (silent skip, NO_ITEM_ID)

Scenario: Ozon returns 429 Too Many Requests
  Given Ozon API returns 429
  When collect_ozon_content is called
  Then the task retries with exponential backoff (1s, 2s, 4s)
  And after 3 retries the task is marked as failed with "RATE_LIMITED"

Scenario: Product delisted on Ozon
  Given item_id does not exist or product is removed from sale
  When collect_ozon_content is called
  Then task logs "NOT_FOUND" and does not create a content_scores row

Scenario: Ozon composer API returns unexpected widgetStates structure
  Given API returns 200 but widgetStates lacks webProductHeading widget
  When collect_ozon_content is called
  Then task raises ScraperError("PARSE_ERROR") and does not create a content_scores row

Scenario: Cross-org isolation — task only writes to correct org's data
  Given sku_platform_A belongs to org_A and sku_platform_B belongs to org_B
  When collect_ozon_content runs for sku_platform_A
  Then only org_A's content_scores row is written
  And org_B's data is not affected

Scenario: Non-numeric external_id rejected before HTTP call
  Given sku_platform has external_id = "not-a-number"
  When collect_ozon_content task runs
  Then _parse_item_id raises ScraperError("PARSE_ERROR")
  And no HTTP request is made to Ozon
  And no content_scores row is created

Scenario: SSRF guard on image URL rejects non-Ozon CDN URLs
  Given webGallery widget returns image URL "https://evil.com/image.jpg"
  When collect_ozon_content executes
  Then the image URL fails _OZ_IMAGE_CDN_RE allowlist check
  And no HTTP request is made to fetch the image
  And content_scores row is written with collected_image_url = null

Scenario: Image CDN failure is non-fatal
  Given webGallery returns valid "https://ir.ozone.ru/..." image URL
  And CDN server returns timeout or 503
  When collect_ozon_content executes
  Then content_scores row is still written
  And collected_image_url is null (image download failure does not block content save)

Scenario: Empty widgetStates dict treated as product not found
  Given composer API returns 200 but widgetStates = {}
  When collect_ozon_content executes
  Then ScraperError("NOT_FOUND") is raised
  And no content_scores row is created
```

### US-O02: Price Collection

```gherkin
Scenario: Celery task collects current price for Ozon SKU
  Given sku_platform with external_id="123456789"
  When collect_ozon_price task runs
  Then a price_snapshots row is inserted
  And price is a positive Decimal in rubles (not kopeks — Ozon returns rubles)
  And original_price >= price (discount_pct computed correctly)
  And collected_at is within 5 seconds of now

Scenario: Product has active promo on Ozon
  Given product has cardPrice (club price) lower than standard price
  When collect_ozon_price task runs
  Then price is set to cardPrice value
  And promo_label is set (e.g. "Ozon Карта")

Scenario: Product has no active discount
  Given product.originalPrice equals product.price
  When collect_ozon_price task runs
  Then price_snapshots row has discount_pct = 0 and promo_label = null

Scenario: Price API unavailable
  Given composer API returns 503
  When collect_ozon_price task runs
  Then task retries 3 times then marks failure "API_UNAVAILABLE"
  And no price_snapshots row is written

Scenario: Cross-org isolation — price task writes only to correct org
  Given sku_platform_A belongs to org_A and sku_platform_B belongs to org_B
  When collect_ozon_price runs for sku_platform_A
  Then price_snapshots row is written with sku_platform_id = sp_a_id
  And no price_snapshots row is written for sp_b_id
```

### US-O03: Stock / Availability Collection

```gherkin
Scenario: Celery task collects stock availability
  Given sku_platform with external_id="123456789"
  And webAddToCart widget returns {"availability": 1, "count": 42}
  When collect_ozon_stock task runs
  Then a stock record is upserted in content_scores (in_stock, warehouse_qty)
  And in_stock = true (availability == 1 AND count > 0)
  And warehouse_qty = 42

Scenario: Product is out of stock — availability flag is 0
  Given webAddToCart widget returns {"availability": 0, "count": 0}
  When collect_ozon_stock task runs
  Then in_stock = false is recorded
  And warehouse_qty = 0

Scenario: Product is out of stock — count is zero despite availability=1
  Given webAddToCart widget returns {"availability": 1, "count": 0}
  When collect_ozon_stock task runs
  Then in_stock = false is recorded (count=0 overrides availability flag)
  And warehouse_qty = 0

Scenario: Stock task does not overwrite content fields
  Given collect_ozon_stock runs before collect_ozon_content for today
  When stock task upserts stock data
  Then content fields (collected_description, collected_image_url) remain null
  And the row is not passed to ML scoring until content fields are populated

Scenario: Stock API unavailable
  Given composer API returns 503
  When collect_ozon_stock task runs
  Then task retries 3 times then marks failure "API_UNAVAILABLE"
  And no stock row is written

Scenario: Cross-org isolation — stock task writes only to correct org
  Given sku_platform_A belongs to org_A and sku_platform_B belongs to org_B
  When collect_ozon_stock runs for sku_platform_A
  Then content_scores upsert uses sku_platform_id = sp_a_id
  And no content_scores row is written for sp_b_id

Scenario: webAddToCart widget absent — treat as out of stock
  Given composer API returns 200 but widgetStates has no webAddToCart-* key
  When collect_ozon_stock task runs
  Then in_stock = false and warehouse_qty = 0 are recorded
  And no error is raised (graceful degradation)
```

### US-O04: Review Collection

```gherkin
Scenario: Celery task collects last 50 reviews
  Given sku_platform with external_id="123456789" and reviews present on Ozon
  When collect_ozon_reviews task runs
  Then up to 50 newest reviews are collected
  And each review row has external_review_id set (UUID from Ozon) for deduplication
  And duplicate reviews (same external_review_id) are skipped via ON CONFLICT DO NOTHING
  And rating is an integer 1–5

Scenario: SKU has no reviews yet
  Given product has 0 reviews on Ozon
  When collect_ozon_reviews task runs
  Then task completes successfully with 0 rows inserted

Scenario: Review text contains HTML or Ozon rich markup
  Given review text contains "<br>" or markdown-like formatting
  When reviews are collected
  Then stored review_text is plain text (HTML stripped, whitespace collapsed)

Scenario: Reviews API returns Cloudflare challenge
  Given Ozon bot-protection returns 403 or Cloudflare JS challenge
  When collect_ozon_reviews is called
  Then task raises ScraperError("RATE_LIMITED") and retries up to 3 times with countdown=2**n
  And after 3 retries no reviews row is written

Scenario: Review with invalid date is individually skipped
  Given review list contains one review with unparseable publishedAt ("not-a-date")
  And one review with valid date
  When collect_ozon_reviews task runs
  Then the invalid-date review is skipped without error
  And the valid review is inserted

Scenario: Review rating out of range is clamped
  Given review list contains a review with score=99
  When collect_ozon_reviews task runs
  Then the stored rating is 5 (clamped to max(1, min(5, score)))

Scenario: Cross-org isolation — reviews task writes only to correct org
  Given sku_platform_A belongs to org_A and sku_platform_B belongs to org_B
  When collect_ozon_reviews runs for sku_platform_A
  Then reviews bulk INSERT uses sku_platform_id = sp_a_id for all rows
  And no reviews row is written for sp_b_id
```

---

## 2. Data Flow

```
Celery Beat (daily 02:00)
  └─ collect_ozon_content_all()  ← orchestrator task
       └─ for each sku_platform WHERE platform="Ozon" AND platform.is_active=True AND is_monitored=True:
            collect_ozon_content.delay(sku_platform_id)
            collect_ozon_stock.delay(sku_platform_id)
            collect_ozon_reviews.delay(sku_platform_id)

Celery Beat (every 4h)
  └─ collect_ozon_prices_all()
       └─ for each sku_platform WHERE platform="Ozon" AND platform.is_active=True AND is_monitored=True:
            collect_ozon_price.delay(sku_platform_id)
```

---

## 3. API Contracts (internal Celery tasks)

```python
collect_ozon_content(sku_platform_id: str) -> None
collect_ozon_price(sku_platform_id: str)   -> None
collect_ozon_stock(sku_platform_id: str)   -> None
collect_ozon_reviews(sku_platform_id: str) -> None

collect_ozon_content_all()  -> None   # orchestrator
collect_ozon_prices_all()   -> None   # orchestrator
```

---

## 4. Output Schemas (DB rows written)

### content_scores (upsert on sku_platform_id + scored_at)
```
scored_at:              today's date
collected_title:        str max 500 chars, HTML stripped
collected_image_url:    "org/{org_id}/sku/{sku_id}/ozon/main.jpg" (S3 key) or null
collected_description:  str max 5000 chars, HTML stripped (from description + richContent merged)
collected_composition:  str max 2000 chars from characteristics/composition, or null
in_stock:               bool (from stock task; null until stock task runs)
warehouse_qty:          int (webAddToCart.count; null until stock task runs)
```

**Partial-row contract identical to WB:** ML scoring must check `collected_description IS NOT NULL`.

### price_snapshots (insert)
```
price:          Decimal(10,2)  — in rubles (Ozon returns rubles, not kopeks)
original_price: Decimal(10,2)
discount_pct:   Decimal(5,2) = (original_price - price) / original_price * 100
promo_label:    str max 255 or null (e.g. "Ozon Карта", "Акция")
collected_at:   datetime UTC
```

### reviews (insert on conflict do nothing)
```
review_text:         str max 5000 chars, HTML stripped
rating:              1–5 (clamp if API returns out-of-range)
review_date:         date from Ozon response
external_review_id:  str (Ozon's UUID review ID)
```

---

## 5. Error Codes

| Code | Meaning |
|------|---------|
| `NO_ITEM_ID` | sku_platform.external_id is null — skip silently |
| `NOT_FOUND` | Product not found on Ozon (delisted or invalid item_id) |
| `RATE_LIMITED` | 429 or Cloudflare 403 persists after max retries |
| `API_UNAVAILABLE` | 503/connection error after max retries |
| `PARSE_ERROR` | widgetStates lacks expected widget or inner JSON invalid |

---

## 6. Widget Parsing Contract

Ozon's composer API response structure:

```json
{
  "widgetStates": {
    "webProductHeading-123456": "{\"title\": \"Product Name\", \"brand\": \"Brand\"}",
    "webPrice-123456": "{\"price\": {\"price\": \"1 299 ₽\", \"originalPrice\": \"1 999 ₽\", \"discount\": \"35%\"}}",
    "webDetailSKU-123456": "{\"description\": \"...\", \"characteristics\": [{\"name\": \"Состав\", \"values\": [\"...\"] }]}",
    "webGallery-123456": "{\"images\": [{\"url\": \"https://ir.ozone.ru/...\"}]}",
    "webAddToCart-123456": "{\"availability\": 1, \"count\": 42}",
    "webReviewList-123456": "{\"reviews\": [{\"id\": \"uuid\", \"text\": \"...\", \"score\": 5, \"publishedAt\": \"2026-03-01\"}]}"
  }
}
```

Parsing strategy:
1. Find key by prefix match (`startswith("webProductHeading-")`)
2. `json.loads()` the string value — second parse
3. Extract fields with `.get()` — never assume presence
4. Raise `ScraperError("PARSE_ERROR")` only if `webProductHeading` completely absent (product doesn't exist)
5. Other widgets absent = return None/empty (non-fatal)

Price parsing: Ozon returns prices as formatted strings like `"1 299 ₽"`. Must strip spaces, `₽`, and convert to `Decimal`.
