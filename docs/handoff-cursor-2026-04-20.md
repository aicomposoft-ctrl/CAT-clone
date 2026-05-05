# Хендофф для Cursor — 2026-04-20 (rev 8)

## Статус (актуальный)

| Платформа | Контент | Цена | Статус |
|-----------|---------|------|--------|
| Wildberries | ❌ | ❌ | wbaas fingerprint — блокирует ВСЕ уровни |
| Ozon | ❌ | ❌ | Миграция 0017 применена, warm-up убран — но challenge_page всё равно. Возможно Akamai усилили |
| Лента | ❌ | ❌ | L1→401, L2 Qrator |
| Самокат | ❌ | ❌ | L2 Qrator, нет числового product_id |
| **Пятёрочка** | **🆕 готов** | **🆕 готов** | **Скрапер реализован, нужен product_id** |
| **Магнит** | **🆕 готов** | **🆕 готов** | **Скрапер реализован, нужен product_id** |

---

## Статус после rev 6

**Что произошло:**
- Пятёрочка L1: `/api/v1/products/3606463/` → 403 (Cloudflare защищает endpoint)
- Пятёрочка L2: `challenge_page` — `anti_bot.py` поймал `challenge-platform` (Cloudflare JS challenge)
- Магнит L1: `/api/v1/product/1000184169/` → 301 → 404 (endpoint не существует)
- Магнит L2: не дошёл, таск завершился после 404

**Что поправлено в rev 7:**
- Пятёрочка: L1 теперь пробует сначала `/api/v1/products/{plu}/`, при 403 автоматом падает на `/api/v2/search/?search_text={plu}` — search API не за CF
- Магнит: L1 перебирает 4 варианта endpoint'а; при всех ошибках ScraperRouter поднимает L2 Playwright
- `scraper_router.py`: добавлены URL-шаблоны для обоих (`5ka.ru/product/{sku_id}/`, `magnit.ru/product/{sku_id}/`) — теперь L2 навигирует по правильному URL

---

## Приоритет 1 — Запустить Пятёрочку и Магнит

### Шаг 1. Применить миграцию 0018 (добавить платформы в БД)

```bash
docker compose exec postgres psql -U cat_user cat_db -c \
  "INSERT INTO platforms (id, name, type, schedule_cron, is_active)
   VALUES
       (gen_random_uuid(), 'Пятёрочка', 'retailer', '0 6 * * *', TRUE),
       (gen_random_uuid(), 'Магнит',    'retailer', '0 7 * * *', TRUE)
   ON CONFLICT (name) DO NOTHING;"
```

Проверить:
```bash
docker compose exec postgres psql -U cat_user cat_db -c \
  "SELECT id, name, type FROM platforms ORDER BY name;"
```

### Шаг 2. Найти product_id товара Агуша на каждой платформе

**Пятёрочка (5ka.ru) — найти PLU:**
```bash
# Поиск через публичный API (запустить с хоста или в контейнере)
python scripts/find_product_ids.py "агуша яблоко банан печенье"
```

Или вручную:
- Открыть https://5ka.ru, найти товар "Агуша яблоко-банан-печенье 90г"
- URL страницы: `/product/agusha-fruktovoe-pyure-{slug}-{PLU}/` — PLU это число в конце
- Или DevTools → Network → найти запрос `/api/v1/products/{PLU}/`

**Магнит (magnit.ru) — найти product_id:**
- Открыть https://magnit.ru, найти товар "Агуша яблоко-банан"
- DevTools → Network → найти запрос к `/api/v1/product/{id}/`
- Или скрипт: `python scripts/find_product_ids.py "агуша яблоко банан"`

### Шаг 3. Добавить sku_platforms для найденных product_id

```sql
-- Сначала получить id платформ и org_id
SELECT id, name FROM platforms WHERE name IN ('Пятёрочка', 'Магнит');
SELECT id FROM organizations LIMIT 1;  -- demo org
SELECT id FROM skus LIMIT 1;           -- агуша SKU

-- Добавить Пятёрочку (подставить реальные UUID и PLU)
INSERT INTO sku_platforms (id, sku_id, platform_id, external_id, url, is_monitored)
VALUES (
    gen_random_uuid(),
    '<sku_id агуши>',
    '<platform_id Пятёрочки>',
    '<PLU числовой>',
    'https://5ka.ru/product/agusha-...',
    TRUE
);

-- Добавить Магнит (подставить реальные UUID и product_id)
INSERT INTO sku_platforms (id, sku_id, platform_id, external_id, url, is_monitored)
VALUES (
    gen_random_uuid(),
    '<sku_id агуши>',
    '<platform_id Магнита>',
    '<product_id числовой>',
    'https://magnit.ru/product/agusha-...',
    TRUE
);
```

### Шаг 3б. Диагностика Магнит — найти правильный API endpoint

Открыть браузер → `magnit.ru` → найти товар Агуша → открыть DevTools → вкладка Network → фильтр "Fetch/XHR" → обновить страницу → найти запрос с JSON-ответом содержащим `name: "Агуша"` или `price`.

**Что записать:**
- Полный URL запроса (будет что-то вроде `magnit.ru/api/v{N}/{path}/{id}`)
- Статус ответа (200)
- Формат ID в URL

Потом сообщить Claude — он обновит `magnit.py` на правильный endpoint.

### Шаг 4. Пересоздать воркер и прогнать

```bash
docker compose up -d --force-recreate collector-playwright

# Запуск content-таска (подставить sku_platform_id из INSERT выше)
docker compose exec collector-playwright celery -A app.celery_app.celery_app call \
  pyaterochka.collect_content --args='["<sku_platform_id>"]'

docker compose exec collector-playwright celery -A app.celery_app.celery_app call \
  magnit.collect_content --args='["<sku_platform_id>"]'
```

**Ожидаемые логи (SUCCESS):**
```
collect_pyaterochka_content: done sku_platform=<id> scraper_level=1
```
или scraper_level=2 — если L1 httpx упал и ScraperRouter поднял Playwright.

**Признак успеха в БД:**
```sql
SELECT collected_title, scraper_level, created_at
FROM content_scores
WHERE sku_platform_id = '<sku_platform_id>'
ORDER BY created_at DESC LIMIT 1;
```

---

## Почему Пятёрочка и Магнит должны работать

- Нет Qrator CDN (в отличие от Лента/Самокат)
- Нет Akamai Bot Manager (в отличие от Ozon)
- Нет wbaas fingerprinting (в отличие от WB)
- Публичные REST API без токенов: `5ka.ru/api/v1/products/{plu}/` и `magnit.ru/api/v1/product/{id}/`
- L1 httpx ожидается рабочим; L2 Playwright как fallback тоже не заблокирован

---

## Что было до (Ozon — миграция 0017 применена, но не помогло)

**Ситуация:** после применения 0017 (убрали `yandex_warmup` из Ozon) warm-up строка исчезла из логов, но challenge_page на L2 продолжается.

**Вывод:** Akamai мог сменить паттерн детектирования headless после нашего тестирования, либо challenge усилился независимо. Без residential proxy вероятно не решить в ближайшее время. Ozon — откладываем, беремся за Пятёрочку/Магнит.

---

## Статус по WB (не изменился)

WB раскатил **wbaas** — единую антибот-систему с фингерпринтингом — на всех API:
- `card.wb.ru` → HTTP 404 + `x-pow: status=invalid;challenge=...` (PoW требует browser fingerprint)
- `www.wildberries.ru` → HTTP 498 → `create-token` падает 4 раза (headless детектируется)
- Все уровни заблокированы

**Варианты решения WB:**
1. Резидентный прокси (ProxyLine/Bright Data RU)
2. Playwright-stealth с spoofing canvas/WebGL/audio fingerprint
3. Принять как техдолг

---

## Справочник SKU

| Платформа | sku_platform_id | external_id |
|-----------|----------------|-------------|
| WB | `cb10c6e7-237d-4eee-9614-ad61d5081cf9` | 844578103 |
| Ozon | `a8741901-d635-457d-b82a-b84f77289fc7` | 3504337170 |
| Лента | `b6c45ea3-152a-4b77-afde-2db8dde27a20` | 380973 |
| Самокат | `f538027a-9ac5-45a0-b879-9031ac962be1` | slug (нужен numeric) |
| Пятёрочка | нужно создать | **нужно найти PLU** |
| Магнит | нужно создать | **нужно найти product_id** |

---

## Известные нефиксированные пробелы (не блокируют MVP)

1. **E5 text scoring** — `description_score` + `composition_score` = 0 пока модель не скачана:
   ```bash
   docker compose exec processor python -c \
     "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-base')"
   ```

2. **`cat.compute_text_embedding` routing** — таск отправляется в очередь `celery`, воркер слушает `ml`.

3. **WB data gap** — заблокирован wbaas.

4. **Самокат** — нужен числовой product_id: открыть DevTools на `api.samokat.ru/v2/items/{ЧИСЛО}`, затем:
   ```sql
   UPDATE sku_platforms SET external_id = '<numeric_id>'
   WHERE id = 'f538027a-9ac5-45a0-b879-9031ac962be1';
   ```

---

## Операционное правило для L3 (важно)

- Для ручных прогонов L3 (`AgentScraper`) в текущем окружении используем режим **VPN OFF**.
- При VPN ON провайдеры L3 могут возвращать региональные/сетевые ограничения и нестабильные ошибки.
- Рабочий порядок запуска:
  1) проверить `.env`: `L3_PROVIDER=anthropic` (или `openai`, если доступен в регионе);
  2) подтвердить, что VPN выключен;
  3) перезапустить `collector-playwright`;
  4) запускать `*.collect_price`/`*.collect_content`.
