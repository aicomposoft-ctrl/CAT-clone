# PRD — Distribution Plan Upload (Stock Plan)

**Feature ID:** stock-plan-upload
**Sprint:** 3
**Priority:** P0
**Story Points:** 5

---

## Problem Statement

CAT отслеживает фактическое наличие товаров на платформах (in_stock). Однако без планового значения дистрибуции невозможно ответить на ключевой бизнес-вопрос: "Сколько торговых точек (ТТ) должно было иметь мой товар на этой неделе, и сколько имело фактически?"

Бренд-менеджеры получают план из внутренних систем (Excel/CSV) — CAT не имеет прямого доступа к этим данным. Нужен ручной механизм загрузки планов в систему.

## Solution

CSV-загрузчик плановых показателей дистрибуции: менеджер загружает файл с планом по неделям (sku_barcode × platform_name × week_number × year → plan_tt_count), система сохраняет его в `distribution_plans` и использует для сравнения план/факт в Distribution Dashboard.

## Users & Value

| Persona | Action | Value |
|---------|--------|-------|
| Менеджер бренда | Загружает CSV с планом раз в неделю / квартал | Видит план/факт по дистрибуции в дашборде |
| Аналитик CAT | Запрашивает план через API для отчётов | Автоматизированные Excel-отчёты по дистрибуции |
| Viewer | Просматривает загруженный план | Read-only доступ к текущему плану |

## Scope (MVP)

### In scope
- `POST /api/v1/stock/distribution-plan` — загрузка CSV (max 5 MB, max 10 000 строк)
- `GET /api/v1/stock/distribution-plan` — список с фильтрами (platform_id, week, year) + пагинация
- `DELETE /api/v1/stock/distribution-plan/{id}` — удаление строки плана
- Разрешение SKU по штрих-коду (`sku_barcode → sku_id`, tenant-scoped)
- Разрешение платформы по имени (`platform_name → platform_id`, case-insensitive, global)
- UPSERT: повторная загрузка перезаписывает план для той же недели
- Поддержка кодировок: UTF-8, UTF-8-BOM, cp1251 (Windows Russian)
- Частичный импорт: валидные строки сохраняются, ошибочные — возвращаются в `errors[]`

### Out of scope
- Автоматический импорт из внешних систем (1С, SAP) — v2.0
- Загрузка планов из Excel (только CSV для MVP) — v2.0
- Fuzzy matching по имени платформы — v2.0
- Bulk delete / replace all plans for a period — v2.0

## Success Metrics

| Metric | Target |
|--------|--------|
| Загрузка 1000 строк CSV | < 3 секунды от POST до 200 |
| Точность разрешения barcode→sku_id | 100% (только exact match по org) |
| Повторная загрузка того же CSV | Idempotent (rowcount не меняется) |
| Частичный импорт: % валидных строк загружен | 100% |
| Перезапись плана при дубликате (sku×platform×week×year) | UPSERT обновляет `plan_tt_count` |

## Data Model

```
distribution_plans
    id               UUID PK
    sku_id           UUID FK → skus.id
    platform_id      UUID FK → platforms.id
    group_name       VARCHAR(100)
    plan_tt_count    INTEGER  -- плановое число ТТ
    week_number      INTEGER  -- ISO неделя (1–53)
    year             INTEGER  -- 4-значный год
    UNIQUE(sku_id, platform_id, week_number, year)
```

Tenant isolation via JOIN: `distribution_plans.sku_id → skus.org_id`.

## CSV Format

```csv
sku_barcode,platform_name,group_name,plan_tt_count,week_number,year
4600000123456,Wildberries,Moscow,150,14,2026
4600000789012,Ozon,SPb,80,14,2026
```

Required columns: `sku_barcode`, `platform_name`, `group_name`, `plan_tt_count`, `week_number`, `year`.
