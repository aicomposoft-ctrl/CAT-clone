# Specification — Adaptive Scraper Pipeline

---

## Функциональные требования

### FR-01: ScraperRouter — центральная точка входа
- **FR-01.1:** ScraperRouter принимает `(platform, sku_id, data_type)` и возвращает `ScrapedData`
- **FR-01.2:** Уровень выбирается автоматически на основе `platform.scraper_mode` и наличия `api_token`
- **FR-01.3:** При сбое уровня — fallback по цепочке `platform.fallback_chain`
- **FR-01.4:** Логирует использованный уровень и причину fallback
- **FR-01.5:** Сохраняет `scraper_level` в итоговую запись БД

### FR-02: L0 — Seller API интеграция
- **FR-02.1:** WBSellerAPIScraper использует `dev.wildberries.ru` API с токеном
- **FR-02.2:** OzonSellerAPIScraper использует `api.ozon.ru` с Client ID + API Key
- **FR-02.3:** Токен расшифровывается из `platform.api_token_encrypted` в момент запроса
- **FR-02.4:** При HTTP 401 → генерирует `ScraperError("TOKEN_INVALID")` → fallback
- **FR-02.5:** Алерт администратору при TOKEN_INVALID (email через существующий AlertService)

### FR-03: L2 — Playwright режим
- **FR-03.1:** Браузер запускается один раз на Celery-воркер (не per-request)
- **FR-03.2:** Network interception: перехват JSON-ответов с Content-Type: application/json
- **FR-03.3:** Если intercepted JSON содержит ожидаемые поля → парсить его, не DOM
- **FR-03.4:** Если DOM-парсинг → CSS-селекторы задаются в `platform.selectors` (JSONB)
- **FR-03.5:** Screenshot при ошибке → MinIO `debug/{platform}/{date}/{sku_id}.png`
- **FR-03.6:** Таймаут страницы: 30 сек, `waitUntil: networkidle`
- **FR-03.7:** Прокси в формате Playwright: `{"server": "http://host:port"}`

### FR-04: L3 — Agent режим
- **FR-04.1:** После загрузки страницы через Playwright → `page.accessibility.snapshot()`
- **FR-04.2:** Снапшот + промпт отправляются в Claude API (claude-haiku-4-5 для скорости)
- **FR-04.3:** Промпт параметризован типом данных: content / price / stock / reviews
- **FR-04.4:** Ответ Claude валидируется через Pydantic → ContentData | PriceData | etc.
- **FR-04.5:** При ошибке валидации — ScraperError("AGENT_EXTRACTION_FAILED")
- **FR-04.6:** Кеш промптов в Redis: `agent_prompt:{platform_id}:{data_type}` TTL 24h

### FR-05: Конфигурация платформ
- **FR-05.1:** Поле `scraper_mode` в таблице `platforms`: auto|http|playwright|agent (глобальный default)
- **FR-05.2:** Таблица `org_platform_credentials` — per-org конфигурация (токены, selectors, fallback_chain)
- **FR-05.3:** Поле `api_token_encrypted` в `org_platform_credentials` — зашифрован Fernet
- **FR-05.4:** Поле `fallback_chain` в `org_platform_credentials` — JSONB: `["l0","l1","l2","l3"]`
- **FR-05.5:** Поле `selectors` в `org_platform_credentials` — JSONB: `{"price": "span.price", "title": "h1.product-title"}`
- **FR-05.6:** API для CRUD org_platform_credentials обновляется (Feature #22) — здесь только миграция

---

## Нефункциональные требования

### NFR-01: Производительность
- L0 запрос: ≤ 2 сек (официальный API)
- L1 запрос: ≤ 5 сек
- L2 (Playwright): ≤ 30 сек
- L3 (Agent): ≤ 60 сек (Playwright + Claude API round-trip)

### NFR-02: Надёжность
- Каждый уровень: 3 retry с exponential backoff (унаследовано из `with_retry`)
- Circuit breaker: если 5 подряд ошибок L0 → отключить L0 на 1 час для данной платформы
- Dead letter queue в Redis для задач, исчерпавших все уровни

### NFR-03: Безопасность
- `api_token_encrypted` никогда не логируется, не возвращается через API
- `PLATFORM_SECRET_KEY` обязателен в env если есть зашифрованные токены
- L3 промпты не включают чувствительные данные организации

### NFR-04: Наблюдаемость
- Каждая задача логирует: `platform`, `level_used`, `fallback_reason`, `duration_ms`
- Метрики в ClickHouse: `collector_stats` таблица (platform, level, success, duration)
- Flower показывает scraper_level в метаданных задачи

---

## BDD Сценарии

### Happy Path

```gherkin
Scenario: L0 success — WB Seller API returns product data
  Given платформа WB, org_id=org_a, есть валидный api_token_encrypted в org_platform_credentials
  And fallback_chain = ["l0", "l2"]
  When ScraperRouter.collect(WB_PLATFORM_ID, nm_id, DataType.CONTENT, org_a.id)
  Then возвращает ContentData с title, description, image_url
  And result.scraper_level == 0
  And запись в content_scores с scraper_level=0

Scenario: L2 XHR interception resolves product JSON
  Given платформа Самокат, scraper_mode='playwright'
  And страница при загрузке делает XHR GET /api/v1/products/{id}
  And ответ XHR содержит {"name": "...", "price": 199.0}
  When PlaywrightScraper.collect(url, DataType.PRICE)
  Then PriceData распарсена из перехваченного JSON
  And DOM-селекторы не использовались

Scenario: L3 agent extracts data from accessibility tree
  Given платформа NewRetailer, fallback_chain = ["l3"]
  When AgentScraper.collect(url, DataType.CONTENT)
  Then page.locator("body").aria_snapshot() вызван
  And снапшот отправлен в Claude claude-haiku-4-5-20251001 в XML-обёртке
  And JSON ответ прошёл Pydantic валидацию против ContentData
  And результат сохранён в Redis с TTL=3600
```

### Граничные случаи

| Сценарий | Ожидаемое поведение |
|----------|---------------------|
| L0 токен истёк (401) | Fallback → L2, алерт admin |
| L2 страница не загрузилась за 30 сек | Screenshot → MinIO, fallback → L3 |
| L3 Claude вернул невалидный JSON | ScraperError("AGENT_EXTRACTION_FAILED"), задача в DLQ |
| Все уровни исчерпаны | ScraperError("ALL_LEVELS_FAILED"), алерт admin |
| scraper_mode = 'auto', нет токена в org_platform_credentials | Chain: L1 → L2 |
| scraper_mode = 'auto', есть токен в org_platform_credentials | Chain: L0 → L2 |
| network interception поймал HTML вместо JSON | Переключение на DOM-парсинг |
| org_b запрашивает WB, org_a имеет токен | org_b НЕ получает токен org_a; chain = L1→L2 |
| L0 ошибка 5 раз подряд для платформы | Circuit breaker: L0 отключается на 1 час |

---

## Изменения в существующих компонентах

| Компонент | Изменение |
|-----------|-----------|
| `BaseScraper` | Добавить `scraper_level: int`, унифицировать интерфейс через `collect()` |
| `WildberriesScraper` | Становится L1-реализацией, L0 выносится в `WBSellerAPIScraper` |
| `OzonScraper` | Аналогично — L1 остаётся, добавляется `OzonSellerAPIScraper` |
| Celery tasks | Используют `ScraperRouter.collect()` вместо прямого вызова скрапера |
| Platform model | Новые поля: `scraper_mode`, `api_token_encrypted`, `fallback_chain`, `selectors` |
| Alembic migration | `0014_adaptive_scraper_platform_fields.py` |
