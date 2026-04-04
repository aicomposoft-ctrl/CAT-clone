# PRD — Web Dashboard
> Feature: web-dashboard | SPARC Phase 1 | CAT Project

---

## 1. Executive Summary

Web Dashboard — интерактивный React-фронтенд для CAT-платформы, предоставляющий бренд-менеджерам и trade-маркетологам единый экран управления мониторингом онлайн-полки. Заменяет ручной анализ Excel-выгрузок на live-интерфейс с цветовой индикацией, drill-down аналитикой, фильтрацией по платформам/брендам/SKU и прямой инициацией Excel-экспорта.

**Бизнес-ценность:** Сокращение времени ежедневного обзора состояния полки с 60–90 минут до 10–15 минут за счёт агрегации всех доменов (контент, сток, цены, отзывы, алерты) в одном интерфейсе.

---

## 2. Problem Statement

FMCG-бренды отслеживают состояние своих товаров на 110+ платформах вручную через Excel-файлы. Ключевые проблемы:

1. **Нет единого экрана** — данные разбросаны по выгрузкам, нет оперативного обзора
2. **Медленный drill-down** — чтобы понять причину низкого score, нужно открыть несколько файлов
3. **Алерты не визуализированы** — email-алерт приходит, но контекст (динамика, сравнение) недоступен
4. **Нет сравнения с планом** — дистрибуция план/факт нельзя сравнить без ручной сводной

---

## 3. Target Users

| Persona | Роль | Задача в системе |
|---------|------|-----------------|
| Brand Manager | Управляет портфелем брендов | Ежедневный обзор, настройка алертов, экспорт |
| Trade Marketing Manager | Следит за дистрибуцией | Мониторинг план/факт, ценовые аномалии |
| Analyst (viewer) | Read-only аналитика | Просмотр дашбордов, экспорт отчётов |

---

## 4. Feature Scope (MVP)

### Included

| Feature | Priority | Description |
|---------|----------|-------------|
| Dashboard Overview | P0 | KPI-сводка: средний content score, % алертов, покрытие дистрибуции |
| Content Score Table | P0 | Таблица SKU × Platform с цветовой индикацией, фильтрами, drill-down |
| Distribution Monitoring | P0 | План/факт дистрибуции по группам и платформам |
| Price Monitoring | P0 | Таблица текущих цен с аномалиями, trend-график |
| Reviews Dashboard | P1 | Сентимент по брендам/платформам, список последних отзывов |
| Alerts Feed | P1 | Лента алертов с фильтром по типу/статусу, acknowledge |
| Excel Export Trigger | P0 | Кнопка экспорта всех отчётов прямо из UI |
| SKU Management | P1 | CRUD SKU + загрузка эталонных материалов |
| Authentication UI | P0 | Login, logout, смена пароля, профиль |

### Excluded (v2)

- Конфигуратор алертов (UI для управления правилами)
- Competitor price tracking view (данные есть, UI — v2)
- Mobile-first responsive layout
- Real-time WebSocket updates (polling v1)

---

## 5. User Stories Summary

| ID | Story | Priority |
|----|-------|----------|
| US-01 | Brand Manager видит KPI-сводку на главном экране | P0 |
| US-02 | Manager просматривает content scores с фильтрами | P0 |
| US-03 | Manager делает drill-down по низкому SKU | P0 |
| US-04 | Manager видит дистрибуцию план/факт | P0 |
| US-05 | Manager видит ценовые аномалии | P0 |
| US-06 | Manager видит сентимент-аналитику отзывов | P1 |
| US-07 | Manager видит ленту алертов и может их acknowledge | P1 |
| US-08 | Manager инициирует Excel-экспорт из UI | P0 |
| US-09 | Admin управляет SKU (CRUD + эталоны) | P1 |
| US-10 | Любой пользователь проходит аутентификацию | P0 |

---

## 6. Non-Functional Requirements

| NFR | Target |
|-----|--------|
| Initial load (LCP) | < 2s на 100 Mbps |
| Table render (1000 rows) | < 300ms |
| API response (filtered list) | < 500ms p95 |
| Browser support | Chrome 100+, Firefox 100+, Safari 15+ |
| Multi-tenant isolation | Данные строго по org_id |
| Session timeout | 15 мин access token, refresh без перезагрузки |
| Accessibility | WCAG 2.1 AA (keyboard navigation, color contrast) |

---

## 7. Success Metrics

| Metric | Baseline | Target |
|--------|----------|--------|
| Время ежедневного обзора | 60–90 мин | ≤ 15 мин |
| Bounce rate с Dashboard | n/a | < 20% |
| Excel export через UI (vs ручной) | 0% | > 80% |
| Покрытие E2E-тестами критических путей | 0% | 100% |
