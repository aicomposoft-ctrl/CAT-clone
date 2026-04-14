# Solution Strategy — Web Dashboard
> Feature: web-dashboard | SPARC Phase 2 | CAT Project

---

## Problem Statement (SCQA)

- **Situation:** CAT платформа имеет полный бэкенд (FastAPI, PostgreSQL, ML-pipeline) с 6 доменными сервисами и рабочими API эндпоинтами. Данные о контенте, ценах, дистрибуции, отзывах, алертах собираются ежедневно.
- **Complication:** Пользователи (бренд-менеджеры) получают данные только через Excel-файлы и email-алерты. Нет интерактивного интерфейса для исследования данных, drill-down по проблемным SKU и оперативного реагирования.
- **Question:** Как создать React-фронтенд, который даёт мгновенный обзор состояния полки без перегрузки пользователя данными, при этом позволяя глубокий анализ при необходимости?
- **Answer:** Feature-based SPA с прогрессивным раскрытием данных: KPI-обзор → домен-таблицы → drill-down в контекст.

---

## First Principles Analysis

1. **Пользователи приходят с вопросом, не с данными** — интерфейс должен отвечать на вопрос "что сейчас проблематично?", а не показывать все данные сразу.
2. **Цветовая индикация быстрее чисел** — green/yellow/red позволяет сканировать 200 строк за секунды.
3. **Drill-down важнее сводных таблиц** — одна строка с 42% контентом требует ответа "почему", а не только "что".
4. **Фильтры должны сохраняться в URL** — чтобы пользователь мог поделиться ссылкой с коллегой.
5. **Экспорт должен работать из контекста** — нажать "Export" на отфильтрованной таблице, а не переходить в другой раздел.

---

## Root Cause Analysis (Why Dashboard нужен сейчас)

1. **Why** бренд-менеджеры тратят 60-90 мин на ежедневный обзор?
   → Данные разбросаны по нескольким Excel-файлам
2. **Why** они используют Excel?
   → Нет web-интерфейса с агрегированным view
3. **Why** нет web-интерфейса?
   → Frontend scaffolded но страницы пустые (нет реализации)
4. **Why** страницы пустые?
   → Разработка шла по порядку: backend → scraping → ML → frontend last
5. **Root cause:** Фронтенд — последний слой стека, блокирует пользовательскую ценность от всей предыдущей работы

---

## Contradictions Resolved (TRIZ)

| Contradiction | TRIZ Principle | Resolution |
|--------------|----------------|------------|
| Показать все данные vs не перегрузить пользователя | #10 Preliminary action | Прогрессивное раскрытие: KPI → таблица → drawer |
| Скорость загрузки vs актуальность данных | #10 + #25 Self-service | React Query staleTime 5 min + background refetch |
| Гибкость фильтров vs простота UI | #1 Segmentation | Базовые фильтры видны, расширенные — в Collapse |
| Цвет как индикатор vs accessibility | #3 Local quality | Цвет + числовое значение + иконка всегда вместе |

---

## Recommended Approach

**Progressive Disclosure Architecture:**

```
Level 1 (Dashboard): 4 KPI cards + Red Zone + Recent Alerts
  ↓ пользователь видит проблему
Level 2 (Domain page): Фильтруемая таблица всех SKU по домену
  ↓ пользователь находит конкретный SKU
Level 3 (Drill-down drawer): Side-by-side сравнение, тренд, история
  ↓ пользователь понимает причину и может действовать
```

**Tech Decisions:**
- React Query вместо Redux для server state — меньше boilerplate, автоматический background refresh
- Ant Design Table с virtual scroll — production-ready для 1000+ строк
- URL-параметры для фильтров — шаринг ссылок, bookmark, browser back
- ECharts вместо Recharts — лучшая производительность для heatmap и multi-series

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Backend API endpoints не реализованы для dashboard/summary | Medium | High | Реализовать summary endpoint как агрегат существующих |
| ECharts resize bugs в Ant Design Drawer | High | Low | Задокументировано в coding-style gotchas, fix известен |
| Токен refresh race condition | Medium | High | Singleton refreshPromise pattern (задокументирован) |
| Большой bundle size (ECharts full) | Medium | Medium | Импортировать только нужные ECharts модули |
| Cross-tenant data leak через URL manipulation | Low | Critical | org_id на бэкенде из JWT, не из query params |
