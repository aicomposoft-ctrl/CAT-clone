# Research Findings — Web Dashboard
> Feature: web-dashboard | SPARC Phase 1 | CAT Project

---

## Executive Summary

Web Dashboard для CAT строится на устоявшемся стеке (React 18 + Ant Design 5 + ECharts), который является де-факто стандартом для data-heavy B2B SaaS в русскоязычном enterprise-сегменте. Ключевые паттерны: React Query для server state, URL-параметры для фильтров, progressive disclosure для сложных таблиц. Главные риски — ECharts resize в Ant Design Drawer и JWT race condition при concurrent 401 — имеют задокументированные решения.

---

## Technology Assessment

### React Query vs Redux Toolkit Query

**Вывод: React Query (TanStack Query v5)**

| Критерий | React Query | RTK Query |
|----------|-------------|-----------|
| Boilerplate | Минимальный | Средний (reducers, slices) |
| Background refresh | Встроен | Требует настройки |
| Optimistic updates | Простые | Сложнее |
| Cache invalidation | `queryKey` паттерн | Tag-based |
| Совместимость с Zustand | Отлично | Избыточно с Redux |

React Query покрывает server state, Zustand — auth state. Нет необходимости в Redux.

### Ant Design 5 Table — Virtual Scroll

Ant Design 5.x (начиная с 5.9) поддерживает `virtual` prop на Table компоненте для виртуализации строк. При 1000+ строках избегает DOM-оверлоада:

```typescript
<Table virtual scroll={{ y: 600 }} ... />
```

Gotcha: `virtual` несовместим с `expandable` rows в некоторых версиях — тестировать отдельно.

### ECharts vs Recharts

**Вывод: ECharts (через echarts-for-react)**

ECharts выигрывает для CAT-специфичного use case:
- Heatmap (distribution monitoring) — встроен в ECharts, в Recharts нет
- Multi-series line (price comparison) — performant в ECharts
- Large datasets (1000+ datapoints) — ECharts canvas-based, быстрее SVG Recharts

**Ключевой gotcha:** `chart.resize()` обязателен в `afterOpenChange` Ant Design Drawer, иначе chart рендерится с шириной 0.

### Vite vs CRA

**Вывод: Vite** (уже в package.json проекта)
- Hot Module Replacement в разы быстрее CRA
- Native ESM, tree-shaking из коробки
- ECharts chunking работает лучше

---

## State Management Patterns

### URL-параметры для фильтров

Паттерн `useSearchParams` (React Router v6) для синхронизации фильтров с URL:

```typescript
const [searchParams, setSearchParams] = useSearchParams()

const filters = {
  platform_id: searchParams.get('platform_id'),
  score_max: searchParams.get('score_max') ? Number(...) : undefined,
}

const updateFilter = (key: string, value: unknown) => {
  setSearchParams(prev => {
    if (value == null) prev.delete(key)
    else prev.set(key, String(value))
    return prev
  })
}
```

Преимущества: browser back работает корректно, ссылки шарабельны, bookmark-able.

### JWT Concurrent Refresh

Классический race condition: 3 запроса получают 401 одновременно → 3 refresh запроса → второй и третий не работают (token уже использован).

Решение — singleton promise:
```typescript
let refreshPromise: Promise<string> | null = null
// Все 3 конкурентных 401 ждут один промис
```

Это не только best practice — это необходимость для refresh token rotation (каждый token одноразовый).

---

## UX Patterns (B2B Analytics)

### Progressive Disclosure

Исследования Nielsen Norman Group показывают: пользователи аналитических систем начинают с вопроса, а не с данных. Оптимальная структура:

1. **Overview first** — KPI карточки с трендами
2. **Filter down** — таблица с фильтрами
3. **Details on demand** — drawer/modal для деталей

Ant Design Drawer (не новая страница) для drill-down — правильный выбор: пользователь не теряет контекст (список остаётся за drawer).

### Color Coding в таблицах

WCAG 2.1 требует не полагаться только на цвет. В CAT:
- Зелёный/жёлтый/красный + числовое значение
- Для скринридеров: `aria-label="Content score: 42%, red zone"`

---

## Competitive Analysis (Dashboard Patterns)

| Продукт | Паттерн | Применимость к CAT |
|---------|---------|-------------------|
| Retail Rocket | Platform × SKU heatmap | ✅ Адаптировать для distribution |
| DataFeed Pro | Color-coded content audit | ✅ Exact fit для content scores |
| Stackline | Category/brand drill-down | ✅ Адаптировать для brand filter |
| Сберлогистика Аналитика | Ant Design + ECharts | ✅ Proof that stack works in RU enterprise |

---

## Confidence Assessment

- **High confidence:** React Query + Zustand + Ant Design + ECharts — validated production stack
- **High confidence:** Virtual scroll performance — documented Ant Design v5 feature
- **High confidence:** JWT refresh singleton — well-known pattern
- **Medium confidence:** Bundle size <2MB gzipped — depends on ECharts tree-shaking config
- **Low confidence:** Heatmap performance at 110 platforms × 52 weeks — needs load test
