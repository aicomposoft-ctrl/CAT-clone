# Refinement — Ozon Scraper

**SPARC Phase 6: Refinement** | Feature: ozon-scraper

---

## 1. Edge Cases Matrix

| Scenario | Input | Expected Handling |
|----------|-------|-------------------|
| `external_id` is null | sku_platform.external_id = None | Return immediately, NO_ITEM_ID, no DB write |
| `external_id` is non-numeric | `"not-a-number"` | `_parse_item_id()` raises `ScraperError("PARSE_ERROR")` |
| Product delisted / 404 equivalent | webProductHeading widget absent | `ScraperError("NOT_FOUND")`, no DB write |
| API returns 429 | HTTP 429 | Retry up to 3 times, countdown=2**n, then fail with RATE_LIMITED |
| Cloudflare 403 challenge | HTTP 403 | Treat same as 429 (RATE_LIMITED), retry |
| API returns 503 | HTTP 503 | Retry up to 3 times, then fail with API_UNAVAILABLE |
| `widgetStates` is empty dict | `{}` | ScraperError("NOT_FOUND") — product page has no content |
| webPrice widget absent | no `webPrice-*` key | Return PriceData with all zeros (price info unavailable, not an error) |
| webAddToCart widget absent | no `webAddToCart-*` key | StockData(in_stock=False, total_qty=0) |
| Price string malformed | `"N/A"` or `""` | `_parse_price_str` returns `Decimal("0")` |
| Image URL not in allowlist | URL outside `ir.ozone.ru` | Log warning, set image_url=None, do NOT fetch (SSRF guard) |
| Image download fails (CDN error) | httpx.TimeoutException | Log warning, s3_key=None — non-fatal, content still saved |
| Review with empty `id` field | `{"id": ""}` | Skip that review (external_review_id required for dedup) |
| Review with invalid date | `"not-a-date"` | Skip that individual review, continue with rest |
| Review rating out of range | `score=99` or `score=-1` | Clamp to `max(1, min(5, score))` |
| Review text contains Ozon rich markup | `"<br>\n<b>text</b>"` | sanitize() strips HTML, collapses whitespace |
| Empty reviews list | `{"reviews": []}` | Return `[]`, no DB write, no error |
| Inner JSON parse failure | malformed widget value | Skip that widget silently (log at DEBUG level) |
| Ozon returns duplicate reviews | same `id` in response | `ON CONFLICT DO NOTHING` handles at DB level |
| Two tasks run concurrently for same sp_id + date | Race condition on content_scores | UNIQUE(sku_platform_id, scored_at) + upsert logic handles it |
| webDetailSKU has richContent but no description | only richContent present | Use richContent as description fallback |
| Characteristics list has no "Состав" entry | no composition found | composition=None — not an error |

---

## 2. Testing Strategy

### Unit Tests (`test_ozon_scraper.py`)

Coverage targets: ≥ 85% of `scrapers/ozon.py`

All HTTP calls mocked with `respx`.

**Required test groups:**
- `sanitize()` — shared, already tested in `test_wb_scraper.py`
- `_parse_price_str()` — formatted strings, non-breaking spaces, empty, None
- `_parse_widget_states()` — happy path, malformed inner JSON, missing widgets, empty dict
- `OzonScraper.collect_content` — happy path, NOT_FOUND, PARSE_ERROR (empty title), image URL allowlist
- `OzonScraper.collect_price` — happy path, no discount, cardPrice vs price, zero price widget
- `OzonScraper.collect_stock` — in_stock, out_of_stock, missing widget → false
- `OzonScraper.collect_reviews` — list parsed, empty, HTML stripped, rating clamped, invalid date skipped
- Retry paths: 429 → retries → success; 429 × 3 → RATE_LIMITED; 503 → API_UNAVAILABLE
- Image CDN regex: valid URL matches, external URL rejected, http (not https) rejected

**Target: ≥ 30 tests in `test_ozon_scraper.py`**

### Integration Tests (`test_ozon_tasks.py`)

Coverage targets: all 4 Celery tasks + orchestrator

All DB access mocked with `unittest.mock.patch`. No real DB or network calls.

**Required test groups:**
- `TestCollectOzonContent`: happy path (content_scores upserted), NOT_FOUND (no write), RATE_LIMITED (retry called), missing item_id (early return), cross-tenant isolation
- `TestCollectOzonPrice`: happy path (PriceSnapshot added), API_UNAVAILABLE (no write), missing item_id
- `TestCollectOzonStock`: happy path (in_stock set), out-of-stock, no DB write on error
- `TestCollectOzonReviews`: bulk insert called once, empty list (no execute), dedup via ON CONFLICT
- `TestOzonOrchestrator`: dispatches correct task count, filters inactive platforms

**Target: ≥ 20 tests in `test_ozon_tasks.py`**

---

## 3. BDD Scenarios (Gherkin)

```gherkin
Feature: Ozon Scraper — Happy Path

Scenario: Collect content for active Ozon SKU
  Given sku_platform exists with platform="Ozon" external_id="123456789"
  And Ozon composer API returns valid widgetStates with webProductHeading, webDetailSKU, webGallery
  When collect_ozon_content task executes
  Then content_scores row is upserted for today
  And collected_title contains parsed product name (HTML stripped)
  And collected_image_url contains "ozon/main.jpg"

Feature: Ozon Scraper — Error Paths

Scenario: Ozon returns 429 → retry → success
  Given Ozon composer API returns 429 twice, then 200 on third attempt
  When collect_ozon_content executes
  Then scraper retries exactly 3 times total
  And content is successfully saved on the 3rd attempt

Scenario: Ozon product delisted
  Given composer API returns 200 but widgetStates lacks webProductHeading widget
  When collect_ozon_content executes
  Then ScraperError("NOT_FOUND") is raised internally
  And no content_scores row is created

Feature: Ozon Scraper — Multi-Tenant

Scenario: Cross-tenant isolation
  Given two sku_platforms A and B belonging to different orgs
  When collect_ozon_content runs for sku_platform A
  Then DB write uses sp_a_id only
  And no write for sp_b_id occurs
```

---

## 4. Performance Considerations

| Concern | Mitigation |
|---------|------------|
| Ozon composer API is slow (~2-4s per call) | `rate_limit=0.5` paces workers; Celery distributes load |
| widgetStates parsing: iterating all keys | O(n) where n = number of widgets (~15-30); acceptable |
| Image download blocking Celery worker | `asyncio.run(_download_image_async(...))` — non-blocking |
| Bulk reviews INSERT | Single `pg_insert(...).values([...])` not N+1 loop |
| orchestrator dispatching 10k+ IDs in tight loop | Same as WB — documented as minor issue; chunking is follow-up |
| Two daily tasks (content + stock) hit same API URL | Unavoidable — separate Celery tasks, separate HTTP calls |

---

## 5. Security Hardening

| Risk | Mitigation |
|------|------------|
| SSRF via Ozon image URL | `_OZ_IMAGE_CDN_RE` allowlist; validate before any HTTP fetch |
| Ozon response contains injected content | `sanitize()` strips HTML + truncates; no eval/exec on scraped data |
| Proxy credentials in logs | `PROXY_LIST_URL` is not logged; proxy string not logged at INFO level |
| item_id injection into URL | Only numeric string passed to API; non-numeric raises PARSE_ERROR before any HTTP call |
| S3 key path traversal | `org_id` and `sku_id` are UUIDs — no path traversal possible |

---

## 6. Known Follow-up Items (non-blocking)

| # | Issue | Priority |
|---|-------|----------|
| f1 | `httpx.AsyncClient` created per request — no connection reuse (same as WB minor m1) | Follow-up |
| f2 | Per-task OzonScraper instantiation — rate limiter not shared across concurrent tasks | Follow-up |
| f3 | Ozon sometimes returns `widgetStates` under different response keys in A/B tests — monitoring needed | Follow-up |
| f4 | Playwright fallback not implemented in Sprint 2 — required for Cloudflare CAPTCHA | Follow-up |
| f5 | Reviews pagination: only page 1 fetched (up to ~20 reviews per page may be < 50) — add page 2 if count < take | Follow-up |
