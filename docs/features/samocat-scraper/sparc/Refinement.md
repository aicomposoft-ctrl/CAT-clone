# Refinement — Самокат Scraper

**Feature:** Самокат Scraper
**SPARC Phase:** Refinement

---

## 1. Edge Cases Matrix

| Scenario | Input | Expected Behaviour |
|----------|-------|--------------------|
| `external_id` is None | `sku_platform.external_id = NULL` | Silent skip — `ValueError("NO_PRODUCT_ID")` |
| `external_id` is non-numeric slug | `"moloko-prostokwashino"` | Log warning, return — `ScraperError("PARSE_ERROR")` |
| Product delisted (404) | `GET /v2/items/99999 → 404` | Log info "not found", return — no DB write |
| Rate limited (429) | API returns 429 | `self.retry()` × 3 with countdown 1/2/4 sec |
| API unavailable (503) | Connection timeout | `self.retry()` × 3, propagate after exhaustion |
| `images` list is empty | `{"images": []}` | `image_url = None`, content upsert proceeds |
| Image URL fails SSRF check | `http://internal.host/img.jpg` | Log warning, `s3_key = None`, content proceeds |
| Image download fails | MinIO timeout | Log warning, `s3_key = None`, content proceeds |
| `discountPercent` is None | `{"discountPercent": null}` | `discount_pct = Decimal(0)` |
| `availableQuantity` is non-int | `{"availableQuantity": "много"}` | `total_qty = 0` (defensive cast) |
| Review `id` is absent | `{"id": null, "text": "..."}` | Skip that review |
| Review `rating` is float | `{"rating": 4.5}` | `int(4.5)` = 4, clamped to [1, 5] |
| Review `createdAt` malformed | `"2024-99-99"` | `review_date = date.today()` (fallback) |
| Concurrent content + stock tasks | Same `sku_platform_id`, same `scored_at` | ON CONFLICT DO UPDATE — idempotent |
| `sku_platform_id` not found in DB | Stale task after SKU deletion | Log warning, return — no crash |
| Cross-tenant: wrong org_id written | sp_a_id → should write org_A | Asserted in test: `values["sku_platform_id"] == sp_a_id` |

---

## 2. Testing Strategy

### Unit Tests (no DB, mocked HTTP)

```gherkin
Scenario: collect_content happy path
  Given a sku_platform with external_id = "12345"
  And Самокат API returns valid product JSON
  When collect_samocat_content(sku_platform_id) is called
  Then content_scores is upserted with correct title/description/composition
  And s3_key = "org/{org_id}/sku/{sku_id}/samocat/main.jpg"

Scenario: product not found
  Given a sku_platform with external_id = "99999"
  And Самокат API returns 404
  When collect_samocat_content(sku_platform_id) is called
  Then no DB write occurs
  And no exception is raised

Scenario: rate limited — retry
  Given a sku_platform with valid external_id
  And Самокат API returns 429 on every call
  When collect_samocat_content(sku_platform_id) is called
  Then self.retry() is called with countdown = 2**attempt
  And max_retries = 3 is respected

Scenario: NO_PRODUCT_ID — external_id is None
  Given a sku_platform with external_id = None
  When collect_samocat_content(sku_platform_id) is called
  Then the task returns silently
  And no DB write occurs

Scenario: PARSE_ERROR — non-numeric external_id
  Given a sku_platform with external_id = "abc-slug"
  When collect_samocat_content(sku_platform_id) is called
  Then the task logs a warning and returns
  And no DB write occurs

Scenario: image URL fails SSRF allowlist
  Given a product with image_url = "http://192.168.1.1/malicious.jpg"
  When collect_samocat_content is processing the image
  Then s3_key remains None
  And a warning is logged (without the URL value)

Scenario: cross-tenant isolation
  Given sku_platforms sp_a (org_A) and sp_b (org_B) with same product_id
  When collect_samocat_content(sp_a_id) is called
  Then the DB write contains sku_platform_id = sp_a_id
  And not sp_b_id

Scenario: collect_price parses kopeks correctly
  Given API returns {"price": 9900, "originalPrice": 12500, "discountPercent": 21}
  When collect_samocat_price is called
  Then price = Decimal("99.00")
  And original_price = Decimal("125.00")
  And discount_pct = Decimal("21")

Scenario: collect_reviews deduplication
  Given 50 reviews from API
  And 10 of them already exist in DB by external_review_id
  When collect_samocat_reviews is called
  Then ON CONFLICT DO UPDATE — existing rows updated, no duplicates

Scenario: collect_reviews empty list
  Given API returns {"reviews": []}
  When collect_samocat_reviews is called
  Then task returns early — no DB session opened for write
```

```gherkin
Scenario: collect_stock happy path
  Given a sku_platform with external_id = "12345"
  And Самокат API returns {"inStock": true, "availableQuantity": 48}
  When collect_samocat_stock(sku_platform_id) is called
  Then content_scores is upserted with in_stock=True and warehouse_qty=48
  And content fields (collected_title, etc.) are NOT overwritten (set_ excludes them)

Scenario: collect_stock product out of stock
  Given a sku_platform with external_id = "12345"
  And API returns {"inStock": false, "availableQuantity": 0}
  When collect_samocat_stock(sku_platform_id) is called
  Then content_scores is upserted with in_stock=False and warehouse_qty=0

Scenario: API_UNAVAILABLE — 503 after 3 retries
  Given a valid sku_platform
  And Самокат API returns 503 on every call
  When any collect_samocat_* task is called
  Then self.retry() is called up to 3 times with countdown = 2**attempt
  And ScraperError("API_UNAVAILABLE") is propagated after max retries

Scenario: cross-tenant isolation — price task
  Given sku_platforms sp_a (org_A) and sp_b (org_B) with the same product_id
  When collect_samocat_price(sp_a_id) is called
  Then the price_snapshots insert contains sku_platform_id = sp_a_id
  And not sp_b_id

Scenario: cross-tenant isolation — stock task
  Given sku_platforms sp_a (org_A) and sp_b (org_B) with the same product_id
  When collect_samocat_stock(sp_a_id) is called
  Then the content_scores upsert contains sku_platform_id = sp_a_id
  And not sp_b_id

Scenario: cross-tenant isolation — reviews task
  Given sku_platforms sp_a (org_A) and sp_b (org_B) with the same product_id
  When collect_samocat_reviews(sp_a_id) is called
  Then all review rows upserted contain sku_platform_id = sp_a_id
  And not sp_b_id

Scenario: images list is empty
  Given API returns valid product JSON with "images": []
  When collect_samocat_content processes the response
  Then collected_image_url = None
  And upsert proceeds with content fields populated

Scenario: image download failure is non-fatal
  Given API returns a valid image URL passing SSRF allowlist
  And MinIO upload raises an exception
  When collect_samocat_content processes the image
  Then collected_image_url = None
  And content_scores upsert proceeds with title/description/composition populated

Scenario: discountPercent is null
  Given API returns {"discountPercent": null, "price": 9900, "originalPrice": 9900}
  When collect_samocat_price processes the response
  Then discount_pct = Decimal("0")
  And no exception is raised

Scenario: availableQuantity is non-integer
  Given API returns {"inStock": true, "availableQuantity": "много"}
  When collect_samocat_stock processes the response
  Then warehouse_qty = 0 (defensive fallback)
  And in_stock = True

Scenario: sku_platform_id not found in DB (stale task)
  Given sku_platform_id refers to a deleted record
  When any collect_samocat_* task is called
  Then the task logs a warning and returns without error
  And no DB write occurs
```

### Coverage Targets

| Test Type | Target |
|-----------|--------|
| Unit (mocked HTTP) | ≥ 85% lines in samocat.py, ≥ 85% in task files |
| Cross-tenant isolation | 1 test per task × 4 tasks (required by testing rules) |
| Error path coverage | All 5 error codes (NO_PRODUCT_ID, PARSE_ERROR, NOT_FOUND, RATE_LIMITED, API_UNAVAILABLE) |

---

## 3. Performance

| Operation | Latency Target | Notes |
|-----------|---------------|-------|
| `collect_content` | < 20s / SKU | Single API call + image download |
| `collect_price` | < 15s / SKU | Single API call |
| `collect_stock` | < 15s / SKU | Single API call (reuses product endpoint) |
| `collect_reviews` | < 15s / SKU | Single API call |

**Optimisation note:** content, price, and stock all call the same `/v2/items/{id}` endpoint. The orchestrator could fetch once and fan out — but for Sprint 2 keep 4 independent tasks (simpler, aligned with WB/Ozon pattern). Consolidation is a v2 optimisation.

---

## 4. Security Hardening

- `_SK_IMAGE_CDN_RE` rejects any non-`cdn.samokat.ru` image URL
- `sanitize()` applied to all scraped text (title, description, composition, review text)
- `X-City-Id: 1` hardcoded — not interpolated from user input
- `product_id` validated as digits-only before HTTP call — prevents path traversal
- No `product_id` value written to logs — only safe `sku_platform_id` UUIDs

---

## 5. Technical Debt

| Item | Priority | Notes |
|------|----------|-------|
| Consolidate 3 calls to `/v2/items/{id}` into one per orchestration cycle | P2 | Reduces API calls by 2/3 for content+price+stock |
| Multi-city support (X-City-Id per org) | P2 | Requires new `org_settings` field |
| Playwright fallback if API starts requiring JS challenge | P3 | Unlikely for mobile API, but possible |
| Pagination for reviews (page > 1) | P2 | Current: page 1 only (50 reviews) |
