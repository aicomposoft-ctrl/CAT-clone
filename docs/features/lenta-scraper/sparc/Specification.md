# Specification: Lenta Scraper

## User Stories

### US-1: Collect Content
As the CAT collector service,
I want to fetch product title, description, composition, and image URL
from Lenta's product API for a given article ID,
so that the ML pipeline can score content quality for Lenta SKUs.

**Acceptance Criteria:**

```gherkin
Scenario: Happy path — valid article_id returns content
  Given a sku_platform row with external_id = "12345" and platform = "Lenta"
  When collect_lenta_content("12345") is called
  Then ContentData(title, description, composition, image_url) is returned
  And title is not empty

Scenario: Product not found
  Given the Lenta API returns HTTP 404 for article_id "99999"
  When collect_lenta_content("99999") is called
  Then ScraperError("NOT_FOUND") is raised
  And no DB write occurs

Scenario: API rate-limited
  Given the Lenta API returns HTTP 429
  When collect_lenta_content is called
  Then with_retry() retries up to 3 times with exponential backoff
  And ScraperError("RATE_LIMITED") is raised after retries exhausted

Scenario: Non-numeric article_id
  Given a sku_platform with external_id = "moloko-prostokvashino"
  When collect_lenta_content is called
  Then ScraperError("PARSE_ERROR") is raised before any HTTP call
  And no DB write occurs

Scenario: Image URL fails SSRF allowlist
  Given the API returns image_url = "http://192.168.1.1/malicious.jpg"
  When collect_lenta_content is called
  Then image_url is set to None in ContentData
  And the SSRF rejection is logged without the URL value
```

### US-2: Collect Price
As the CAT collector service,
I want to record current price, original price, discount, and promo label
from the Lenta product API,
so that price deviation alerts can fire when prices drift.

**Acceptance Criteria:**

```gherkin
Scenario: Happy path — price returned in kopeks
  Given the API returns { "price": 15990, "originalPrice": 19990, "discountPercent": 20 }
  When collect_lenta_price("12345") is called
  Then PriceData.price = Decimal("159.90")
  And PriceData.original_price = Decimal("199.90")
  And PriceData.discount_pct = Decimal("20.00")
  # discount_pct is taken directly from the API's discountPercent field (not computed)

Scenario: promoLabel present and absent
  Given the API returns { "price": 15990, "promoLabel": "Акция" }
  When collect_lenta_price("12345") is called
  Then PriceData.promo_label = "Акция"
  Given the API returns { "price": 15990 } with no promoLabel field
  When collect_lenta_price("12345") is called
  Then PriceData.promo_label = None

Scenario: No discount (originalPrice absent)
  Given the API returns { "price": 15990 } with no originalPrice field
  When collect_lenta_price is called
  Then PriceData.original_price = PriceData.price
  And PriceData.discount_pct = Decimal("0")

Scenario: Price fields missing
  Given the API returns JSON without a "price" key
  When collect_lenta_price is called
  Then ScraperError("PARSE_ERROR") is raised
```

### US-3: Collect Stock
As the CAT collector service,
I want to record in_stock flag and available quantity from the Lenta API,
so that distribution monitoring can detect out-of-stock events.

Stock data is written to the `content_scores` table using a partial-row
upsert — only `in_stock` and `warehouse_qty` columns are set; content fields
are never overwritten by the stock task.

```gherkin
Scenario: Product in stock
  Given the API returns { "inStock": true, "availableQuantity": 120 }
  When collect_lenta_stock("12345") is called
  Then StockData.in_stock = True
  And StockData.total_qty = 120
  And content_scores upsert sets in_stock=True, warehouse_qty=120

Scenario: availableQuantity is non-integer string
  Given the API returns { "inStock": true, "availableQuantity": "много" }
  When collect_lenta_stock is called
  Then StockData.total_qty = 0  (defensive fallback)
  And upsert still fires

Scenario: Partial-row contract — content fields NOT in ON CONFLICT set_
  When collect_lenta_stock upserts content_scores
  Then the ON CONFLICT constraint is "uq_content_scores_sp_date"
  And set_ contains only in_stock and warehouse_qty
  And collected_title, collected_description, collected_composition,
      collected_image_url are absent from set_

Scenario: Out-of-stock product
  Given the API returns { "inStock": false, "availableQuantity": 0 }
  When collect_lenta_stock("12345") is called
  Then StockData.in_stock = False
  And StockData.total_qty = 0
  And content_scores upsert fires with in_stock=False, warehouse_qty=0
```

### US-4: Collect Reviews
As the CAT collector service,
I want to fetch the most recent reviews for a Lenta product,
so that NLP sentiment analysis can run on fresh review text.

```gherkin
Scenario: Happy path — reviews returned
  Given the Lenta reviews API returns 2 reviews with id, rating, text, date
  When collect_lenta_reviews("12345") is called
  Then 2 ReviewData objects are returned

Scenario: Reviews endpoint returns 404
  Given the Lenta reviews API returns HTTP 404
  When collect_lenta_reviews is called
  Then an empty list [] is returned  (graceful degradation)

Scenario: Deduplication on re-run
  Given the same review has already been stored
  When collect_lenta_reviews runs again
  Then ON CONFLICT DO UPDATE fires on uq_reviews_sp_ext_id
  And the existing row's review_text, rating, review_date are updated
  And no duplicate row is inserted

Scenario: Bulk insert — single db.execute call for all reviews
  Given the Lenta API returns 5 reviews
  When collect_lenta_reviews runs
  Then db.execute is called exactly once with all 5 rows
  And no per-review loop executes individual INSERT statements
```

## Data Model

No schema changes. Uses existing tables:

| Table | Task | Columns written |
|-------|------|-----------------|
| `content_scores` | content task | collected_title, collected_description, collected_composition, collected_image_url |
| `content_scores` | stock task | in_stock, warehouse_qty (partial-row upsert) |
| `price_snapshots` | price task | price, original_price, discount_pct, promo_label, collected_at |
| `reviews` | reviews task | external_review_id, review_text, rating, review_date, sku_platform_id |

## Lenta API Endpoints

| Purpose | Method | URL |
|---------|--------|-----|
| Product (content + price + stock) | GET | `https://lenta.com/api/v1/products/{article_id}` |
| Reviews | GET | `https://lenta.com/api/v1/products/{article_id}/reviews?page=1&limit=50` |

**Note:** Single product endpoint returns content, price, and stock fields —
the same efficient single-endpoint design as Samocat.

## Non-Functional Requirements

- Rate limit: 1.0 req/sec (BaseScraper semaphore + sleep).
- User-Agent: `LentaApp/4.2.1 (Android)` — matches public Lenta mobile app.
- Proxy rotation mandatory — `get_proxy_rotator()`.
- Image SSRF guard: `_LT_IMAGE_CDN_RE` regex, anchored on `https://lenta.com/images/`.
- `product_id` validated as numeric string before any HTTP call.
- All scraped text fields through `sanitize()` before DB write.
- `external_review_id` length-capped to 200 chars and stripped (security policy).
- Celery tasks: `max_retries=3`, exponential backoff `countdown=2**self.request.retries`.
- Two-session DB pattern: Session 1 reads primitives, Session 2 writes.
