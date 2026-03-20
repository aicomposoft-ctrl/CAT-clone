# Specification — Commerce Analytics Tool (CAT)

> **SPARC Phase 3: Specification** | Detailed Requirements + User Stories + Acceptance Criteria

---

## 1. System Overview

CAT состоит из 5 доменных модулей:

```
┌─────────────────────────────────────────────────────────────────────┐
│  CAT — Commerce Analytics Tool                                       │
├──────────────┬──────────────┬──────────────┬──────────────┬─────────┤
│  COLLECTOR   │  PROCESSOR   │  REPORTER    │  ALERTER     │  API    │
│  (scrapers)  │  (ML, rules) │  (Excel, UI) │  (email)     │  (REST) │
└──────────────┴──────────────┴──────────────┴──────────────┴─────────┘
```

---

## 2. User Stories with Full Acceptance Criteria

---

### EPIC 1: Управление SKU и эталонами

#### US-01: Добавление SKU в мониторинг

```gherkin
Feature: SKU Management

Scenario: Brand Manager adds SKU for monitoring
  Given I am authenticated as Brand Manager
  When I navigate to "SKU Configuration"
  And I click "Add SKU"
  And I fill in:
    | Field        | Value                        |
    | Brand        | ИндиЛайт                    |
    | Article      | 3927                         |
    | Name         | Индейка Индилайт Духовая     |
    | Barcode      | 4600000123456                |
    | Category     | Мясо птицы                  |
  And I select platforms: [Samokat_APP, WB, Ozon, Lenta]
  Then SKU is created with status "Active"
  And monitoring is scheduled for next collection cycle

Scenario: Bulk SKU upload via CSV
  Given I have a CSV file with 200 SKUs
  When I upload the file
  Then all 200 SKUs are created
  And invalid rows are reported with line numbers and error messages
  And valid SKUs start monitoring immediately
```

#### US-02: Загрузка эталонных материалов

```gherkin
Scenario: Brand Manager uploads reference image
  Given SKU "3927" is created
  When I upload file "indilite_front_reference.jpg" as Image:Front reference
  Then image is stored in S3 with URL recorded
  And content scoring uses this image for all future comparisons
  And "Image:Front reference uploaded" confirmation is shown

Scenario: Brand Manager sets reference description
  Given SKU "3927" is created
  When I paste the reference description text (max 5000 chars)
  And I paste the reference composition text
  Then both are stored as benchmarks for this SKU
  And system confirms: "Reference updated. Next scoring: tonight at 02:00"
```

---

### EPIC 2: Content Monitoring

#### US-03: Просмотр Content Score

```gherkin
Feature: Content Score Dashboard

Scenario: Trade Marketing Manager views content scores
  Given the system has collected data for the last 24 hours
  When I navigate to "Content" section
  Then I see a table with columns:
    [Платформа | Бренд | Артикул | SKU Name | Content Total | Image:Front | Description | Composition | URL]
  And each score is color-coded: green (≥80%) | yellow (50-79%) | red (<50%)
  And I can sort by any column
  And I can filter by: brand, platform, score range, date

Scenario: Manager drills into a low-scoring SKU
  Given SKU "3927" has Content Total = 42% on Samokat_APP
  When I click on that SKU row
  Then I see:
    - Side-by-side comparison: collected image vs reference image
    - Diff highlight of description vs reference text
    - Composition match percentage with diff
    - Historical score chart (30 days)
  And I can click "Reference URL" to open the actual marketplace page
```

#### US-04: Export Content Report (Excel)

```gherkin
Scenario: Agency Manager exports Content Report
  Given data exists for period "2025-03-10 to 2025-03-17"
  When I click "Export" → "Content Report"
  And I select date range and brands
  Then I download "Content_Report_2025-03-17.xlsx"
  And file has two sheets:
    Sheet "Total":
      | Магазин | Content total | Image:Front | Description | Composition |
      | Ритейлер | 72 | 63 | 63 | 92 |
    Sheet "Score card":
      | Магазин | Бренд | Артикул | RPC | Название продукта | Ссылка | Картинка | Эталонная картинка |
      | ... |
  And the format matches the Content Report.xlsx template exactly
```

---

### EPIC 3: Stock & Distribution Monitoring

#### US-05: Настройка плана дистрибуции

```gherkin
Feature: Distribution Plan Management

Scenario: Manager uploads distribution plan
  Given I am on "Distribution Plan" page
  When I upload a plan file with columns:
    [Площадка | Группа | Название карточки | Кол-во ТТ План]
  Then plan values are stored per SKU per network
  And system starts tracking actual vs plan
  And confirmation shows: "Plan uploaded for 45 SKUs across 3 networks"

Scenario: Manager manually sets plan for SKU
  Given SKU "Крылышки утенка Озерка в маринаде 900г" is configured
  When I set Plan TT = 66 for platform "Ритейлер"
  Then distribution tracking starts with this plan
```

#### US-06: Просмотр дистрибуции план/факт

```gherkin
Feature: Distribution Dashboard

Scenario: Trade Marketing Manager checks distribution
  Given plan is set and data is collected
  When I open "Distribution" section
  Then I see sheet "По сети" with:
    | Площадка | Группа | SKU | Кол-во ТТ План | Кол-во ТТ Факт | Дистрибуция % |
    | Ритейлер | Фреш | Крылышки утенка... | 66 | 66 | 100% |
  And I can filter by network, brand, distribution threshold
  And SKUs with Дистрибуция < 80% are highlighted red

Scenario: Manager drills to city level
  Given distribution data exists
  When I click on SKU "Ветчина Индилайт Кампана"
  Then I see breakdown by city:
    | Город | Неделя 1 | Неделя 2 | Неделя 3 | Неделя 4 |
    | Москва | 16 | 16 | 16 | 12 |
  And I can drill to dark store / address level

Scenario: Manager views share in assortment
  Given data is collected
  When I view "Доля в ассортименте" tab
  Then I see:
    | Площадка | Группа | Город | Бренд | Нед.1 | Нед.2 | Нед.3 | Нед.4 |
    | Ритейлер | Заморозка | Москва | Novoferma | 11% | 11% | 11% | 11% |
```

#### US-07: Export Stock Report

```gherkin
Scenario: Manager exports Stock Report
  Given stock data exists
  When I click "Export" → "Stock Report"
  Then I download Stock_Report_YYYY-MM-DD.xlsx with sheets:
    - "План Факт по сети"
    - "Все SKU, категория_бренд"
    - "SKU на ДС по городам"
    - "Доля в асс-те по городам"
    - "SKU по адресам"
    - "План_Факт ТОП города"
    - "SKU на ТТ"
  And each sheet matches the Stock Report.xlsx template exactly
```

---

### EPIC 4: Reviews Analysis

#### US-08: Анализ отзывов по брендам

```gherkin
Feature: Reviews Dashboard

Scenario: Brand Manager views review sentiment summary
  Given reviews have been collected
  When I open "Reviews" section → "Тотал по брендам"
  Then I see:
    | Бренд | Компания | Доля негатива | Доля позитива |
    | ИндиЛайт | Клиент | 22.7% | 61.4% |
    | 365 дней | Конкурент | 37.5% | 37.5% |
  And I can compare own brand vs competitors
  And trend line shows 90-day dynamics

Scenario: Manager views individual reviews
  Given reviews are collected
  When I open "Тексты отзывов" tab
  Then I see filterable list with:
    | Маркетплейс | Категория | Бренд | SKU | Review Text | Sentiment | Date |
  And I can filter by: brand, marketplace, category, sentiment, date range
  And I can export filtered results to Excel (Reviews Report format)

Scenario: Manager exports Reviews Report
  When I click "Export" → "Reviews Report"
  Then I download Reviews_Report_YYYY-MM-DD.xlsx with sheets:
    - "Сводная"
    - "Тотал по брендам"
    - "Тотал по брендам и категориям"
    - "Тексты отзывов"
  And format matches Reviews Report.xlsx template
```

---

### EPIC 5: Price & Competitor Monitoring

#### US-09: Мониторинг цен конкурентов

```gherkin
Feature: Price & Promo Monitoring

Scenario: Manager views competitor price dynamics
  Given competitor SKUs are configured
  When I open "Prices" section
  Then I see price history for each SKU × Platform × Date
  And I can compare own price vs competitor prices on same platform
  And I can see promo/discount events highlighted

Scenario: Manager receives competitor promo alert
  Given alert threshold is set: "notify when competitor discount > 10%"
  When a configured competitor SKU shows a 15% discount on WB
  Then within 2 hours I receive an email:
    Subject: "⚠️ Конкурент снизил цену: [SKU name] на Wildberries"
    Body: SKU name | Previous price | New price | Discount % | Platform | Direct link
  And alert appears in dashboard notification center
```

---

### EPIC 6: System Configuration

#### US-10: Управление платформами и расписанием

```gherkin
Feature: Platform Configuration

Scenario: Admin configures new platform scraper
  Given I am authenticated as Admin
  When I open "Platforms" settings
  And I add platform with:
    | Field | Value |
    | Name | Самокат APP |
    | Type | Darkstore |
    | Scraper | samokat_v2 |
    | Schedule | Daily 02:00 |
  Then scraper runs on next scheduled cycle
  And new platform appears in platform filter across all sections

Scenario: Admin views scraper health
  Given scraping is configured
  When I open "System Status" page
  Then I see health status per platform:
    | Platform | Last Run | Status | SKUs Collected | Duration |
    | WB | 2025-03-20 02:15 | ✅ OK | 1,247 | 45 min |
    | Samokat | 2025-03-20 03:02 | ⚠️ Partial | 89/120 | 72 min |
  And failed platforms are highlighted for manual investigation
```

---

## 3. API Specification

### Authentication

```
POST /api/v1/auth/login
Request: { email: string, password: string }
Response 200: { access_token: string, refresh_token: string, expires_in: 3600 }
Response 401: { error: "INVALID_CREDENTIALS" }

POST /api/v1/auth/refresh
Request: { refresh_token: string }
Response 200: { access_token: string }

POST /api/v1/auth/logout
Headers: { Authorization: Bearer <token> }
Response 200: { message: "Logged out" }
```

### SKU Management

```
GET  /api/v1/skus?brand=&platform=&page=&limit=
POST /api/v1/skus
PUT  /api/v1/skus/{id}
DELETE /api/v1/skus/{id}
POST /api/v1/skus/bulk-upload (CSV)
POST /api/v1/skus/{id}/reference (upload reference image/text)
```

### Content

```
GET  /api/v1/content/scores?sku_id=&platform=&date_from=&date_to=
GET  /api/v1/content/scores/{sku_id}/{platform}/history
GET  /api/v1/content/export?format=xlsx&...
```

### Stock

```
GET  /api/v1/stock/distribution?network=&brand=&week=
GET  /api/v1/stock/by-city?sku_id=&network=
GET  /api/v1/stock/by-address?sku_id=&city=
POST /api/v1/stock/plan (upload distribution plan)
GET  /api/v1/stock/export?format=xlsx&...
```

### Reviews

```
GET  /api/v1/reviews?brand=&marketplace=&sentiment=&date_from=&date_to=
GET  /api/v1/reviews/summary?brand=&period=
GET  /api/v1/reviews/export?format=xlsx&...
```

### Prices

```
GET  /api/v1/prices?sku_id=&platform=&date_from=&date_to=
GET  /api/v1/prices/alerts (pending alerts)
POST /api/v1/prices/alert-config (set thresholds)
```

---

## 4. Feature Matrix (Priority)

| Feature | Priority | Sprint | Story Points |
|---------|----------|--------|--------------|
| Auth (JWT) | P0 | 1 | 5 |
| SKU CRUD + bulk upload | P0 | 1 | 8 |
| Reference upload (S3) | P0 | 1 | 5 |
| WB scraper | P0 | 2 | 13 |
| Ozon scraper | P0 | 2 | 13 |
| Самокат scraper | P0 | 2 | 8 |
| Лента scraper | P0 | 2 | 8 |
| Content scoring (image) | P0 | 3 | 13 |
| Content scoring (text) | P0 | 3 | 8 |
| Stock plan upload | P0 | 3 | 5 |
| Distribution dashboard | P0 | 4 | 13 |
| Excel Export (Content) | P0 | 4 | 8 |
| Excel Export (Stock) | P0 | 4 | 8 |
| Email alerts | P0 | 5 | 8 |
| Price monitoring | P1 | 6 | 13 |
| Reviews NLP | P1 | 7 | 13 |
| Excel Export (Reviews) | P1 | 7 | 5 |
| Web Dashboard | P1 | 8 | 21 |
| API public endpoints | P1 | 9 | 13 |
| Multi-client support | P1 | 10 | 13 |
