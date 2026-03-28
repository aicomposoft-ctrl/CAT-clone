# PRD — Самокат Scraper

**Feature:** Самокат Scraper
**Priority:** P0 | **Sprint:** 2 | **Story Points:** 8
**Status:** Planning

---

## 1. Problem Statement

Самокат — крупнейший российский дарксторный сервис экспресс-доставки продуктов (15 мин), принадлежащий Сберу. Присутствует в 25+ городах РФ, ~50 000 SKU. FMCG-производители, размещающие товары в Самокате, не могут автоматически контролировать корректность карточек, цен и остатков через текущий CAT-пайплайн.

Самокат использует REST API (мобильное приложение + PWA) со структурированными JSON-ответами. Авторизация не требуется для чтения каталога. Продукты идентифицируются числовым `product_id` из URL вида `samokat.ru/product/{slug}-{product_id}`.

**Impact:** Дарксторы — быстрорастущий канал для FMCG. P0 для Sprint 2 — завершает покрытие "большой тройки" RU каналов вместе с WB + Ozon.

---

## 2. Target Data

Per SKU × Самокат platform combination (`sku_platform` record where `platform.name = "Samocat"`):

| Data Type | Fields | Frequency |
|-----------|--------|-----------|
| Content | title, description, composition (ingredients), main image URL | Daily 02:00 |
| Price | price, original_price, discount_pct, promo_label | Every 4h |
| Stock | in_stock (bool), available_qty | Daily 02:00 |
| Reviews | review_text, rating (1-5), review_date, external_review_id | Daily 02:00 |

`external_id` на `sku_platforms` = Самокат product_id (числовой string), например `"12345"`.
Product ID содержится в конце slug URL: `https://samokat.ru/product/molochnye-produkty-12345/`.

---

## 3. Core Requirements

### Must Have (Sprint 2)
- Скрапинг content (title, description, composition, main image URL) по product_id
- Скрапинг текущей цены и оригинальной цены по product_id
- Скрапинг флага in_stock и доступного количества по product_id
- Скрапинг последних 50 отзывов по product_id
- Rate limit: ≤ 2.0 req/sec (Самокат менее агрессивен чем Ozon)
- Поддержка proxy rotation (`PROXY_LIST_URL` env var)
- Celery task integration: 4 отдельных задачи (content, price, stock, reviews)
- Сохранение результатов в PostgreSQL (content_scores, price_snapshots, reviews)
- Retry на 429/503 с exponential backoff (max 3 retries)
- Загрузка изображений в MinIO (`collected_image_url` = S3 key)

### Should Have
- User-agent rotation
- Обработка ситуации "товар временно недоступен" vs "товар снят"
- Учёт городского контекста (цены/остатки могут различаться по городу — default: Москва)

### Won't Have (this sprint)
- Скрапинг по геолокации (несколько городов одновременно)
- Интеграция с Самокат Partner API (требует per-org credentials)
- Мониторинг поисковых позиций и категорий

---

## 4. Success Metrics

| Metric | Target |
|--------|--------|
| Success rate per daily run | ≥ 92% SKUs without error |
| Price collection latency | < 15 s per SKU |
| Content collection latency | < 20 s per SKU |
| Review collection latency | < 15 s per SKU |
| Zero IP bans per week | Rate limiting + proxy rotation |

Note: 92% target выше Ozon (90%) — у Самоката менее агрессивная защита.

---

## 5. Самокат API Endpoints

| Data | Method | URL Pattern |
|------|--------|-------------|
| Product details | GET | `https://api.samokat.ru/v2/items/{product_id}` |
| Product reviews | GET | `https://api.samokat.ru/v2/items/{product_id}/reviews?page=1&limit=50` |
| Stock availability | GET | `https://api.samokat.ru/v2/items/{product_id}/availability` |

**Headers required:**
```
User-Agent: SamokatApp/3.x.x (Android)
Accept: application/json
X-City-Id: 1  ← Москва (default)
```

**Response formats:** JSON. No Cloudflare challenge. No JS rendering required.

---

## 6. Integration Points

- `sku_platforms.platform_id` → Platform record with `name = "Samocat"`
- `sku_platforms.external_id` → Самокат product_id (numeric string)
- `content_scores` table → upsert ON CONFLICT `(sku_platform_id, scored_at)`
- `price_snapshots` table → INSERT (append-only)
- `reviews` table → upsert ON CONFLICT `(sku_platform_id, external_review_id)`
- MinIO bucket → `org/{org_id}/sku/{sku_id}/samocat/main.jpg`

---

## 7. Security Constraints

- Image URL allowlist: только `cdn.samokat.ru` домен (SSRF guard)
- `X-City-Id` хардкодим на Москву (1) — не принимаем от пользователя
- Все scraped тексты санитизируются через `sanitize()` перед DB write
- Нет API key в коде — только `PROXY_LIST_URL` из env

---

## 8. Comparison with WB / Ozon Scrapers

| Aspect | WB | Ozon | Самокат |
|--------|-----|------|---------|
| API type | REST (card API) | SPA composer JSON | REST mobile API |
| Auth required | No | No | No |
| JS rendering | No | No | No |
| Rate limit | 1 req/s | 0.5 req/s | 2 req/s |
| Bot protection | Low | High (Cloudflare) | Low |
| Product ID | nm_id (int) | item_id (int) | product_id (int) |
| Reviews source | feedbacks2 API | composer reviews | `/reviews` endpoint |
| Complexity | Medium | High | Low |
