# Architecture — Adaptive Scraper Pipeline

---

## 1. Уровневая модель (L0→L3)

```
┌─────────────────────────────────────────────────────────────────┐
│                    ADAPTIVE SCRAPER PIPELINE                     │
│                                                                  │
│  SKU + Platform → ScraperRouter → выбор уровня → данные         │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  L0: Official Seller API                                  │   │
│  │  WB: dev.wildberries.ru  |  Ozon: api.ozon.ru            │   │
│  │  Требует: api_token в Platform  |  Нет anti-bot           │   │
│  └───────────────────────┬──────────────────────────────────┘   │
│          fallback ↓       │ fail (401/403)                       │
│  ┌────────────────────────▼─────────────────────────────────┐   │
│  │  L1: HTTP API / Static HTML                               │   │
│  │  httpx + proxy rotation + UA rotation                    │   │
│  │  Лента /api/v1/stores/  |  WB basket CDN (нестабильно)   │   │
│  └───────────────────────┬──────────────────────────────────┘   │
│          fallback ↓       │ fail (403/498/SPA)                   │
│  ┌────────────────────────▼─────────────────────────────────┐   │
│  │  L2: Playwright Headless Browser                          │   │
│  │  Chromium + network interception + residential proxies   │   │
│  │  Самокат, Лента auth, WB (без токена), Ozon              │   │
│  └───────────────────────┬──────────────────────────────────┘   │
│          fallback ↓       │ fail (layout change / unknown)       │
│  ┌────────────────────────▼─────────────────────────────────┐   │
│  │  L3: Playwright MCP + Claude Agent                        │   │
│  │  Accessibility tree → LLM extraction                     │   │
│  │  Новые платформы, edge cases, изменившийся layout         │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Компоненты

### ScraperRouter (новый)
```python
# services/collector/app/core/scraper_router.py
class ScraperRouter:
    """Выбирает уровень скрапинга и управляет fallback-цепочкой."""

    async def collect(
        self,
        platform: Platform,
        sku_id: str,
        data_type: DataType,  # content | price | stock | reviews
    ) -> ScrapedData:
        chain = self._build_chain(platform)
        for scraper in chain:
            try:
                return await scraper.collect(sku_id, data_type)
            except ScraperError as e:
                if e.code in ("TOKEN_INVALID", "API_UNAVAILABLE"):
                    continue  # try next level
                raise
        raise ScraperError("ALL_LEVELS_FAILED")

    def _build_chain(self, platform: Platform) -> list[BaseScraper]:
        """Возвращает цепочку скраперов по приоритету."""
        chain = []
        if platform.api_token:
            chain.append(self._get_l0_scraper(platform))
        if platform.scraper_mode in ("http", "auto"):
            chain.append(self._get_l1_scraper(platform))
        if platform.scraper_mode in ("playwright", "auto"):
            chain.append(self._get_l2_scraper(platform))
        if platform.scraper_mode == "agent":
            chain.append(self._get_l3_scraper(platform))
        return chain
```

### BaseScraper (расширение)
```python
# Новые атрибуты
class BaseScraper(ABC):
    platform: str
    rate_limit: float
    scraper_level: int  # 0, 1, 2, or 3 — NEW

    # Унифицированный интерфейс для всех уровней
    @abstractmethod
    async def collect(self, sku_id: str, data_type: DataType) -> ScrapedData: ...
```

### L0: SellerAPIScraper (новый)
```python
# services/collector/app/scrapers/seller_api/wb_seller.py
class WBSellerAPIScraper(BaseScraper):
    scraper_level = 0
    _BASE = "https://supplies-api.wildberries.ru"  # и другие эндпоинты

    async def collect(self, nm_id: str, data_type: DataType) -> ScrapedData:
        headers = {"Authorization": f"Bearer {self._token}"}
        # GET /content/v2/get/cards/list
        # Возвращает ContentData из официального ответа
```

### L2: PlaywrightScraper (новый)
```python
# services/collector/app/scrapers/playwright_scraper.py
class PlaywrightScraper(BaseScraper):
    scraper_level = 2

    async def collect(self, url: str, data_type: DataType) -> ScrapedData:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            ctx = await browser.new_context(proxy=self._proxy.next_playwright())
            page = await ctx.new_page()

            # Network interception: перехватываем API-ответы
            api_responses = []
            page.on("response", lambda r: api_responses.append(r)
                    if "application/json" in r.headers.get("content-type", "") else None)

            await page.goto(url, wait_until="networkidle")
            # Извлечение через CSS или network intercept
```

### L3: AgentScraper (новый)
```python
# services/collector/app/scrapers/agent_scraper.py
class AgentScraper(BaseScraper):
    scraper_level = 3

    async def collect(self, url: str, data_type: DataType) -> ScrapedData:
        # 1. Playwright открывает страницу
        # 2. page.locator("body").aria_snapshot() → ARIA tree (Playwright Python ≥1.41)
        #    ВНИМАНИЕ: page.accessibility.snapshot() есть только в Node.js Playwright,
        #    в Python Playwright эта API недоступна. Используем aria_snapshot().
        # 3. Снапшот оборачиваем в XML-теги для защиты от prompt injection:
        #    <accessibility_tree>...</accessibility_tree>
        # 4. Инструкции по извлечению — в system prompt (не в user message)
        # 5. Claude возвращает JSON → валидируем через Pydantic
```

### Отдельный Celery-сервис для Playwright

Playwright несовместим с Celery prefork pool (Chromium не является fork-safe). L2/L3 задачи
должны выполняться в отдельном воркере с `--pool=solo`:

```yaml
# docker-compose.yml
collector-playwright:
  image: mcr.microsoft.com/playwright/python:v1.44.0-jammy
  command: celery -A app.celery_app worker -Q playwright --pool=solo --concurrency=1
  environment:
    - PLAYWRIGHT_QUEUE=playwright
```

Основной `collector` (prefork) обрабатывает L0/L1 задачи. ScraperRouter автоматически
направляет L2/L3 задачи в очередь `playwright` через `.apply_async(queue="playwright")`.

---

## 3. Изменения в БД

### Глобальная таблица platforms (только общие настройки)
```sql
-- Добавляем только глобальный режим по умолчанию
ALTER TABLE platforms ADD COLUMN scraper_mode VARCHAR(20) DEFAULT 'auto';
-- Значения: 'auto' | 'http' | 'playwright' | 'agent'
-- api_token_encrypted НЕ хранится здесь — только в org_platform_credentials
```

### Новая таблица org_platform_credentials (per-org токены)
```sql
-- Токены хранятся per-org, а не в глобальной таблице platforms
-- Это обязательно для multi-tenant изоляции: нельзя допустить, чтобы
-- org_b использовала токен org_a через тот же platform_id
CREATE TABLE org_platform_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    platform_id UUID NOT NULL REFERENCES platforms(id) ON DELETE CASCADE,
    api_token_encrypted TEXT,          -- Fernet-зашифрован
    api_token_type VARCHAR(20),        -- 'wb_seller' | 'ozon_seller' | null
    fallback_chain JSONB,              -- ["l0","l2"] — переопределяет платформенный default
    selectors JSONB,                   -- {"price": "span.price", "title": "h1"}
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (org_id, platform_id)
);
CREATE INDEX idx_org_platform_cred_org ON org_platform_credentials(org_id);
```

```sql
-- Аудит-поле в content_scores / price_snapshots
ALTER TABLE content_scores ADD COLUMN scraper_level SMALLINT;
-- 0=seller_api, 1=http, 2=playwright, 3=agent
ALTER TABLE price_snapshots ADD COLUMN scraper_level SMALLINT;
```

---

## 4. Конфигурация платформ (пример)

```python
# Глобальная запись платформы (без токенов)
Platform(name="Wildberries", scraper_mode="auto")
Platform(name="Самокат", scraper_mode="playwright")

# Per-org credentials (токен хранится изолированно per org)
OrgPlatformCredentials(
    org_id=org_a.id,
    platform_id=WB_PLATFORM_ID,
    api_token_type="wb_seller",
    api_token_encrypted=encrypt("Bearer eyJ..."),
    fallback_chain=["l0", "l2"],  # L0 → L2, пропускаем L1 (wbaas блокирует)
)

# Org без токена — только L2
OrgPlatformCredentials(
    org_id=org_b.id,
    platform_id=WB_PLATFORM_ID,
    fallback_chain=["l2"],
)

# Новая неизвестная платформа → L3
OrgPlatformCredentials(
    org_id=org_c.id,
    platform_id=NEW_PLATFORM_ID,
    fallback_chain=["l3"],
)
```

---

## 5. Безопасность токенов

- API-токены хранятся **зашифровано** через `cryptography.fernet`
- Ключ шифрования: `PLATFORM_SECRET_KEY` env var (обязателен при наличии токенов)
- Декриптация только в момент HTTP-запроса, не кешируется в памяти
- Ротация: поле `api_token_expires_at` + алерт за 7 дней до истечения

---

## 6. Зависимости

```
# Новые зависимости в collector/requirements.txt
playwright==1.44.0          # уже есть в образе mcr.microsoft.com/playwright/python
anthropic==0.30.0           # для L3 агента
cryptography==42.0.0        # для шифрования токенов
```
