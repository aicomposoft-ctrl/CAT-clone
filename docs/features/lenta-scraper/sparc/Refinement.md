# Refinement: Lenta Scraper

## Edge Cases Matrix

| Scenario | Input | Expected | Handling |
|----------|-------|----------|----------|
| `external_id` is None | `product_id=None` | Silent skip, no DB write | `ValueError("NO_PRODUCT_ID")` in `_parse_product_id` |
| `external_id` is empty string | `product_id=""` | Silent skip | Same |
| `external_id` non-numeric | `product_id="moloko-2%"` | Log warning, return | `ScraperError("PARSE_ERROR")` |
| Product deleted from Lenta | HTTP 404 | Log info, return | `ScraperError("NOT_FOUND")` |
| Rate limited by Lenta API | HTTP 429 | Retry ×3, exponential backoff | `with_retry()` → `ScraperError("RATE_LIMITED")` |
| Lenta API 503 | HTTP 503 | Retry ×3 | `resp.raise_for_status()` → `with_retry()` |
| Price field missing in JSON | No `"price"` key | Raise PARSE_ERROR | `KeyError` caught → `ScraperError("PARSE_ERROR")` |
| `discountPercent` is null | `"discountPercent": null` | `discount_pct = Decimal("0")` | `TypeError` caught → default |
| `availableQuantity` is string | `"availableQuantity": "много"` | `total_qty = 0` | `ValueError` caught → 0 |
| Image URL not on lenta.com CDN | `http://evil.com/img.jpg` | `image_url = None`, logged | `_LT_IMAGE_CDN_RE.match()` → discard |
| Image uses HTTP not HTTPS | `http://lenta.com/images/x.jpg` | Rejected | Regex anchored on `https://` |
| Image download fails | Network error | `s3_key = None`, content upsert proceeds | `except Exception` non-fatal |
| MinIO unreachable | `minio.upload()` raises | `s3_key = None`, content upsert proceeds | `except Exception` + `exc_info=True` |
| Reviews endpoint returns 404 | HTTP 404 | Return `[]` | Sentinel None → `[]` |
| Review has no `id` field | `{"text": "ok"}` | Skip that review | `if not external_id: continue` |
| `external_review_id` very long | `"id": "a" * 10000` | Capped at 200 chars | `[:200].strip()` |
| `sku_platform_id` not in DB | Stale Celery task | Log warning, return | `if row is None: return` |
| Two tasks run concurrently | Same `(sp_id, date)` | No duplicate rows | `ON CONFLICT DO UPDATE` |
| Stock task runs after content | Same row exists | Only stock fields overwritten | Partial-row: content fields absent from `set_` |
| Midnight boundary crossing | `scored_at` derived from `now_utc` | Consistent date | `now_utc` captured once, both `scored_at` and `created_at` use same value |

## Testing Strategy

### Unit tests (no real HTTP, no real DB)

All Celery tasks tested with:
- `patch("...asyncio.run", ...)` — controls scraper return value or exception
- `patch("...get_db_session", side_effect=factory)` — two-session pattern
- `patch("...SamokatScraper")` / `patch("...LentaScraper")` — scraper construction
- `patch("...pg_insert")` / `db.add.assert_called_once()` — DB write verification

Coverage targets: ≥ 85 % lines, 100 % error branches.

### Required test scenarios

#### lenta_content_task
1. Happy path: content + image fetched, DB upserted once
2. s3_key format: `org/{org_id}/sku/{sku_id}/lenta/main.jpg`
3. NOT_FOUND: no DB write
4. RATE_LIMITED: self.retry() called, no DB write
5. API_UNAVAILABLE: self.retry() called, no DB write
6. NO_PRODUCT_ID: silent skip, no DB write
7. PARSE_ERROR: log warning, no DB write
8. SSRF image URL: s3_key=None, upsert proceeds
9. Image download failure: s3_key=None, upsert proceeds
10. MinIO upload failure: s3_key=None, upsert proceeds, exc_info logged
11. image_url=None: s3_key=None, upsert proceeds
12. Cross-tenant isolation: sp_a_id written, not sp_b_id
13. Stale sp_id not in DB: warning logged, no crash

#### lenta_price_task
14. Happy path: PriceSnapshot added
15. Kopeks conversion: 15990 → Decimal("159.90")
16. discountPercent absent → Decimal("0")
17. NOT_FOUND: no DB write
18. RATE_LIMITED: self.retry(), no DB write
19. API_UNAVAILABLE: self.retry(), no DB write
20. NO_PRODUCT_ID: skip
21. PARSE_ERROR: skip
22. Cross-tenant isolation
23. Stale sp_id: skip

#### lenta_stock_task
24. Happy path: in_stock=True, warehouse_qty=120
25. Out of stock: in_stock=False, warehouse_qty=0
26. Non-integer availableQuantity: warehouse_qty=0
27. NOT_FOUND: no DB write
28. RATE_LIMITED: self.retry(), no DB write
29. API_UNAVAILABLE: self.retry(), no DB write
30. NO_PRODUCT_ID: skip
31. PARSE_ERROR: skip
32. **Partial-row contract**: `set_` contains ONLY `in_stock` and `warehouse_qty`; `collected_title`, `collected_description`, `collected_composition`, `collected_image_url` absent
33. Cross-tenant isolation
34. Stale sp_id: skip

#### lenta_reviews_task
35. Happy path: 2 reviews upserted
36. ON CONFLICT DO UPDATE (deduplication)
37. Constraint name: `uq_reviews_sp_ext_id`
38. Single bulk execute (not N+1)
39. Empty reviews list: no DB write
40. NOT_FOUND (404 on reviews endpoint): returns [], no DB write
41. RATE_LIMITED: self.retry(), no DB write
42. API_UNAVAILABLE: self.retry(), no DB write
43. NO_PRODUCT_ID: skip
44. PARSE_ERROR: skip
45. Cross-tenant isolation
46. Stale sp_id: skip

#### LentaScraper helpers
47. `_parse_product_id`: valid numeric string
48. `_parse_product_id`: None → ValueError
49. `_parse_product_id`: empty string → ValueError
50. `_parse_product_id`: slug → ScraperError("PARSE_ERROR")
51. SSRF regex: accepts valid `https://lenta.com/images/...jpg`
52. SSRF regex: rejects internal IP
53. SSRF regex: rejects HTTP (not HTTPS)
54. SSRF regex: rejects disallowed extension (.svg)
55. `_kopeks_to_decimal`: 15990 → Decimal("159.90")
56. `_safe_qty`: non-numeric string → 0
57. `_parse_rating`: clamp to [1,5], None defaults to 5
58. `_parse_review_date`: valid ISO, malformed fallback, None fallback

## Key Design Decisions

### Why single endpoint for content + price + stock?
Lenta's `/api/v1/products/{article_id}` returns all three data types in one
response, same as Samocat. Using a shared `_fetch_product()` method means all
three tasks share one HTTP call per product when they run concurrently — no
redundant network requests from the shared rate limiter.

### Why `asyncio.run(_fetch_content_and_image())` instead of two separate calls?
Two `asyncio.run()` calls create two event loops in the same thread. Combining
content fetch + image download into a single coroutine avoids this at the cost
of slightly more complex error handling — image download exceptions are caught
inside the coroutine and signalled by returning `None` for `image_bytes`.

### Why 1.0 req/sec not 2.0?
Lenta is a traditional brick-and-mortar retailer whose online API is not
designed for high-frequency programmatic access (unlike Samocat's purpose-built
darkstore API). 1.0 req/sec is conservative and can be raised if monitoring
shows no 429 responses.

### Why `"Lenta"` not `"lenta.com"`?
`platform` attribute must match the `Platform.name` value in the DB. The DB
was seeded with short readable names consistent across WB, Ozon, Samocat.

## Security Hardening Checklist

- [ ] `_LT_IMAGE_CDN_RE` anchors on `^https://lenta\.com/images/` (no HTTP, no other domain)
- [ ] `_download_image_async()` re-validates URL (callers must not rely on pre-validation)
- [ ] Image URL value never written to logs
- [ ] `product_id` validated with `_parse_product_id()` (numeric digits only) before URL interpolation
- [ ] All scraped text fields through `sanitize()` before DB write
- [ ] `external_review_id` capped to 200 chars and stripped before storage
- [ ] No hardcoded credentials (User-Agent is public mobile app string, not a secret)
- [ ] Proxy rotation on every HTTP call
