# Refinement — Adaptive Scraper Pipeline

---

## Итерации и компромиссы

### R-01: BrowserPool — синглтон на воркер, не на задачу

**Проблема:** Playwright запускает Chromium (~150MB RAM). Если запускать на каждую задачу — воркер умирает от OOM.

**Решение:** `BrowserPool` как синглтон на Celery-воркер через `@worker_init_at_start` сигнал Celery. Пул из 2 браузеров на воркер.

```python
from celery.signals import worker_init, worker_shutdown

@worker_init.connect
def init_browser_pool(**kwargs):
    app.conf.browser_pool = BrowserPool(size=2)

@worker_shutdown.connect
def close_browser_pool(**kwargs):
    app.conf.browser_pool.close()
```

**Компромисс:** воркеры с Playwright не масштабируются так же легко как httpx-воркеры. Рекомендуется отдельная очередь `celery -A app.celery_app worker -Q playwright`.

---

### R-02: L3 токены и стоимость

**Проблема:** Claude API стоит денег. L3 используется для edge cases, но если misconfigured — может запускаться слишком часто.

**Решение:**
1. Rate limiter на L3: максимум 100 вызовов/день на организацию (Redis counter)
2. Caching результатов: `agent_result:{url_hash}` TTL 4 часа
3. Model: `claude-haiku-4-5-20251001` (самый дешёвый, достаточно для structured extraction)
4. Метрика стоимости: логировать `input_tokens + output_tokens` в ClickHouse

---

### R-03: Шифрование токенов — Fernet vs DB encryption

**Рассматривалось:** PostgreSQL `pgcrypto` (шифрование на уровне БД).

**Выбрано:** Fernet на уровне приложения:
- Проще в реализации
- Не зависит от PostgreSQL-расширений
- Ключ `PLATFORM_SECRET_KEY` отдельно от `POSTGRES_URL`

```python
from cryptography.fernet import Fernet

def encrypt_token(token: str) -> str:
    f = Fernet(settings.PLATFORM_SECRET_KEY.encode())
    return f.encrypt(token.encode()).decode()

def decrypt_token(encrypted: str) -> str:
    f = Fernet(settings.PLATFORM_SECRET_KEY.encode())
    return f.decrypt(encrypted.encode()).decode()
```

---

### R-04: Обратная совместимость Celery-задач

**Требование:** существующие задачи (`wb_collect_content`, `ozon_collect_price` и др.) не должны сломаться.

**Решение:** Celery-задачи остаются неизменными по сигнатуре. Внутри они делегируют в `ScraperRouter`:

```python
# Было:
@celery_app.task
async def wb_collect_content(sku_id: str, nm_id: str, org_id: str):
    scraper = WildberriesScraper(proxy_rotator)
    data = await scraper.collect_content(nm_id)
    # ...

# Стало:
@celery_app.task
async def wb_collect_content(sku_id: str, nm_id: str, org_id: str):
    router = ScraperRouter(db, redis)
    data = await router.collect(WB_PLATFORM_ID, nm_id, DataType.CONTENT, UUID(org_id))
    # ...
```

---

### R-05: Селекторы Самоката через network interception

**Исследование (из аудита):** Самокат — React SPA с internal REST API. При открытии страницы товара браузер делает XHR к `/api/v1/products/{id}` или аналогичному.

**Стратегия L2 для Самоката:**
1. Network interception перехватывает все JSON-ответы
2. Ищем ответ с полями `name`, `price`, `available`
3. Если найден — парсим JSON (не DOM)
4. Если не найден за 5 сек после `networkidle` → screenshot → L3

**Конфигурация:**
```json
{
  "name": "Самокат",
  "scraper_mode": "playwright",
  "fallback_chain": ["l2", "l3"],
  "selectors": {
    "intercept_patterns": ["api/v1/product", "graphql"],
    "price_field": "price.value",
    "stock_field": "availability.isAvailable"
  }
}
```

---

## Риски и митигации

| Риск | Вероятность | Митигация |
|------|------------|-----------|
| WB изменит структуру Seller API | Средняя | Версионирование в URL (`/v2/`), monitoring на 4xx |
| Playwright browser crash | Низкая | BrowserPool перезапускает упавший browser автоматически |
| L3 accessibility tree слишком большой (>8K tokens) | Средняя | Truncation с сохранением видимых элементов (viewport-only) |
| Claude API недоступен | Низкая | ScraperError("AGENT_EXTRACTION_FAILED") → DLQ, retry через 1 час |
| Токен WB протёк (логи) | Низкая | Sanitize логов: `re.sub(r"Bearer [A-Za-z0-9.-]+", "Bearer [REDACTED]", msg)` |

---

## Порядок реализации (Phase 3)

```
Sprint A (параллельно):
  Task 1: Alembic migration 0014 + Platform model обновление
  Task 2: ScraperRouter skeleton + WBSellerAPIScraper (L0)

Sprint B (параллельно):
  Task 3: PlaywrightScraper (L2) + BrowserPool
  Task 4: OzonSellerAPIScraper (L0) + token encryption utils

Sprint C:
  Task 5: AgentScraper (L3) прототип
  Task 6: Обновление Celery-задач (делегация в ScraperRouter)
  Task 7: Тесты (unit + integration)
```
