# Architecture — Ozon Scraper

**SPARC Phase 5: Architecture** | Feature: ozon-scraper

---

## 1. Component Overview

```
services/collector/
├── app/
│   ├── core/
│   │   ├── base_scraper.py          # BaseScraper ABC (shared, already exists)
│   │   ├── proxy.py                 # ProxyRotator (shared, already exists)
│   │   └── sanitize.py              # sanitize() (shared, already exists)
│   ├── scrapers/
│   │   ├── wildberries.py           # already exists
│   │   └── ozon.py                  # NEW: OzonScraper
│   └── tasks/
│       ├── ozon_content_task.py     # NEW: collect_ozon_content
│       ├── ozon_price_task.py       # NEW: collect_ozon_price
│       ├── ozon_stock_task.py       # NEW: collect_ozon_stock
│       ├── ozon_reviews_task.py     # NEW: collect_ozon_reviews
│       └── ozon_orchestrator.py     # NEW: collect_ozon_content_all + collect_ozon_prices_all
```

No new DB tables. No new migration. All writes go to existing tables from migration 0003.

---

## 2. OzonScraper

```python
# services/collector/app/scrapers/ozon.py

class OzonScraper(BaseScraper):
    platform = "Ozon"
    rate_limit = 0.5  # req/sec — more conservative than WB (0.5 = 1 req per 2 seconds)

    COMPOSER_API = "https://www.ozon.ru/api/composer-api.bx/page/json/v2"
    PRODUCT_URL  = "/product/{item_id}/"
    REVIEWS_URL  = "/product/{item_id}/reviews/"

    # Required headers to bypass Ozon's User-Agent filtering
    _HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "x-o3-app-name": "pdp",
        "x-o3-app-version": "2.68.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9",
    }
```

---

## 3. Composer API Parsing

Ozon uses a **double-JSON** pattern. The outer response has `widgetStates: dict[str, str]` where each value is a JSON-encoded string that must be parsed again.

```python
def _parse_widget_states(response_json: dict) -> dict[str, dict]:
    """
    Parse widgetStates: find each known widget by name prefix,
    deserialize the inner JSON string, return parsed dict keyed by widget prefix.
    """
    raw = response_json.get("widgetStates", {})
    result = {}
    for key, value in raw.items():
        for prefix in _KNOWN_WIDGETS:
            if key.startswith(prefix):
                try:
                    result[prefix] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    pass  # skip malformed widget
                break
    return result

_KNOWN_WIDGETS = [
    "webProductHeading-",
    "webPrice-",
    "webDetailSKU-",
    "webGallery-",
    "webAddToCart-",
    "webReviewList-",
]
```

---

## 4. Image URL Security

Ozon images are served from `ir.ozone.ru`. Before fetching, validate URL against allowlist:

```python
_OZ_IMAGE_CDN_RE = re.compile(
    r"^https://ir\.ozone\.ru/s3/multimedia-[a-z0-9]+/[a-f0-9]+/(?:wc\d+/)?[a-f0-9]+\.jpg$"
)
```

If URL doesn't match: log warning, set `image_url = None`, do NOT fetch (SSRF guard).

---

## 5. Price String Parsing

Ozon returns prices as locale-formatted strings (`"1 299 ₽"` with non-breaking spaces).
Must strip and convert:

```python
def _parse_price_str(s: str | None) -> Decimal:
    """Parse Ozon price string to Decimal. Returns Decimal("0") if blank."""
    if not s:
        return Decimal("0")
    # Strip currency symbol, non-breaking spaces (U+00A0), regular spaces
    cleaned = re.sub(r"[^\d.,]", "", s.replace("\xa0", "").replace(" ", ""))
    cleaned = cleaned.replace(",", ".")
    return Decimal(cleaned) if cleaned else Decimal("0")
```

---

## 6. Celery Task Design (same pattern as WB)

```python
# collect_ozon_content_task.py

@celery_app.task(bind=True, max_retries=3, name="ozon.collect_content")
def collect_ozon_content(self, sku_platform_id: str):
    # 1. Extract (sp_id, sku_id, item_id, org_id) as primitives within DB session
    # 2. Validate item_id — return if None (NO_ITEM_ID)
    # 3. Instantiate OzonScraper(proxy_rotator=get_proxy_rotator())
    # 4. asyncio.run(scraper.collect_content(item_id))
    # 5. Validate image URL against _OZ_IMAGE_CDN_RE, download async, upload to MinIO
    # 6. Upsert content_scores row in separate DB session
    # Retry on ScraperError(RATE_LIMITED / API_UNAVAILABLE) with countdown=2**retries
```

**Critical pattern (identical to WB):** All DB access uses **tuple queries** to extract primitives before session close. No ORM object survives the `with get_db_session()` boundary. Avoids `DetachedInstanceError`.

**Single retry mechanism:** Manual `self.retry()` in exception handler only — no `autoretry_for`. Consistent with WB tasks.

---

## 7. S3 Key Convention

Ozon images uploaded to:
```
org/{org_id}/sku/{sku_id}/ozon/main.jpg
```
(vs WB: `org/{org_id}/sku/{sku_id}/wb/main.jpg`)

Platform slug in path allows multi-platform reference images per SKU.

---

## 8. Orchestrator Design

```python
# ozon_orchestrator.py

_OZ_PLATFORM_NAME = "Ozon"

def _load_ozon_sku_platform_ids(db) -> list[str]:
    rows = (
        db.query(SKUPlatform.id)
        .join(Platform, Platform.id == SKUPlatform.platform_id)
        .filter(
            Platform.name == _OZ_PLATFORM_NAME,
            Platform.is_active.is_(True),
            SKUPlatform.is_monitored.is_(True),
        )
        .all()
    )
    return [str(row.id) for row in rows]
```

ID-only query — keeps memory flat at any catalog size.

---

## 9. Shared Infrastructure (no changes needed)

| Component | Status | Notes |
|-----------|--------|-------|
| `BaseScraper` | Reuse as-is | OzonScraper inherits `_get()`, `with_retry()` |
| `ProxyRotator` | Reuse as-is | `get_proxy_rotator()` singleton |
| `sanitize()` | Reuse as-is | HTML stripping + truncation |
| `get_db_session()` | Reuse as-is | Sync SQLAlchemy context manager |
| `MinioClient` | Reuse as-is | `upload()` for images |
| Migration 0003 | Reuse tables | `content_scores`, `price_snapshots`, `reviews` |

---

## 10. Differences vs WB Scraper

| Aspect | WB | Ozon |
|--------|----|----|
| External ID field | `nm_id` (numeric string) | `item_id` (numeric string) |
| Price unit | kopeks ÷ 100 | rubles (direct, string parse) |
| Rate limit | 1.0 req/sec | 0.5 req/sec |
| API style | Structured JSON (card API) | double-JSON (widgetStates) |
| Image CDN regex | `wbbasket.ru` | `ir.ozone.ru` |
| Image URL construction | deterministic formula | taken from gallery widget |
| S3 key platform slug | `wb` | `ozon` |
| Celery task prefix | `wb.*` | `ozon.*` |
| Error skip code | `NO_NM_ID` | `NO_ITEM_ID` |
