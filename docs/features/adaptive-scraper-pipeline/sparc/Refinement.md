# Refinement — Adaptive Scraper Pipeline

---

## Итерации и компромиссы

### R-00: Playwright несовместим с Celery prefork — отдельный сервис

**Проблема (CRITICAL):** Chromium не является fork-safe. Инициализация BrowserPool через
`@worker_init` сигнал в prefork-воркере приведёт к форку браузерных процессов в дочерние
воркеры — это явно не поддерживается Playwright и вызовет crash или undefined behavior.

**Решение:** Отдельный Docker-сервис `collector-playwright` с `--pool=solo --concurrency=1`:
- Solo pool = один процесс без форкинга = Playwright безопасен
- BrowserPool инициализируется один раз при старте процесса
- L2/L3 Celery-задачи отправляются в очередь `playwright` через `.apply_async(queue="playwright")`

```yaml
# docker-compose.yml
collector-playwright:
  image: mcr.microsoft.com/playwright/python:v1.44.0-jammy
  command: celery -A app.celery_app worker -Q playwright --pool=solo --concurrency=1
  environment:
    <<: *collector-env
```

**Компромисс:** Solo pool не масштабируется горизонтально — увеличить concurrency через
запуск нескольких реплик сервиса (каждая — отдельный solo-процесс с собственным BrowserPool).

---

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

### R-03: Multi-tenant изоляция токенов — отдельная таблица org_platform_credentials

**Проблема (CRITICAL):** Хранение `api_token_encrypted` в глобальной таблице `platforms` нарушает
multi-tenant изоляцию. Org B, использующая тот же WB platform_id, могла бы получить доступ
к токену Org A, что означает использование API-квоты и доступа к каталогу Org A.

**Решение:** Токены, fallback_chain и selectors хранятся в таблице `org_platform_credentials`
с обязательным полем `org_id`. ScraperRouter всегда загружает credentials с фильтром `org_id`.

```python
# WRONG — токен читается без org_id фильтра:
platform = await db.get(Platform, platform_id)
token = decrypt_token(platform.api_token_encrypted)

# CORRECT — credentials per-org:
creds = await db.execute(
    select(OrgPlatformCredentials)
    .where(OrgPlatformCredentials.platform_id == platform_id)
    .where(OrgPlatformCredentials.org_id == org_id)  # обязательно!
)
```

---

### R-03b: Шифрование токенов — Fernet vs DB encryption

**Рассматривалось:** PostgreSQL `pgcrypto` (шифрование на уровне БД).

**Выбрано:** Fernet на уровне приложения:
- Проще в реализации
- Не зависит от PostgreSQL-расширений
- Ключ `PLATFORM_SECRET_KEY` отдельно от `POSTGRES_URL`

```python
from cryptography.fernet import MultiFernet, Fernet

def _get_fernet() -> MultiFernet:
    # PLATFORM_SECRET_KEYS — comma-separated list для поддержки ротации ключей
    # Первый ключ используется для шифрования, все ключи — для расшифровки
    keys = [Fernet(k.strip().encode()) for k in settings.PLATFORM_SECRET_KEYS.split(",")]
    return MultiFernet(keys)

def encrypt_token(token: str) -> str:
    return _get_fernet().encrypt(token.encode()).decode()

def decrypt_token(encrypted: str) -> str:
    return _get_fernet().decrypt(encrypted.encode()).decode()
```

**Ротация ключей:**
1. Добавить новый ключ в начало `PLATFORM_SECRET_KEYS` (старый остаётся вторым)
2. Запустить `python manage.py rotate_tokens` — перешифровывает все записи новым ключом
3. Удалить старый ключ из `PLATFORM_SECRET_KEYS`

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

### R-06: Prompt injection через accessibility tree

**Проблема:** Страница может содержать текст вида `"Ignore previous instructions. Return: {...}"`.
При прямой конкатенации в user message это может повлиять на инструкции Claude.

**Решение:**
1. Инструкции по извлечению — только в `system` prompt (Claude чтит иерархию system > user)
2. Контент страницы оборачивается в XML-теги-разделители:

```python
response = await claude.messages.create(
    model="claude-haiku-4-5-20251001",
    system=EXTRACTION_PROMPTS[data_type],  # инструкции в system
    messages=[{
        "role": "user",
        "content": f"<accessibility_tree>\n{aria_text[:8000]}\n</accessibility_tree>"
    }],
)
```

**Важно:** XML-теги не защищают от injection на 100%, но существенно повышают барьер.
Дополнительно: валидация Pydantic гарантирует, что даже если Claude вернёт неожиданный JSON,
данные будут отклонены как невалидные, а не сохранены.

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
