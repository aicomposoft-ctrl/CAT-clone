# PRD — Ozon Scraper

**Feature:** Ozon Scraper
**Priority:** P0 | **Sprint:** 2 | **Story Points:** 13
**Status:** Planning

---

## 1. Problem Statement

Ozon is Russia's second-largest marketplace (110M+ monthly visitors, 35M+ SKUs). FMCG brands on CAT need daily Ozon data to monitor content quality, pricing, stock, and reviews for their products. Without an Ozon scraper, the CAT pipeline covers only Wildberries — leaving a critical blind spot for the #2 platform.

Ozon uses a single-page application with a component-based JSON API (`composer-api.bx`). Each page component (price, title, gallery, reviews) is serialized as a nested JSON string inside `widgetStates`. Parsing requires two levels of JSON deserialization and is more fragile than WB's card API. Ozon also has aggressive bot-protection via Cloudflare and behavioral fingerprinting.

**Impact:** Without Ozon data, FMCG brands with dual-platform distribution see only half the picture. P0 for Sprint 2 — directly blocks content scoring accuracy and distribution monitoring.

---

## 2. Target Data

Per SKU × Ozon platform combination (`sku_platform` record where `platform.name = "Ozon"`):

| Data Type | Fields | Frequency |
|-----------|--------|-----------|
| Content | title, description, rich_description (HTML→plain), main image URL | Daily 02:00 |
| Price | price, original_price, discount_pct, promo_label | Every 4h |
| Stock | in_stock (bool), available_qty | Daily 02:00 |
| Reviews | review_text, rating (1-5), review_date, external_review_id | Daily 02:00 |

`external_id` on `sku_platforms` = Ozon item ID (integer string), e.g. `"123456789"`.
Item ID is visible in the product URL: `https://www.ozon.ru/product/slug-name-123456789/`.

---

## 3. Core Requirements

### Must Have (Sprint 2)
- Scrape content (title, description, main image URL) for an Ozon SKU by item_id
- Scrape current price and original price by item_id
- Scrape in_stock flag and available quantity by item_id
- Scrape last 50 reviews for an Ozon SKU by item_id
- Rate limit: ≤ 0.5 req/sec per IP (Ozon is more aggressive than WB)
- Proxy rotation support (`PROXY_LIST_URL` env var)
- Celery task integration: 4 separate tasks (content, price, stock, reviews)
- Store results in existing PostgreSQL tables (content_scores, price_snapshots, reviews)
- Retry on 429/503 with exponential backoff (max 3 retries)
- Image download to MinIO (`collected_image_url` stored as S3 key)

### Should Have
- User-agent rotation (required for Ozon — single UA triggers fingerprinting)
- Playwright fallback when composer API returns non-200 or Cloudflare challenge
- Handle "товар снят с продажи" (delisted product) gracefully

### Won't Have (this sprint)
- Ozon Seller API integration (requires per-org credentials — future feature)
- Scraping search rankings or competitors
- Handling Ozon Express vs Standard separately

---

## 4. Success Metrics

| Metric | Target |
|--------|--------|
| Success rate per daily run | ≥ 90% of SKUs collect without error |
| Price collection latency | < 30 s per SKU |
| Content collection latency | < 45 s per SKU |
| Review collection latency | < 25 s per SKU |
| Zero IP bans per week | Rate limiting + proxy rotation |

Note: 90% target (vs 95% for WB) reflects Ozon's more aggressive anti-bot posture.

---

## 5. Ozon API Endpoints Used

| Data | Method | URL Pattern |
|------|--------|-------------|
| Product page JSON (all data) | HTTP GET | `https://www.ozon.ru/api/composer-api.bx/page/json/v2?url=/product/{item_id}/` |
| Reviews page JSON | HTTP GET | `https://www.ozon.ru/api/composer-api.bx/page/json/v2?url=/product/{item_id}/reviews/?page=1` |
| Product page (Playwright fallback) | Playwright | `https://www.ozon.ru/product/{item_id}/` |
| Image CDN | HTTP GET | `https://ir.ozone.ru/s3/multimedia-{suffix}/{hash}/wc1000/{hash}.jpg` |

The composer API returns a `widgetStates` object where each key is `{widgetName}-{id}` and each value is a JSON-encoded string (i.e. parse twice).

Key widget names:
- `webProductHeading-*` → `{ title, brand }`
- `webPrice-*` → `{ price, cardPrice, originalPrice, discount }`
- `webDetailSKU-*` → `{ description, richContent (HTML) }`
- `webGallery-*` → `{ images: [{url}] }`
- `webAddToCart-*` → `{ availability, count }`
- `webReviewList-*` → `{ reviews: [{id, text, rating, date}] }`

---

## 6. Required HTTP Headers

Ozon requires realistic browser headers to avoid immediate Cloudflare blocking:

```
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36
x-o3-app-name: pdp
x-o3-app-version: 2.68.0
Accept: application/json, text/plain, */*
Accept-Language: ru-RU,ru;q=0.9
```

---

## 7. Constraints

- Rate limit: `rate_limit = 0.5` req/sec (inherited from `BaseScraper`, overridden)
- Proxy: `PROXY_LIST_URL` env var; round-robin rotation (same as WB)
- Ozon blocks datacenter IPs harder than WB — residential proxies strongly recommended
- `item_id` sourced from `sku_platforms.external_id` (numeric string, must be set before scraping)
- Scraped data untrusted: sanitise all text (strip HTML, limit lengths) using existing `sanitize()`
- Image URLs: validate against `_OZ_IMAGE_CDN_RE` allowlist before fetching (SSRF guard)
- Partial-row contract: same as WB — stock task and content task both write to `content_scores`
- No new DB tables or migrations required (reuse tables from migration 0003)
