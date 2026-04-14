# PRD — Adaptive Scraper Pipeline

**Feature:** adaptive-scraper-pipeline
**Sprint:** 12
**Priority:** Critical
**Story Points:** 21

---

## Problem Statement

Текущий `BaseScraper` реализует только один режим сбора данных — HTTP-запросы через httpx (L1). Это приводит к:

1. **WB и Ozon:** 498/403 ошибки из-за anti-bot (wbaas, Qrator) — данные не собираются
2. **Самокат:** возвращает minimal HTML (1784 символа) без данных — SPA требует JS
3. **Лента:** 401 на всех эндпоинтах — требует авторизацию
4. **Нет пути к официальным API:** WB и Ozon имеют Seller API, но код его не использует
5. **Хрупкость:** hardcoded CSS-селекторы ломаются при любом редизайне платформы

---

## Goals

1. Реализовать 4-уровневый пайплайн сбора данных (L0→L3) с авто-выбором уровня
2. Интегрировать официальные Seller API для WB и Ozon (L0)
3. Добавить Playwright-режим для JS-heavy платформ (L2)
4. Прототип адаптивного агентного экстрактора на базе Playwright + LLM (L3)
5. Полностью сохранить обратную совместимость с существующими Celery-задачами

---

## Non-Goals

- Реализация L3 для всех 110+ платформ (только прототип)
- Замена существующей БД-схемы
- UI для управления уровнями скрапинга (это Platform Management, Feature #22)

---

## User Stories

### US-01: Бренд с токеном WB получает данные через официальный API
```
As a brand manager,
When my organization has a WB API token configured,
I want the system to use the official WB Seller API to collect product data,
So that data is reliable, complete, and without risk of blocking.

Acceptance Criteria:
- Given: org has wb_api_token in Platform record
- When: Celery task runs collect_content for WB SKU
- Then: data fetched via dev.wildberries.ru Seller API, not card.wb.ru
- And: if token invalid (401) → fallback to L2, alert admin
- And: api_level_used field stored in content_scores record
```

### US-02: Платформа без API собирает данные через Playwright
```
As a system operator,
When a platform is configured with mode=playwright,
I want the collector to launch a headless Chromium browser,
So that JS-rendered content is captured correctly.

Acceptance Criteria:
- Given: platform.scraper_mode = 'playwright'
- When: collect task executes
- Then: Playwright launches Chromium, loads page, waits for network idle
- And: network XHR requests are intercepted and parsed as JSON when possible
- And: browser session reused within same Celery task (not per-request)
- And: screenshots stored to MinIO on error for debugging
```

### US-03: Неизвестная платформа парсится через агентный экстрактор
```
As a system operator,
When adding a new platform with mode=agent,
I want the system to use accessibility tree + LLM extraction,
So that I don't need to write hardcoded selectors.

Acceptance Criteria:
- Given: platform.scraper_mode = 'agent'
- When: collect task runs for a new platform
- Then: Playwright opens page, captures accessibility tree snapshot
- And: snapshot sent to Claude API with extraction prompt
- And: Claude returns structured JSON: {title, price, stock, description}
- And: result validated against ContentData/PriceData schemas before saving
```

### US-04: Автоматическая деградация при сбое уровня
```
As a system,
When a higher scraping level fails,
I want to automatically try the next lower level,
So that data collection continues with best-effort result.

Acceptance Criteria:
- Given: L0 returns 401 (expired token)
- When: fallback chain is configured
- Then: system tries L1 → L2 in order
- And: logs which level succeeded
- And: admin alert sent when L0 fails (token expiry notification)
```

---

## Success Metrics

| Метрика | До | После |
|---------|----|----|
| WB data collection success rate | ~0% (wbaas блок) | ≥95% (L0 с токеном) |
| Ozon data collection success rate | ~0% (Qrator блок) | ≥95% (L0 с токеном) |
| Samocat data collected | 0 (SPA блок) | ≥80% (L2 Playwright) |
| Новая платформа time-to-data | Недели (писать scraper) | Часы (L3 agent) |

---

## Dependencies

- WB Seller API токен (от клиента бренда) — хранится зашифровано в Platform
- Playwright установлен в collector Docker образе (уже есть в `mcr.microsoft.com/playwright/python`)
- Claude API key для L3 агента
- `docs/research/platform-scraping-audit-2025.md` — источник данных об API эндпоинтах
