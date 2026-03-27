# Refinement — Wildberries Scraper

**SPARC Phase 6: Refinement** | Feature: wb-scraper

---

## 1. Open Questions & Decisions

### Q1: Playwright vs. HTTP API for content
**Decision:** Use WB card API (`card.wb.ru`) as primary. Fall back to Playwright only if API is unavailable or returns empty products.
**Rationale:** The card API is faster (< 500ms vs. 3-5s Playwright), more reliable, and returns structured JSON. Playwright is heavyweight and adds Docker complexity. WB's card API is undocumented but stable — used by their own mobile app.
**Risk:** WB may change card API structure. Monitored via `PARSE_ERROR` alerts.

### Q2: Sync vs. Async in Celery workers
**Decision:** Celery tasks are synchronous functions. Async scraper methods wrapped with `asyncio.run()`.
**Rationale:** Celery workers run in a threaded/forked model, not an asyncio event loop. Running `asyncio.run()` inside a task is the standard pattern for bridging sync Celery with async HTTP clients.
**Risk:** If Celery is configured with gevent/eventlet concurrency, `asyncio.run()` may fail. Default Celery prefork is safe.

### Q3: Prices in kopeks
**Decision:** WB card API returns prices as integer kopeks × 100 (i.e., divide by 100 to get rubles, then divide by 100 again = divide by 10000... actually WB returns prices multiplied by 100 in kopeks). Use `Decimal(str(value)) / 100`.
**Confirmed:** `{"product": 29900}` = 299.00 RUB. Formula: `price_rub = Decimal(str(raw)) / 100`.

### Q4: Content scores `in_stock` column
**Decision:** Add `in_stock BOOLEAN` column to `content_scores` table in migration 0003.
**Note:** Architecture doc does not have `in_stock` in `content_scores` table. Confirmed addition is needed — stock and content are collected together per day.

### Q5: Image download failure
**Decision:** Non-fatal. If image download fails, `collected_image_url = None`. Content scoring will fall back to text-only scoring (image weight drops to 0 for that SKU on that day).

---

## 2. WB API Response Structure (card.wb.ru)

```json
{
  "data": {
    "products": [{
      "id": 12345678,
      "name": "Индейка Индилайт духовая 700г",
      "description": "...",
      "composition": "Индейка 100%",
      "promoTextCard": "Новинка",
      "sizes": [{
        "price": {
          "basic": 59900,
          "product": 49900
        },
        "stocks": [
          {"wh": 507, "qty": 150},
          {"wh": 321, "qty": 0}
        ]
      }]
    }]
  }
}
```

Price formula: `price = sizes[0].price.product / 100` → 499.00 RUB

### Reviews API (feedbacks2.wb.ru)

```json
{
  "feedbacks": [{
    "id": "abc123",
    "text": "Отличный продукт!",
    "productValuation": 5,
    "createdDate": "2026-03-01T10:00:00Z"
  }]
}
```

---

## 3. Edge Cases

| Case | Handling |
|------|---------|
| `nm_id = null` | Silent skip, no error logged at ERROR level |
| Product deleted from WB | `NOT_FOUND` error, no row inserted |
| WB returns empty `products` list | `NOT_FOUND` (product removed from catalog) |
| Review with no text (only rating) | `review_text = ""` stored (valid — rating-only review) |
| Duplicate review ID on re-run | `ON CONFLICT DO NOTHING` — idempotent |
| Image CDN 403/404 | Non-fatal, `collected_image_url = None` |
| WB price = 0 (free/giveaway) | Allowed — `price = 0`, `discount_pct = 0` |
| Very long product description (> 5000 chars) | Truncated to 5000 chars by `sanitize()` |

---

## 4. Testing Strategy

| Test Type | What to Test |
|-----------|-------------|
| Unit | `sanitize()`, `_build_image_url()`, `_extract_product()`, `ProxyRotator.next()` |
| Unit | `WildberriesScraper` methods with `respx` mock of card API and reviews API |
| Unit | Price calculation: kopek-to-ruble conversion, discount_pct |
| Integration | Celery task: load sku_platform → scrape → upsert DB row (SQLite) |
| Integration | Deduplication: second run of collect_wb_reviews does not insert duplicate rows |

No live WB API calls in tests. All HTTP mocked via `respx` (httpx-compatible mock library).

---

## 5. Security Considerations

- `nm_id` is sourced from `sku_platforms.external_id` — never from user input directly in scraper context
- All scraped text sanitised before DB insert (HTML strip + length limit)
- Proxy credentials in `PROXY_LIST_URL` env var — never in code
- `User-Agent` rotation to avoid fingerprinting — list of real browser UAs
- WB image URLs constructed deterministically from `nm_id` — no SSRF risk from user input
- Collected image bytes uploaded to private MinIO bucket (not public)
