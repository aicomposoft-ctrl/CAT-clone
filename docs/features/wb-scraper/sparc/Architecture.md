# Architecture — Wildberries Scraper

**SPARC Phase 5: Architecture** | Feature: wb-scraper

---

## 1. Component Overview

```
services/collector/
├── app/
│   ├── celery_app.py            # Celery app + Redis broker config
│   ├── core/
│   │   ├── base_scraper.py      # BaseScraper ABC
│   │   ├── proxy.py             # ProxyRotator
│   │   └── sanitize.py          # HTML strip + length truncation
│   ├── scrapers/
│   │   └── wildberries.py       # WildberriesScraper
│   └── tasks/
│       ├── wb_content_task.py   # collect_wb_content Celery task
│       ├── wb_price_task.py     # collect_wb_price Celery task
│       ├── wb_stock_task.py     # collect_wb_stock Celery task
│       ├── wb_reviews_task.py   # collect_wb_reviews Celery task
│       └── wb_orchestrator.py   # collect_wb_content_all + collect_wb_prices_all
```

---

## 2. BaseScraper ABC

```python
# services/collector/app/core/base_scraper.py

class BaseScraper(ABC):
    platform: str          # "Wildberries"
    rate_limit: float      # requests per second

    def __init__(self, proxy_rotator: ProxyRotator):
        self._proxy = proxy_rotator
        self._semaphore = asyncio.Semaphore(int(rate_limit))

    @abstractmethod
    async def collect_content(self, nm_id: str) -> ContentData: ...

    @abstractmethod
    async def collect_price(self, nm_id: str) -> PriceData: ...

    @abstractmethod
    async def collect_stock(self, nm_id: str) -> StockData: ...

    @abstractmethod
    async def collect_reviews(self, nm_id: str, take: int = 50) -> list[ReviewData]: ...

    async def _get(self, url: str, **kwargs) -> httpx.Response:
        """Async HTTP GET with rate limiting, proxy, retry."""
        async with self._semaphore:
            await asyncio.sleep(1 / self.rate_limit)
            proxy = self._proxy.next()
            return await self._client.get(url, proxy=proxy, **kwargs)

    async def with_retry(self, coro, max_retries=3):
        for attempt in range(max_retries):
            try:
                return await coro()
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)
```

---

## 3. WildberriesScraper

```python
# services/collector/app/scrapers/wildberries.py

class WildberriesScraper(BaseScraper):
    platform = "Wildberries"
    rate_limit = 1.0  # req/sec

    CARD_API = "https://card.wb.ru/cards/v2/detail"
    REVIEWS_API = "https://feedbacks2.wb.ru/feedbacks/v1/{nm_id}"
    IMAGE_CDN = "https://basket-{basket:02d}.wbbasket.ru/vol{vol}/part{part}/{nm_id}/images/big/1.jpg"

    async def collect_content(self, nm_id: str) -> ContentData:
        """Fetch product card via WB card API. Falls back to Playwright if API fails."""
        async def _fetch():
            resp = await self._get(
                self.CARD_API,
                params={"appType": "1", "curr": "rub", "dest": "-1257786", "nm": nm_id},
            )
            resp.raise_for_status()
            return resp.json()

        data = await self.with_retry(_fetch)
        product = _extract_product(data, nm_id)
        return ContentData(
            title=sanitize(product.get("name", ""), max_len=500),
            description=sanitize(product.get("description", ""), max_len=5000),
            composition=sanitize(product.get("composition", ""), max_len=2000) or None,
            image_url=_build_image_url(nm_id, product),
        )

    async def collect_price(self, nm_id: str) -> PriceData:
        async def _fetch():
            resp = await self._get(
                self.CARD_API,
                params={"appType": "1", "curr": "rub", "dest": "-1257786", "nm": nm_id},
            )
            resp.raise_for_status()
            return resp.json()

        data = await self.with_retry(_fetch)
        product = _extract_product(data, nm_id)
        sizes = product.get("sizes", [{}])
        price_info = sizes[0].get("price", {}) if sizes else {}

        price = Decimal(str(price_info.get("product", 0))) / 100  # WB prices in kopeks × 100
        original = Decimal(str(price_info.get("basic", price_info.get("product", 0)))) / 100
        discount = (original - price) / original * 100 if original > 0 else Decimal(0)

        return PriceData(
            price=price,
            original_price=original,
            discount_pct=discount.quantize(Decimal("0.01")),
            promo_label=product.get("promoTextCard") or None,
        )

    async def collect_stock(self, nm_id: str) -> StockData:
        async def _fetch():
            resp = await self._get(
                self.CARD_API,
                params={"appType": "1", "curr": "rub", "dest": "-1257786", "nm": nm_id},
            )
            resp.raise_for_status()
            return resp.json()

        data = await self.with_retry(_fetch)
        product = _extract_product(data, nm_id)
        total_qty = sum(
            stock.get("qty", 0)
            for size in product.get("sizes", [])
            for stock in size.get("stocks", [])
        )
        return StockData(in_stock=total_qty > 0, total_qty=total_qty)

    async def collect_reviews(self, nm_id: str, take: int = 50) -> list[ReviewData]:
        async def _fetch():
            resp = await self._get(
                self.REVIEWS_API.format(nm_id=nm_id),
                params={"take": take, "skip": 0, "order": "dateDesc"},
            )
            resp.raise_for_status()
            return resp.json()

        data = await self.with_retry(_fetch)
        feedbacks = data.get("feedbacks", [])
        return [
            ReviewData(
                external_review_id=str(fb["id"]),
                review_text=sanitize(fb.get("text", ""), max_len=5000),
                rating=int(fb.get("productValuation", 5)),
                review_date=date.fromisoformat(fb["createdDate"][:10]),
            )
            for fb in feedbacks
        ]
```

---

## 4. Data Classes

```python
@dataclass
class ContentData:
    title: str
    description: str
    composition: str | None
    image_url: str | None  # CDN URL to download

@dataclass
class PriceData:
    price: Decimal
    original_price: Decimal
    discount_pct: Decimal
    promo_label: str | None

@dataclass
class StockData:
    in_stock: bool
    total_qty: int

@dataclass
class ReviewData:
    external_review_id: str
    review_text: str
    rating: int
    review_date: date
```

---

## 5. Celery Task Design

```python
# collect_wb_content_task.py

@celery_app.task(bind=True, max_retries=3, name="wb.collect_content")
def collect_wb_content(self, sku_platform_id: str):
    # 1. Load sku_platform from DB (sync SQLAlchemy in Celery worker)
    # 2. Validate external_id (nm_id); raise SkipTask if None
    # 3. Instantiate WildberriesScraper
    # 4. Call scraper.collect_content(nm_id) in asyncio.run()
    # 5. If ContentData.image_url: download image → upload to MinIO → store S3 key
    # 6. Upsert content_scores row
    # Retry on httpx errors with countdown=2**retries
```

---

## 6. Proxy Rotation

```python
class ProxyRotator:
    def __init__(self, proxy_list: list[str]):
        self._proxies = proxy_list
        self._idx = 0

    def next(self) -> str | None:
        if not self._proxies:
            return None
        proxy = self._proxies[self._idx % len(self._proxies)]
        self._idx += 1
        return proxy

    @classmethod
    def from_env(cls) -> "ProxyRotator":
        url = os.environ.get("PROXY_LIST_URL")
        if not url:
            return cls([])
        proxies = requests.get(url).text.strip().splitlines()
        return cls(proxies)
```

---

## 7. DB Access in Celery

Celery workers use **synchronous** SQLAlchemy sessions (not async). FastAPI API uses async sessions. These are separate session factories.

```python
# collector uses: create_engine(POSTGRES_URL.replace("+asyncpg", ""))
# API uses:       create_async_engine(POSTGRES_URL)
```

---

## 8. New Files / No Migration

No new DB tables. Writes go to existing tables:
- `content_scores` — created in migration 0003 (separate feature)
- `price_snapshots` — created in migration 0003
- `reviews` — created in migration 0003

For this sprint: scraper implementation + tasks only. Migration for content/price/review tables is migration 0003 (tracked separately).
