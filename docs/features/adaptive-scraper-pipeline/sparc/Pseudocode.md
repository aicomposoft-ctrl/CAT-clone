# Pseudocode — Adaptive Scraper Pipeline

---

## 1. ScraperRouter

```python
# services/collector/app/core/scraper_router.py

class ScraperRouter:
    def __init__(self, db: AsyncSession, redis: Redis):
        self._db = db
        self._redis = redis

    async def collect(
        self,
        platform_id: UUID,
        sku_id: str,
        data_type: DataType,
        org_id: UUID,
    ) -> ScrapedData:

        platform = await self._get_platform(platform_id, org_id)  # org_id filter!
        chain = self._build_chain(platform)

        last_error = None
        for scraper in chain:
            try:
                result = await scraper.collect(sku_id, data_type)
                result.scraper_level = scraper.scraper_level  # audit field
                logger.info(
                    "scraper_success",
                    platform=platform.name,
                    level=scraper.scraper_level,
                    sku_id=sku_id,
                )
                return result
            except ScraperError as e:
                last_error = e
                logger.warning(
                    "scraper_fallback",
                    platform=platform.name,
                    level=scraper.scraper_level,
                    error_code=e.code,
                )
                if e.code == "TOKEN_INVALID":
                    await self._notify_token_expired(platform, org_id)
                if e.code not in ("TOKEN_INVALID", "API_UNAVAILABLE", "RATE_LIMITED", "ANTIBOT_BLOCK"):
                    raise  # не пробуем следующий уровень для непредвиденных ошибок

        raise ScraperError("ALL_LEVELS_FAILED", str(last_error))

    def _build_chain(self, platform: Platform) -> list[BaseScraper]:
        chain_spec = platform.fallback_chain or self._default_chain(platform)
        scrapers = []
        for level in chain_spec:
            scraper = self._instantiate(level, platform)
            if scraper:
                scrapers.append(scraper)
        return scrapers

    def _default_chain(self, platform: Platform) -> list[str]:
        if platform.api_token_encrypted:
            return ["l0", "l2"]
        return ["l1", "l2"]

    def _instantiate(self, level: str, platform: Platform):
        if level == "l0" and platform.api_token_encrypted:
            token = decrypt_token(platform.api_token_encrypted)
            return L0_REGISTRY[platform.api_token_type](token)
        if level == "l1":
            return L1_REGISTRY[platform.name]()
        if level == "l2":
            return PlaywrightScraper(platform)
        if level == "l3":
            return AgentScraper(platform, self._redis)
        return None
```

---

## 2. WBSellerAPIScraper (L0)

```python
# services/collector/app/scrapers/seller_api/wb_seller.py

class WBSellerAPIScraper(BaseScraper):
    scraper_level = 0
    rate_limit = 5.0  # официальный API более щедрый

    _CARDS_LIST = "https://content-api.wildberries.ru/content/v2/get/cards/list"
    _PRICES     = "https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter"

    def __init__(self, token: str):
        self._token = token
        self._headers = {"Authorization": f"Bearer {token}"}

    async def collect(self, nm_id: str, data_type: DataType) -> ScrapedData:
        if data_type == DataType.CONTENT:
            return await self._collect_content(nm_id)
        elif data_type == DataType.PRICE:
            return await self._collect_price(nm_id)
        elif data_type == DataType.STOCK:
            return await self._collect_stock(nm_id)
        elif data_type == DataType.REVIEWS:
            return await self._collect_reviews(nm_id)

    async def _collect_content(self, nm_id: str) -> ContentData:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                self._CARDS_LIST,
                headers=self._headers,
                json={
                    "settings": {
                        "cursor": {"limit": 1},
                        "filter": {"nmIDs": [int(nm_id)]},
                    }
                },
            )
            if resp.status_code == 401:
                raise ScraperError("TOKEN_INVALID", "WB Seller API: 401")
            resp.raise_for_status()

            cards = resp.json().get("cards", [])
            if not cards:
                raise ScraperError("SKU_NOT_FOUND", f"nm_id={nm_id}")

            card = cards[0]
            return ContentData(
                title=sanitize(card.get("title", ""), 500),
                description=sanitize(self._extract_description(card), 5000),
                composition=sanitize(self._extract_composition(card), 2000),
                image_url=self._extract_image_url(card),
            )

    def _extract_description(self, card: dict) -> str:
        for char in card.get("characteristics", []):
            if char.get("id") == 97827:  # WB ID для "Описание"
                return char.get("value", [""])[0]
        return ""

    def _extract_image_url(self, card: dict) -> str | None:
        photos = card.get("photos", [])
        if photos:
            # WB возвращает список фото, берём первое в максимальном разрешении
            return photos[0].get("big", photos[0].get("c246x328"))
        return None
```

---

## 3. PlaywrightScraper (L2)

```python
# services/collector/app/scrapers/playwright_scraper.py

class PlaywrightScraper(BaseScraper):
    scraper_level = 2
    rate_limit = 0.5  # 1 запрос каждые 2 сек

    def __init__(self, platform: Platform, browser_pool: BrowserPool):
        self._platform = platform
        self._pool = browser_pool
        self._selectors = platform.selectors or {}

    async def collect(self, url: str, data_type: DataType) -> ScrapedData:
        async with self._pool.acquire() as page:
            intercepted: list[dict] = []

            async def on_response(response):
                ct = response.headers.get("content-type", "")
                if "application/json" in ct and response.status == 200:
                    try:
                        body = await response.json()
                        intercepted.append({"url": response.url, "body": body})
                    except Exception:
                        pass

            page.on("response", on_response)

            try:
                await page.goto(url, wait_until="networkidle", timeout=30_000)
            except TimeoutError:
                await self._save_screenshot(page, url)
                raise ScraperError("PAGE_TIMEOUT", url)

            # Попытка 1: извлечь из перехваченных JSON
            result = self._parse_intercepted(intercepted, data_type)
            if result:
                return result

            # Попытка 2: CSS-селекторы из конфигурации
            result = await self._parse_dom(page, data_type)
            if result:
                return result

            raise ScraperError("EXTRACTION_FAILED", f"No data found for {url}")

    def _parse_intercepted(self, responses: list[dict], data_type: DataType):
        """Ищет в перехваченных ответах структуры похожие на нужный тип данных."""
        for resp in responses:
            body = resp["body"]
            if data_type == DataType.PRICE:
                price = self._try_extract_price(body)
                if price:
                    return price
        return None

    async def _parse_dom(self, page, data_type: DataType):
        if data_type == DataType.CONTENT:
            title_sel = self._selectors.get("title")
            price_sel = self._selectors.get("price")
            if title_sel:
                title = await page.text_content(title_sel, timeout=5000)
                return ContentData(title=sanitize(title, 500), ...)
        return None

    async def _save_screenshot(self, page, url: str):
        """Сохраняет скриншот в MinIO для дебага."""
        try:
            screenshot = await page.screenshot(full_page=True)
            key = f"debug/{self._platform.name}/{date.today()}/{uuid4()}.png"
            await minio_client.put_object("cat-debug", key, screenshot)
        except Exception as e:
            logger.warning("screenshot_failed", error=str(e))
```

---

## 4. AgentScraper (L3)

```python
# services/collector/app/scrapers/agent_scraper.py

EXTRACTION_PROMPTS = {
    DataType.CONTENT: """
        Из этого accessibility tree HTML страницы извлеки данные о товаре.
        Верни JSON строго в формате:
        {"title": "...", "description": "...", "composition": "...", "image_url": "..."}
        Если поле отсутствует — null. Только JSON, без пояснений.
    """,
    DataType.PRICE: """
        Из этого accessibility tree найди цену товара.
        Верни JSON: {"price": 999.99, "original_price": 1199.99, "discount_pct": 16.7, "promo_label": "..."}
        Цены в рублях как числа. Только JSON.
    """,
    DataType.STOCK: """
        Из этого accessibility tree определи наличие товара.
        Верни JSON: {"in_stock": true/false, "total_qty": 0}
        total_qty если явно указано количество, иначе 0. Только JSON.
    """,
}

class AgentScraper(BaseScraper):
    scraper_level = 3
    rate_limit = 0.2  # 1 запрос каждые 5 сек (Claude API стоит денег)

    def __init__(self, platform: Platform, redis: Redis):
        self._platform = platform
        self._redis = redis
        self._claude = anthropic.AsyncAnthropic()

    async def collect(self, url: str, data_type: DataType) -> ScrapedData:
        async with PlaywrightContext() as page:
            await page.goto(url, wait_until="networkidle", timeout=30_000)

            # Accessibility tree snapshot
            snapshot = await page.accessibility.snapshot(interesting_only=True)
            snapshot_text = self._flatten_snapshot(snapshot)

            # Claude extraction
            prompt = EXTRACTION_PROMPTS[data_type]
            cache_key = f"agent_result:{self._platform.id}:{hash(url)}:{data_type}"

            # Проверяем кеш
            cached = await self._redis.get(cache_key)
            if cached:
                return self._deserialize(cached, data_type)

            response = await self._claude.messages.create(
                model="claude-haiku-4-5-20251001",  # быстро и дёшево
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": f"{prompt}\n\nACCESSIBILITY TREE:\n{snapshot_text[:8000]}"
                }],
            )

            raw_json = response.content[0].text.strip()
            result = self._validate_and_parse(raw_json, data_type)

            # Кешируем на 1 час
            await self._redis.set(cache_key, raw_json, ex=3600)
            return result

    def _flatten_snapshot(self, node: dict, depth: int = 0) -> str:
        """Конвертирует accessibility tree в читаемый текст."""
        lines = []
        role = node.get("role", "")
        name = node.get("name", "")
        value = node.get("value", "")
        if name or value:
            lines.append(f"{'  ' * depth}{role}: {name or value}")
        for child in node.get("children", []):
            lines.extend(self._flatten_snapshot(child, depth + 1).split("\n"))
        return "\n".join(lines)

    def _validate_and_parse(self, raw_json: str, data_type: DataType) -> ScrapedData:
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            raise ScraperError("AGENT_EXTRACTION_FAILED", f"Invalid JSON: {raw_json[:200]}")

        if data_type == DataType.CONTENT:
            return ContentData(**{k: data.get(k) for k in ContentData.__dataclass_fields__})
        elif data_type == DataType.PRICE:
            return PriceData(**{k: data.get(k) for k in PriceData.__dataclass_fields__})
        # ...
```

---

## 5. Alembic Migration 0014

```python
# infrastructure/postgres/migrations/0014_adaptive_scraper_platform_fields.py

revision = "0014"
down_revision = "0013"

def upgrade() -> None:
    op.add_column("platforms", sa.Column("scraper_mode",
        sa.String(20), nullable=False, server_default="auto"))
    op.add_column("platforms", sa.Column("api_token_encrypted",
        sa.Text(), nullable=True))
    op.add_column("platforms", sa.Column("api_token_type",
        sa.String(20), nullable=True))
    op.add_column("platforms", sa.Column("fallback_chain",
        postgresql.JSONB(), nullable=True))
    op.add_column("platforms", sa.Column("selectors",
        postgresql.JSONB(), nullable=True))

    # Аудит-поле в content_scores
    op.add_column("content_scores", sa.Column("scraper_level",
        sa.SmallInteger(), nullable=True))
    op.add_column("price_snapshots", sa.Column("scraper_level",
        sa.SmallInteger(), nullable=True))

def downgrade() -> None:
    for col in ["scraper_mode", "api_token_encrypted", "api_token_type",
                "fallback_chain", "selectors"]:
        op.drop_column("platforms", col)
    op.drop_column("content_scores", "scraper_level")
    op.drop_column("price_snapshots", "scraper_level")
```
