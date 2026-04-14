# Аудит платформ для парсинга — CAT
**Дата:** 2026-04-12 | **Верификация:** GOAP-Research | **Статус:** Verified

---

## Критический вывод (читать первым)

**WB и Ozon имеют официальные Seller API.** CAT ориентирован на бренды-производители — они, как правило, являются селлерами на этих платформах. Это означает что для WB и Ozon **парсинг может быть заменён на легитимный API с токеном** — без anti-bot, без прокси, с официальной поддержкой.

Это меняет архитектуру пайплайна кардинально.

---

## 1. Wildberries

### Официальный Seller API
- **Портал:** `dev.wildberries.ru` (с 28.01.2025, старый openapi.wb.ru → редирект)
- **С 15.04.2025:** все методы переехали с `wb.ru` на `wildberries.ru`
- **Документация:** Swagger UI, OpenAPI 3.0
- **Аутентификация:** API-токен (read-only или read-write)

**Ключевые эндпоинты через Seller API:**

| Данные | Метод | Эндпоинт |
|--------|-------|----------|
| Карточки товаров | POST | `/content/v2/get/cards/list` |
| Остатки на складах WB | POST | `/api/analytics/v1/stocks-report/wb-warehouses` |
| Цены | GET/POST | `/prices/api/...` |
| Отзывы/оценки | GET | через Feedback API |
| Аналитика поиска | GET | CSV-отчёты |

**Неофициальные публичные эндпоинты** (без токена, нестабильные):

| Эндпоинт | Данные | Статус |
|----------|--------|--------|
| `card.wb.ru/cards/v2/detail?nm={id}` | Карточка товара | Работает, но wbaas блокирует |
| `search.wb.ru/exactmatch/ru/common/v4/search` | Поиск товаров | 429 при частых запросах |
| `feedbacks2.wb.ru/feedbacks/v1/{nm_id}` | Отзывы | Нестабильный |
| `basket-NN.wbbasket.ru/vol.../card.json` | CDN данные карточки | Нет защиты |

### Anti-bot защита
- **wbaas (WB Anti-Abuse System):** JS-challenge при любом запросе к www.wildberries.ru
- HTTP 498 = geo/antibot блок (не стандартный код)
- Заголовок `x-wbaas-token: get` = нужно решить challenge
- **Решение только через Playwright** — curl/httpx дают 498 даже с Russian IP
- В сентябре 2025 WB закрыл часть публичных данных, доступных ранее

### Рекомендация для CAT
**Приоритет 1 (L0):** Seller API с токеном клиента — официально, без блокировок
**Приоритет 2 (L2):** Playwright + residential RU прокси для публичных эндпоинтов

---

## 2. Ozon

### Официальный Seller API
- **Документация:** `docs.ozon.ru/global/en/api/`
- **Аутентификация:** Client ID + API Key (из личного кабинета продавца)
- **Библиотеки:** `ozon-api-client` (PyPI), PHP/Go клиенты на GitHub

**Ключевые возможности:**
- Цены товаров, остатки на складах
- Карточки товаров, описания, фото
- Отзывы и рейтинги
- Аналитика продаж, поисковые запросы

### Anti-bot защита
- **Qrator:** промышленный anti-DDoS/antibot (защищает ~30% крупного RU e-commerce)
- **Canvas Fingerprinting:** идентификация браузера по отрисовке canvas
- **Behavior analysis:** мышь, клики, паузы — анализ поведения
- **TLS fingerprinting:** JA3/JA4 сигнатуры TLS-хендшейка
- HTTP 403 при детекции бота

### Без авторизации (публичный сайт)
Нет задокументированных публичных API. Страницы — динамический SPA (React), данные загружаются через internal GraphQL/REST. Коммерческие сервисы (RealDataAPI, iwebdatascraping) предлагают scraping-as-a-service для Ozon.

### Рекомендация для CAT
**Приоритет 1 (L0):** Seller API — единственный надёжный путь
**Приоритет 2 (L2):** Playwright + BrightData residential proxies (обход Qrator)

---

## 3. Самокат (Samokat.ru)

### API
- **Технологический бренд:** ecom.tech (ex. Samokat.tech)
- Сайт — React SPA, весь контент через JS
- **Частичный API:** `samokat.ru` имеет internal REST API, не документирован публично
- Нет официального публичного API для партнёров/брендов

### Anti-bot защита
- **ServicePipe** — AntiDDoS + antibot (подтверждено через Bug Bounty программу)
- Сайт без JS возвращает minimal HTML (~1784 символа) без данных о товарах

### Что нужно для парсинга
- **Обязательно Playwright** — данные только через JS-рендеринг
- После загрузки страницы intercept XHR-запросов к internal API → извлечь JSON
- Или: скриншот + LLM extraction (L3)

### Рекомендация для CAT
**Приоритет 1 (L2):** Playwright + network interception (перехват API запросов браузера)
**Нет L0 пути** — официального API для брендов нет

---

## 4. Лента (lenta.com / online.lenta.com)

### Публичный API (задокументирован частично)
```
Base: https://lenta.com/api/v1/
https://api.lenta.com/
```

**Известные эндпоинты:**
| Эндпоинт | Данные |
|----------|--------|
| `GET /api/v1/stores/` | Список магазинов со store_id |
| `GET /api/v1/stores/{store_id}/home` | Акции на главной |
| `GET /api/v1/stores/{store_id}/crazypromotions` | "Сумасшедшие цены" |
| `GET /api/v1/stores/{store_id}/mobilepromo` | Мобильные промо |

**Авторизация:** Требуется для персональных акций и полного каталога. Метод авторизации официально не задокументирован. Возможно JWT через мобильное приложение.

### Anti-bot защита
- HTTP 401 на большинстве эндпоинтов — требует сессию/токен
- Нет публичной информации о Cloudflare/Qrator у Ленты

### Рекомендация для CAT
**Приоритет 1 (L1):** Reverse-engineer мобильного API (перехват трафика приложения через mitmproxy)
**Приоритет 2 (L2):** Playwright на `online.lenta.com` после авторизации

---

## 5. Архитектура пайплайна парсеров (рекомендации)

### Три уровня (L0 → L3)

```
L0: Official API (токен продавца)
    ↓ WB Seller API, Ozon Seller API
    ↓ Официальные данные, без блокировок, лимиты по договору
    ↓ ПРИОРИТЕТ ДЛЯ WB И OZON

L1: Known public HTTP API (без браузера)
    ↓ httpx + rate limiting + proxy rotation
    ↓ Лента /api/v1/stores/{id}/... (частично)
    ↓ WB basket CDN API (нестабильно)

L2: Playwright headless browser
    ↓ JS challenge solving (wbaas, ServicePipe)
    ↓ Network interception (перехват XHR/fetch)
    ↓ Самокат, полный Ozon, WB (если нет токена)
    ↓ Требует: residential RU proxies + fingerprint spoofing

L3: Playwright MCP + Claude (Adaptive Agent)
    ↓ Accessibility tree snapshot → LLM extraction
    ↓ Не требует hardcoded CSS selectors
    ↓ Адаптируется к изменению layout
    ↓ Для новых площадок и edge cases
```

### Playwright MCP (ключевая находка 2025)

Microsoft выпустил официальный **Playwright MCP server** (`@playwright/mcp`), который:
- Открывает браузер и управляет им через MCP-протокол
- Возвращает **accessibility tree** (не скриншоты) — структурированный DOM
- Claude читает дерево и извлекает данные без hardcoded селекторов
- **Не требует vision-модели** — работает с text-based accessibility snapshot

```python
# Концепт L3 агента для CAT
async def adaptive_scrape(url: str, extraction_prompt: str) -> dict:
    # 1. Playwright открывает страницу
    # 2. Возвращает accessibility snapshot
    # 3. Claude извлекает данные по промпту
    # "найди цену, остаток и название товара"
    # → структурированный JSON без CSS selectors
```

---

## 6. Сторонние сервисы-агрегаторы (альтернатива собственному парсингу)

| Сервис | Что даёт | Статус 2025 |
|--------|----------|------------|
| **MPSTATS** | WB + Ozon + Яндекс Маркет аналитика, API | Куплен Точка Банком, выручка 1.8B₽ |
| **Oxylabs** | Scraper API для любых сайтов, ML-рендеринг | Активен |
| **BrightData** | Residential proxies + ready datasets | Активен |
| **RealDataAPI** | Ozon product scraping API | Активен |
| **mpstats.io/integrations** | API для интеграции с WB/Ozon данными | Активен |

**Для CAT:** MPSTATS API как дополнительный источник данных (когда прямой парсинг заблокирован) — возможный fallback.

---

## 7. Итоговая матрица

| Платформа | L0 (API) | L1 (HTTP) | L2 (Playwright) | L3 (Agent) | Текущий код |
|-----------|----------|-----------|-----------------|------------|-------------|
| WB | ✅ Seller API | ⚠️ Нестабильно | ✅ + RU proxy | ✅ | ❌ Нет токена |
| Ozon | ✅ Seller API | ❌ Нет pub API | ✅ + RU proxy | ✅ | ❌ Нет токена |
| Самокат | ❌ | ❌ | ✅ + intercept | ✅ | ⚠️ Шаблон |
| Лента | ❌ | ⚠️ Частично | ✅ + auth | ✅ | ⚠️ Шаблон |

---

## 8. Следующие шаги (приоритизированные)

1. **[Быстро]** Добавить поддержку L0 — поле `api_token` в модели Platform, WB/Ozon используют Seller API если токен есть
2. **[Средне]** Переработать BaseScraper на 3-режимную архитектуру (L0/L1/L2)
3. **[Средне]** Реализовать L2 с Playwright network interception для Самоката
4. **[Долго]** Прототип L3 агента на Playwright MCP + Claude API

---

## Источники

- [WB Developer Portal](https://dev.wildberries.ru/en)
- [WB API FAQ](https://dev.wildberries.ru/en/faq)
- [Ozon Seller API Docs](https://docs.ozon.ru/global/en/api/)
- [Lenta API endpoints gist](https://gist.github.com/thevar1able/c2ea032d364c4c070f0b35ed8f74a99b)
- [Парсим Ozon — Habr](https://habr.com/ru/companies/amvera/articles/960280/)
- [Parsing Ozon с TMAPI — DTF](https://dtf.ru/software/4753306-parsing-ozon-s-tmapi)
- [Playwright MCP официальный](https://playwright.dev/docs/getting-started-mcp)
- [microsoft/playwright-mcp GitHub](https://github.com/microsoft/playwright-mcp)
- [MPSTATS куплен Точкой — Ведомости](https://www.vedomosti.ru/business/articles/2026/02/09/1174851-bank-tochka-kupil-krupnii-servis-analitiki)
- [Samokat Bug Bounty (ServicePipe)](https://bugbounty.standoff365.com/en-US/programs/samokat/)
