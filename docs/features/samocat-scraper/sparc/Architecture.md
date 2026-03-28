# Architecture — Самокат Scraper

**Feature:** Самокат Scraper
**SPARC Phase:** Architecture

---

## 1. Component Design

Самокат scraper следует точно той же архитектуре, что WB и Ozon scrapers:

```
┌─────────────────────────────────────────────────────────┐
│  Celery Beat (scheduler)                                  │
│  samocat_orchestrator — triggers 4 tasks per sku_platform│
└──────────────────────┬──────────────────────────────────┘
                       │ chord / group
          ┌────────────┼────────────┬─────────────┐
          ▼            ▼            ▼             ▼
  content_task   price_task   stock_task   reviews_task
          │            │            │             │
          └────────────┴────────────┴─────────────┘
                       │
               SamokatScraper (BaseScraper)
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
  api.samokat.ru/v2/           cdn.samokat.ru
  (product data)               (image download)
          │
          ▼
  ProxyRotator → httpx.AsyncClient
```

---

## 2. SamokatScraper Class

```python
class SamokatScraper(BaseScraper):
    platform = "Samocat"
    rate_limit = 2.0  # req/sec (permissive — darkstore API)

    _BASE_API = "https://api.samokat.ru/v2"
    _CITY_ID = 1  # Москва — hardcoded, not user-configurable

    _HEADERS = {
        "User-Agent": "SamokatApp/3.5.0 (Android)",
        "Accept": "application/json",
        "X-City-Id": "1",
    }

    async def collect_content(self, product_id: str) -> ContentData
    async def collect_price(self, product_id: str) -> PriceData
    async def collect_stock(self, product_id: str) -> StockData
    async def collect_reviews(self, product_id: str, take: int = 50) -> list[ReviewData]
```

Все HTTP-запросы через `BaseScraper._get()` → rate limit + proxy + UA rotation.

---

## 3. API Response Mapping

### Product Details (`GET /v2/items/{product_id}`)

```json
{
  "id": 12345,
  "name": "Молоко «Простоквашино» 3.2% 930 мл",
  "description": "Натуральное молоко...",
  "composition": "Молоко нормализованное пастеризованное",
  "images": [{"url": "https://cdn.samokat.ru/images/12345/main.jpg"}],
  "price": 9900,       ← копейки
  "originalPrice": 12500,
  "discountPercent": 21,
  "promoLabel": "Скидка 21%",
  "inStock": true,
  "availableQuantity": 48
}
```

Field mapping:
- `price` / 100 → `PriceData.price` (Decimal)
- `originalPrice` / 100 → `PriceData.original_price`
- `discountPercent` → `PriceData.discount_pct`
- `promoLabel` → `PriceData.promo_label` (nullable)
- `inStock` → `StockData.in_stock`
- `availableQuantity` → `StockData.total_qty`
- `images[0].url` → `ContentData.image_url` (if passes SSRF allowlist)

### Reviews (`GET /v2/items/{product_id}/reviews?page=1&limit=50`)

```json
{
  "reviews": [
    {
      "id": "abc123",
      "text": "Очень вкусное молоко",
      "rating": 5,
      "createdAt": "2024-03-15T10:30:00Z"
    }
  ],
  "total": 142
}
```

---

## 4. product_id Validation

Same pattern as Ozon's `_parse_item_id`:

```python
def _parse_product_id(raw: str | None) -> str:
    """
    Validate product_id is non-empty and numeric.
    Raises ValueError("NO_PRODUCT_ID") if None/empty.
    Raises ScraperError("PARSE_ERROR") if non-numeric.
    Returns validated product_id string.
    """
    if not raw:
        raise ValueError("NO_PRODUCT_ID")
    stripped = raw.strip()
    if not stripped.isdigit():
        raise ScraperError("PARSE_ERROR", f"product_id not numeric: {stripped!r}")
    return stripped
```

---

## 5. Image SSRF Allowlist

```python
_SK_IMAGE_CDN_RE = re.compile(
    r"^https://cdn\.samokat\.ru/[A-Za-z0-9/_\-\.]+\.(jpg|jpeg|png|webp)$"
)
```

Only `cdn.samokat.ru` images allowed. Non-matching URLs logged as warning, `s3_key` stays `None`.

---

## 6. Task Architecture (per task pattern)

Each task (content/price/stock/reviews) follows identical pattern:

```
1. get_db_session() → load sku_platform primitives (sp_id, sku_id, external_id, org_id)
2. Close session (primitives extracted, no ORM objects escape)
3. _parse_product_id(external_id) → validate
4. SamokatScraper(proxy_rotator).collect_X(product_id) → data
5. Handle ScraperError codes
6. get_db_session() → upsert/insert result
```

Rationale: same two-session pattern as WB/Ozon — avoids DetachedInstanceError.

---

## 7. celery_app.py Include

```python
include=[
    ...existing WB tasks...,
    ...existing Ozon tasks...,
    "app.tasks.samocat_content_task",
    "app.tasks.samocat_price_task",
    "app.tasks.samocat_stock_task",
    "app.tasks.samocat_reviews_task",
    "app.tasks.samocat_orchestrator",
]
```

---

## 8. Dependency on Existing Infrastructure

| Component | Reused As-Is |
|-----------|-------------|
| `BaseScraper` | Inherit — rate limit, proxy, UA rotation, retry |
| `ProxyRotator` / `get_proxy_rotator()` | Direct import |
| `get_db_session()` | Direct import |
| `celery_app` | Direct import |
| `sanitize()` | Apply to all scraped text |
| `ContentScore`, `SKUPlatform`, `SKU` ORM models | Direct import |
| `pg_insert` upsert pattern | Copied from ozon tasks |

No new infrastructure needed. No new DB migration (tables exist, platform row needed in `platforms`).
