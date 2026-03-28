# Specification — Самокат Scraper

**Feature:** Самокат Scraper
**SPARC Phase:** Specification

---

## 1. User Stories

### US-1: Content Collection
```
As a CAT collector worker,
I want to fetch product title, description, composition, and image from Самокат by product_id,
So that the content_scores table has up-to-date collected fields for FMCG brands.

Acceptance Criteria:
Given a sku_platform row with platform.name = "Samocat" and a valid external_id,
When collect_samocat_content(sku_platform_id) is called,
Then content_scores is upserted with collected_title, collected_description,
     collected_composition, and collected_image_url (S3 key or None),
     scored_at = today() UTC,
     no exception propagated for NOT_FOUND products.
```

### US-2: Price Collection
```
As a CAT collector worker,
I want to fetch the current and original price from Самокат by product_id,
So that price_snapshots has a daily record for trend analysis.

Acceptance Criteria:
Given a valid sku_platform row for Самокат,
When collect_samocat_price(sku_platform_id) is called,
Then a new row is inserted into price_snapshots with price, original_price,
     discount_pct, and promo_label (nullable).
```

### US-3: Stock Collection
```
As a CAT collector worker,
I want to fetch in_stock flag and available quantity from Самокат by product_id,
So that distribution monitoring reflects actual darkstore availability.

Acceptance Criteria:
Given a valid sku_platform row for Самокат,
When collect_samocat_stock(sku_platform_id) is called,
Then stock_snapshots / content_scores is upserted with in_stock and total_qty.
```

### US-4: Reviews Collection
```
As a CAT collector worker,
I want to fetch the last 50 reviews from Самокат by product_id,
So that sentiment analysis has fresh review data.

Acceptance Criteria:
Given a valid sku_platform row for Самокат,
When collect_samocat_reviews(sku_platform_id) is called,
Then up to 50 reviews are upserted into the reviews table,
     deduplicated by (sku_platform_id, external_review_id).
```

### US-5: Cross-Tenant Isolation
```
As the CAT multi-tenant system,
I want every Самокат scraper DB write to be scoped to the correct org_id,
So that org_A's SKU data never contaminates org_B's records.

Acceptance Criteria:
Given sku_platforms for org_A and org_B with the same product_id,
When collect_samocat_content(sp_a_id) is called,
Then only org_A's sku_platform_id appears in the upserted content_scores row.
```

### US-6: Retry on Transient Errors
```
As a CAT operator,
I want the scraper to retry on 429 and 5xx responses with exponential backoff,
So that transient rate limits don't produce permanent failures.

Acceptance Criteria:
Given an API response of 429 or 503,
When the scraper receives it,
Then it retries up to 3 times with countdown = 2^attempt seconds,
     and raises ScraperError("RATE_LIMITED") or ScraperError("API_UNAVAILABLE")
     after max retries.
```

---

## 2. Acceptance Criteria (Non-Functional)

| Criterion | Value |
|-----------|-------|
| Rate limit | ≤ 2.0 req/sec (via `rate_limit = 2.0` in SamokatScraper) |
| Max retries | 3 |
| Image SSRF allowlist | `^https://cdn\.samokat\.ru/` |
| Text sanitization | All scraped text through `sanitize()` (5000 char limit) |
| No secrets in code | `PROXY_LIST_URL` from env only |
| Default city | X-City-Id: 1 (Москва) — not configurable per request |
| Logging | `logger.info/warning` — no `print()`, no raw user data in logs |

---

## 3. Feature Matrix

| Feature | MVP (Sprint 2) | v2 |
|---------|---------------|-----|
| Content scraping | ✅ | — |
| Price scraping | ✅ | — |
| Stock scraping | ✅ | — |
| Reviews scraping | ✅ | — |
| Multi-city support | ❌ | ✅ |
| Playwright fallback | ❌ | ✅ |
| Seller Partner API | ❌ | ✅ |

---

## 4. Data Schema (existing tables, no migration needed)

All Самокат data writes to the same tables as WB/Ozon:

```
content_scores (sku_platform_id, scored_at) — UNIQUE constraint
price_snapshots (sku_platform_id, collected_at) — append-only
reviews (sku_platform_id, external_review_id) — UNIQUE constraint
```

No new migration required — platform row `{name: "Samocat"}` must exist in `platforms` table.

---

## 5. Error Taxonomy

| Error Code | Condition | Task Behaviour |
|------------|-----------|---------------|
| `NO_PRODUCT_ID` | external_id is None or empty | Silent skip, no DB write |
| `PARSE_ERROR` | product_id not numeric | Log warning, return |
| `NOT_FOUND` | HTTP 404 — product delisted | Log info, return |
| `RATE_LIMITED` | 429 after 3 retries | `self.retry()` exhausted → propagate |
| `API_UNAVAILABLE` | 5xx / timeout after 3 retries | `self.retry()` exhausted → propagate |

---

## 6. File Structure

```
services/collector/app/
├── scrapers/
│   └── samocat.py            ← SamokatScraper + data parsing + image download
├── tasks/
│   ├── samocat_content_task.py
│   ├── samocat_price_task.py
│   ├── samocat_stock_task.py
│   ├── samocat_reviews_task.py
│   └── samocat_orchestrator.py
└── tests/
    └── test_samocat_tasks.py
```

`celery_app.py` — добавить все 5 задач в `include` list.
