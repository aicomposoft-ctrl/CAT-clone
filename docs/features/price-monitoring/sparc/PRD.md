# PRD — Price Monitoring

**Feature ID:** price-monitoring
**Sprint:** 6
**Priority:** P1
**Story Points:** 13

---

## Problem Statement

Скрейперы CAT уже собирают `price_snapshots` ежедневно — данные о ценах накапливаются, но недоступны бренд-менеджерам через API. Без аналитического слоя нельзя ответить на ключевые вопросы:

- "Как изменилась цена на мой товар на WB за последние 30 дней?"
- "На какой платформе сейчас самая низкая цена?"
- "Когда произошло резкое изменение цены (+/- 10%)?"
- "Средняя скидка на мою категорию vs конкуренты?"

Данные есть — аналитического API нет.

## Solution

Домен `prices/` в `services/api/app/prices/` предоставляет REST API для анализа накопленных ценовых снимков:

1. **История цен** — временной ряд цены по SKU + платформе за период
2. **Сравнение платформ** — текущие цены одного SKU на всех платформах
3. **Ценовая статистика** — min/max/avg/медиана + дельта к предыдущему периоду
4. **Аномалии** — события, когда цена изменилась > N% за сутки
5. **Интеграция с алертами** — тип `price_change` уже есть в `alert_configs`

## Users & Value

| Persona | Задача | Ценность |
|---------|--------|----------|
| Бренд-менеджер | Мониторинг ценовой политики партнёров | "Wildberries снизил цену до 299₽ — ниже MSRP" |
| Категорийный менеджер | Сравнение с конкурентами | "Конкурент X дешевле на 15% на Ozon" |
| Маркетолог | Анализ промо-периодов | Цена vs скидка в промо-окне |
| Аналитик CAT | Базовые отчёты | Данные для Excel-экспорта (Sprint 7) |

## Scope (MVP — Sprint 6)

### In scope
- `GET /api/v1/prices/history` — временной ряд цены (фильтры: sku_id, platform_id, date_from, date_to)
- `GET /api/v1/prices/latest` — последние цены по SKU на всех платформах (сравнение)
- `GET /api/v1/prices/stats` — статистика за период (min, max, avg, median, change_pct)
- `GET /api/v1/prices/anomalies` — дни с изменением цены > threshold% (default 10%)
- Tenant isolation: все запросы фильтруются через `sku_platforms → skus.org_id`
- Данные из PostgreSQL (последние 90 дней с детализацией)

### Out of scope
- ClickHouse queries для исторических данных (> 90 дней) — v2.0
- Конкурентный анализ (SKU конкурентов) — requires competitor SKU mapping (v2.0)
- Excel Export (Prices) — Sprint 7
- Пуш-уведомления через WebSocket — v2.0
- ML-прогнозирование цен — v2.0

## Data Source

`price_snapshots` (PostgreSQL):
```
id               UUID
sku_platform_id  UUID → sku_platforms.id → skus.org_id
price            DECIMAL(10,2)
original_price   DECIMAL(10,2)
discount_pct     DECIMAL(5,2)
promo_label      VARCHAR(255)
collected_at     TIMESTAMPTZ
```

Index exists: `idx_price_snapshots_sp_time ON price_snapshots (sku_platform_id, collected_at DESC)`

## Success Metrics

| Metric | Target |
|--------|--------|
| Latency p95 для `/prices/history` (30 дней, 1 SKU, 3 платформы) | < 200 мс |
| Latency p95 для `/prices/stats` | < 100 мс |
| Аномалии детектируются корректно | threshold = изменение цены > N% между соседними снимками |
| Все запросы tenant-scoped | 100% (org_id filter на каждом запросе) |
| Нет N+1 запросов | Все данные получаются ≤ 2 SQL запросами на эндпоинт |
