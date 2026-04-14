# Product Requirements Document
## Commerce Analytics Tool (CAT) — Мониторинг Онлайн-Полки

**Version:** 1.0
**Date:** 2025-03-20
**Status:** Draft → In Review
**Product Owner:** TBD
**Target Architecture:** Distributed Monolith | Docker + Docker Compose | VPS

---

## 1. Executive Summary

**CAT Clone** — SaaS-платформа для мониторинга онлайн-полки, предназначенная для FMCG-производителей, брендов и digital commerce агентств. Система ежедневно собирает данные о карточках товаров, ценах, остатках и отзывах на 110+ цифровых платформах (маркетплейсы, интернет-магазины, дарксторы), сравнивает их с эталонными стандартами клиента и генерирует структурированные Excel-отчёты + алёрты.

**Ключевое позиционирование:** Первый российский инструмент, заточенный под **производителей/бренды** (не продавцов), с полным покрытием онлайн-полки, ML-оценкой контента и мониторингом дистрибуции план/факт.

---

## 2. Problem Statement

FMCG-бренды не контролируют, что происходит с их товарами на 110+ цифровых платформах ежедневно:

- **Контент деградирует**: карточки товаров не соответствуют стандартам бренда
- **Дистрибуция непрозрачна**: план/факт по торговым точкам не отслеживается
- **Конкуренты непредсказуемы**: изменения цен и промо не отслеживаются в реальном времени
- **Отзывы не анализируются**: тысячи отзывов без систематики → слепое пятно

Ручной мониторинг нескалируем: 100+ человеко-часов/неделю на 1000 SKU × 10 платформ.

---

## 3. Target Users

### Primary Persona: Trade Marketing Manager (Бренд)
- Компания: FMCG-производитель (продукты питания, напитки, бытовая химия)
- Размер: средний-крупный (50–5000 SKU, 10–110 платформ)
- Цель: ежедневный контроль полки без ручного труда
- KPI: доля полки, дистрибуция %, content score

### Secondary Persona: Brand Manager
- Цель: контроль соответствия бренд-стандартам и репутации
- KPI: content compliance %, доля позитивных отзывов

### Tertiary Persona: Digital Commerce Agency
- Компания: агентство полного цикла (Easy Commerce и аналоги)
- Цель: автоматизация репортинга для 5–20+ клиентов-брендов
- KPI: time-to-report, клиентский NPS

---

## 4. Key Features (Feature Matrix)

| Feature | MVP | v1.0 | v2.0 | Описание |
|---------|-----|------|------|----------|
| Content Monitoring | ✅ | ✅ | ✅ | Сравнение изображений, описаний, состава с эталоном |
| Stock Monitoring | ✅ | ✅ | ✅ | Дистрибуция план/факт по ТТ, городам, дарксторам |
| Price & Promo Monitoring | ✅ | ✅ | ✅ | Мониторинг цен, скидок, промо конкурентов |
| Email Alerts | ✅ | ✅ | ✅ | Алёрты при скидках конкурентов и отклонениях |
| Excel Export | ✅ | ✅ | ✅ | Content/Reviews/Stock отчёты в формате клиента |
| Reviews Analysis | — | ✅ | ✅ | NLP-анализ отзывов, sentiment, тематики |
| Web Dashboard | — | ✅ | ✅ | Интерактивный дашборд с графиками и фильтрами |
| Platform Coverage | 5-10 | 50+ | 110+ | Количество поддерживаемых платформ |
| API Access | — | ✅ | ✅ | REST API для интеграций |
| Multi-client (Agency) | — | ✅ | ✅ | Управление несколькими брендами/клиентами |
| Predictive Analytics | — | — | ✅ | Прогноз stockout, demand forecasting |
| AI Content Recommendations | — | — | ✅ | Генеративные рекомендации по улучшению карточек |

---

## 5. User Stories (MVP)

### Epic 1: Content Monitoring

**US-01** — Content Score Dashboard
```
As a Trade Marketing Manager,
I want to see a content compliance score for each SKU on each platform,
So that I can prioritize which cards need immediate correction.

Acceptance Criteria:
Given I am logged in and have SKUs configured
When I open the Content section
Then I see a score (0-100%) for each SKU × Platform combination
And the score reflects: Image:Front match %, Description match %, Composition match %
And I can sort by lowest score to identify critical issues first
```

**US-02** — Reference Upload
```
As a Brand Manager,
I want to upload reference images and text for each SKU,
So that the system can compare marketplace cards against my brand standards.

Acceptance Criteria:
Given I am on the SKU configuration page
When I upload a reference image and paste reference description/composition
Then the system stores these as the benchmark for this SKU
And future monitoring uses these references for scoring
```

**US-03** — Content Alert
```
As a Trade Marketing Manager,
I want to receive an email alert when a content score drops below threshold,
So that I can respond to card degradation immediately.

Acceptance Criteria:
Given I have set a threshold (e.g., 70%)
When the system detects a score drop below threshold
Then I receive an email within 2 hours of detection
And the email includes: SKU name, platform, score, direct link to card
```

### Epic 2: Stock & Distribution Monitoring

**US-04** — Distribution Plan vs Fact
```
As a Trade Marketing Manager,
I want to see the distribution plan vs actual for each SKU across retail networks,
So that I can identify distribution gaps and escalate to the logistics team.

Acceptance Criteria:
Given I have uploaded a distribution plan (plan TT count per SKU per network)
When I view the Stock section
Then I see Plan TT / Actual TT / Distribution % for each SKU × Network
And I can drill down to city and store address level
And I can export to Excel matching the Stock Report format
```

**US-05** — Stock by Dark Store/Warehouse
```
As an E-commerce Manager,
I want to see stock levels in pieces broken down by dark store and warehouse,
So that I can identify availability gaps before they cause stockouts.

Acceptance Criteria:
Given monitoring is configured for a platform with dark store data
When I view Stock details
Then I see stock in pieces by dark store / warehouse
And data is updated at least daily
And I can see trend (4 weeks back)
```

### Epic 3: Competitive Price Monitoring

**US-06** — Price & Promo Tracking
```
As a Trade Marketing Manager,
I want to track competitor prices and promotions across platforms,
So that I can adjust our pricing and promo strategy in response.

Acceptance Criteria:
Given competitor SKUs are configured as benchmarks
When a competitor price changes or a promotion starts
Then the change is reflected in the dashboard within 4 hours
And I receive an email alert for significant changes (configurable threshold)
```

### Epic 4: Reporting

**US-07** — Excel Export (Content Report)
```
As an Agency Manager,
I want to export a Content Report in Excel format matching our client template,
So that I can deliver the weekly report without manual formatting.

Acceptance Criteria:
Given data has been collected for the configured period
When I click "Export Content Report"
Then I receive an .xlsx file with sheets: Total, Score card
And format matches the existing Content Report.xlsx template
And data includes all configured SKUs and platforms
```

**US-08** — Excel Export (Stock Report)
```
As a Trade Marketing Manager,
I want to export a Stock Report in Excel format,
So that I can share distribution status with the logistics team.

Acceptance Criteria:
Given distribution data has been collected
When I click "Export Stock Report"
Then I receive an .xlsx file with all required sheets:
  - План Факт по сети
  - Все SKU категория/бренд
  - SKU на ДС по городам
  - Доля в асс-те по городам
  - SKU по адресам
  - План_Факт ТОП города
  - SKU на ТТ
And format matches the existing Stock Report.xlsx template
```

---

## 6. Non-Functional Requirements

### Performance
- Сбор данных: полный цикл по 5-10 платформам × 1000 SKU — не более 4 часов
- Веб-дашборд: время загрузки страницы < 2 сек
- API response time: < 500ms (p95)
- Excel экспорт: генерация < 30 сек для 1000 SKU

### Scalability
- MVP: 1-5 клиентов, 1000-10000 SKU, 5-10 платформ
- v1.0: 10-50 клиентов, 100,000 SKU, 50+ платформ
- Горизонтальное масштабирование через Docker Compose replicas

### Availability
- SLA: 99.5% uptime для веб-интерфейса
- Мониторинг сбора данных: алёрт при сбое > 2ч
- Graceful degradation: если платформа недоступна → пропустить + алёрт

### Security
- Аутентификация: JWT + refresh tokens
- Данные клиентов изолированы (multi-tenant)
- Эталонные изображения хранятся в S3 с private access
- Пароли: bcrypt hashing
- HTTPS only

### Data Retention
- Исторические данные: 12 месяцев (расширяемо)
- Excel отчёты: хранятся 90 дней
- Сырые scraped данные: 30 дней

---

## 7. Success Metrics

| Метрика | MVP Target | v1.0 Target |
|---------|-----------|-------------|
| Клиентов | 3-5 | 20-50 |
| SKU в системе | 5,000 | 100,000 |
| Платформ | 5-10 | 50+ |
| Time-to-report | < 4 ч | < 1 ч |
| Content score accuracy | > 85% | > 92% |
| Alert delivery time | < 2 ч | < 30 мин |
| DAU (активных пользователей) | > 80% от клиентов | > 90% |

---

## 8. Out of Scope (MVP)

- Мобильное приложение
- Автоматическая коррекция карточек (write-back)
- Реклама на маркетплейсах (управление кампаниями)
- Финансовая аналитика продаж (P&L)
- Прогнозирование спроса (ML forecasting)
- Интеграция с ERP системами

---

## 9. Dependencies & Integrations

| Зависимость | Тип | Статус |
|------------|-----|--------|
| Playwright / Scrapy | Web scraping | Open Source |
| PostgreSQL | Primary DB | Open Source |
| ClickHouse | Analytics DB | Open Source |
| Redis | Cache + Queue | Open Source |
| Celery | Task Queue | Open Source |
| MinIO (S3) | Image Storage | Open Source |
| FastAPI | Backend | Open Source |
| React | Frontend | Open Source |
| openpyxl | Excel generation | Open Source |
| Hugging Face ruBERT | Sentiment NLP | Open Source |
| SMTP / Postfix | Email alerts | Infrastructure |

---

## 10. Architecture Constraints (Target)

```yaml
Architecture: Distributed Monolith (Monorepo)
Containers: Docker + Docker Compose
Infrastructure: VPS (AdminVPS/HOSTKEY)
Deploy: Docker Compose direct deploy (SSH / CI pipeline)
AI Integration: MCP servers (optional future)
```
