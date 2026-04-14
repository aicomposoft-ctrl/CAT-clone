# ADR-009: React + TypeScript + Ant Design для фронтенда

**Дата:** 2026-03-01  
**Статус:** Accepted  
**Авторы:** CAT Team

---

## Контекст

CAT — B2B SaaS-дашборд для аналитиков и менеджеров брендов. Нужен: богатый UI с таблицами, графиками, фильтрами; быстрая разработка; TypeScript для надёжности.

## Рассматриваемые варианты

### UI Framework
| Вариант | B2B компоненты | TypeScript | Готовые таблицы/формы |
|---------|---------------|------------|----------------------|
| **Ant Design 5 (выбран)** | ✅ Отличные | ✅ | ✅ Table, Form, DatePicker |
| Material UI | ✅ Хорошие | ✅ | ✅ |
| Tailwind + headlessUI | ❌ (самодел) | ✅ | ❌ |
| shadcn/ui | Умеренные | ✅ | Частично |

### State Management
| Вариант | Server state | Client state |
|---------|-------------|-------------|
| **React Query v5 + Zustand (выбран)** | ✅ | ✅ |
| Redux Toolkit | Оверинжиниринг | ✅ |
| SWR | ✅ | ❌ |

### Charts
| Вариант | Кастомизация | Производительность |
|---------|-------------|-------------------|
| **ECharts (выбран)** | Высокая | Отличная |
| Recharts | Средняя | Хорошая |
| Chart.js | Средняя | Хорошая |

## Решение

**React 18 + TypeScript + Ant Design 5 + React Query v5 + Zustand + ECharts + Vite**

- React Query — весь server state (кеш, инвалидация, pagination, optimistic updates)
- Zustand — только auth state (токены, пользователь)
- Ant Design Table с серверной пагинацией (pageSize=50)
- ECharts для трендов цен, дистрибуции, тональности отзывов

## Последствия

- **Положительные:** Ant Design даёт готовые B2B-компоненты (Table, Form, DatePicker, Select) без кастомной разработки; ECharts производительнее Recharts на больших датасетах
- **Известные gotchas:**
  - `rowKey` в Table всегда должен быть `id`, не index
  - ECharts требует `chart.resize()` при изменении размера панели
  - React Query v5: нет `onSuccess` в `useQuery`, использовать `useEffect`
