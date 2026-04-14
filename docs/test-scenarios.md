# BDD Test Scenarios — Commerce Analytics Tool (CAT)

> **SPARC Phase 2: Validation** | Gherkin Scenarios
> **Generated:** 2026-03-21

---

## Feature: Authentication

### Happy Path

```gherkin
Feature: User Authentication

  Scenario: Successful login
    Given user "manager@brand.ru" exists with valid password
    When I POST /api/v1/auth/login with { email: "manager@brand.ru", password: "ValidPass123!" }
    Then response status is 200
    And response contains "access_token" and "refresh_token"
    And "expires_in" equals 3600

  Scenario: Token refresh
    Given I have a valid refresh_token
    When I POST /api/v1/auth/refresh with the refresh_token
    Then response status is 200
    And I receive a new "access_token"
```

### Error Handling

```gherkin
  Scenario: Login with wrong password
    When I POST /api/v1/auth/login with wrong password
    Then response status is 401
    And response body contains "INVALID_CREDENTIALS"
    And no tokens are returned

  Scenario: Login with non-existent email
    When I POST /api/v1/auth/login with email "ghost@nobody.ru"
    Then response status is 401
    And response time is same as valid user (timing attack prevention)

  Scenario: Expired refresh token
    Given the refresh_token expired 24 hours ago
    When I POST /api/v1/auth/refresh
    Then response status is 401
    And error is "TOKEN_EXPIRED"
```

### Security

```gherkin
  Scenario: Brute force protection
    When I send 11 login requests within 1 minute from the same IP
    Then the 11th request returns 429 Too Many Requests
    And response includes "Retry-After" header

  Scenario: SQL injection in login
    When I POST /api/v1/auth/login with email "' OR 1=1 --"
    Then response status is 400 or 401
    And no database error is leaked in response
    And the injection attempt is logged

  Scenario: JWT token from another tenant rejected
    Given user A has a valid JWT from tenant "brand_a"
    When user A requests GET /api/v1/skus belonging to tenant "brand_b"
    Then response status is 403
    And no data from brand_b is returned
```

---

## Feature: SKU Management

### Happy Path

```gherkin
Feature: SKU Management

  Scenario: Add single SKU
    Given I am authenticated as Brand Manager for tenant "indilite"
    When I POST /api/v1/skus with:
      | brand    | ИндиЛайт                |
      | article  | 3927                    |
      | name     | Индейка Духовая 1.5кг   |
      | barcode  | 4600000123456           |
      | category | Мясо птицы              |
      | platforms | ["WB", "Ozon", "Samokat_APP"] |
    Then response status is 201
    And SKU is created with status "Active"
    And monitoring is scheduled for the next collection cycle

  Scenario: Bulk SKU upload via CSV
    Given I have a CSV file with 200 valid SKUs
    When I POST /api/v1/skus/bulk-upload with the file
    Then response status is 202 (accepted for processing)
    And job_id is returned for status polling
    And all 200 SKUs are created within 30 seconds
    And GET /api/v1/jobs/{job_id} shows status "completed", created: 200, failed: 0

  Scenario: Upload reference image for SKU
    Given SKU "3927" exists
    When I POST /api/v1/skus/3927/reference with image file "front.jpg" and type "image_front"
    Then response status is 200
    And image is stored in S3
    And response contains the S3 URL
    And content scoring uses this reference from the next cycle
```

### Error Handling

```gherkin
  Scenario: Bulk upload with invalid rows
    Given CSV has 198 valid rows and 2 invalid (missing barcode)
    When I upload the file
    Then 198 SKUs are created
    And response includes: { failed: 2, errors: [{ row: 45, error: "barcode required" }, ...] }

  Scenario: Duplicate SKU (same article + tenant)
    When I POST /api/v1/skus with article "3927" that already exists for my tenant
    Then response status is 409 Conflict
    And error is "SKU_ALREADY_EXISTS"

  Scenario: Reference image exceeds size limit
    When I upload an image > 10MB
    Then response status is 413
    And error message specifies the size limit
```

### Edge Cases

```gherkin
  Scenario: SKU with special characters in name
    When I create SKU with name "Утёнок «Озерка» 900г"
    Then SKU is created and name stored exactly as entered
    And Excel export renders the name correctly

  Scenario: Concurrent bulk uploads from same tenant
    When two bulk uploads are submitted simultaneously
    Then both process successfully without duplicate SKUs
    And each job reports independent results
```

---

## Feature: Content Score Dashboard

### Happy Path

```gherkin
Feature: Content Score Dashboard

  Scenario: View content scores
    Given the system collected data in the last 24 hours for 50 SKUs
    When I GET /api/v1/content/scores
    Then response status is 200
    And response contains array of scores with fields:
      [platform, brand, article, sku_name, content_total, image_front, description, composition, url]
    And content_total = weighted average of component scores
    And scores are color-coded: ≥80 green, 50-79 yellow, <50 red

  Scenario: Sort by lowest score
    When I GET /api/v1/content/scores?sort=content_total&order=asc
    Then SKUs with lowest scores appear first

  Scenario: Filter by platform and score range
    When I GET /api/v1/content/scores?platform=WB&score_max=60
    Then only WB scores below 60% are returned

  Scenario: View score history for specific SKU
    When I GET /api/v1/content/scores/3927/WB/history?days=30
    Then I receive 30 data points (one per day)
    And each point has: date, content_total, image_front, description, composition
```

### Error Handling

```gherkin
  Scenario: No data collected yet
    Given no collection has run for tenant
    When I GET /api/v1/content/scores
    Then response status is 200
    And response is empty array with message "No data collected yet. First collection scheduled for tonight at 02:00."

  Scenario: Score data older than 48h shows staleness indicator
    Given last collection was 50 hours ago
    When I view the Content Score dashboard
    Then each row shows a ⚠️ staleness badge
    And tooltip shows "Data from 50 hours ago"
```

### Security

```gherkin
  Scenario: Cross-tenant content score access blocked
    Given SKU "3927" belongs to tenant "indilite"
    And I am authenticated as user of tenant "competitor_brand"
    When I GET /api/v1/content/scores?brand=ИндиЛайт
    Then response is 200 with empty array (no data from other tenant)
    And no 403 error leaks tenant existence
```

---

## Feature: Content Alert

### Happy Path

```gherkin
Feature: Content Alerts

  Scenario: Alert triggered when score drops below threshold
    Given threshold is set to 70% for tenant "indilite"
    And SKU "3927" had score 75% yesterday
    When today's collection shows score 58%
    Then within 2 hours an email is sent to configured recipients
    And email subject contains "Снижение контент-скора: Индейка Духовая 1.5кг"
    And email body contains: SKU name, platform, old score (75%), new score (58%), direct URL

  Scenario: No duplicate alerts for sustained low score
    Given SKU "3927" scored 58% yesterday and alert was sent
    When today's score is still 58%
    Then NO second alert is sent for the same SKU+platform+threshold breach
    And alert is re-triggered only when score recovers above threshold then drops again
```

### Error Handling

```gherkin
  Scenario: SMTP server unavailable
    Given SMTP is down
    When an alert is triggered
    Then alert is queued with status "pending"
    And retry is attempted every 15 minutes
    And alert is NOT lost after system restart (persisted in DB)

  Scenario: Recipient email address invalid
    When alert is sent to "not-an-email"
    Then alert is logged as "delivery_failed"
    And admin notification is sent to fallback address
    And other recipients still receive the alert
```

### Edge Cases

```gherkin
  Scenario: Alert threshold is 0% (catch all)
    Given threshold is set to 0%
    When any score is recorded
    Then no alerts are triggered (0% threshold = disabled)

  Scenario: Multiple SKUs breach threshold in same collection
    Given 15 SKUs breach threshold in one collection run
    When alerts are processed
    Then a single digest email is sent (not 15 individual emails)
    And digest lists all 15 SKUs with scores
```

---

## Feature: Distribution Plan vs Fact

### Happy Path

```gherkin
Feature: Distribution Monitoring

  Scenario: Upload distribution plan
    Given I am authenticated as Trade Marketing Manager
    When I POST /api/v1/stock/plan with CSV:
      | Площадка | Группа | Название карточки | Кол-во ТТ План |
      | Ритейлер | Фреш   | Крылышки утенка... | 66             |
    Then response status is 200
    And response shows: { imported: 45, skus_matched: 45, skus_not_found: 0 }

  Scenario: View distribution plan vs fact
    Given plan and actual data both exist
    When I GET /api/v1/stock/distribution
    Then response contains for each SKU × Network:
      | platform | group | sku_name | plan_tt | actual_tt | distribution_pct |
    And distribution_pct = (actual_tt / plan_tt) * 100
    And rows with distribution_pct < 80 are flagged

  Scenario: Drill to city level
    When I GET /api/v1/stock/by-city?sku_id=3927&network=Ритейлер
    Then I receive weekly data for last 4 weeks by city
    Each row: { city, week_1, week_2, week_3, week_4 }

  Scenario: Export Stock Report
    When I GET /api/v1/stock/export?format=xlsx
    Then I receive a .xlsx file with 7 sheets as specified
    And generation time is < 30 seconds for 1000 SKUs
```

### Error Handling

```gherkin
  Scenario: Plan upload with unrecognized SKU names
    Given plan CSV references SKU "Unknown Product XYZ" not in the system
    When I upload the plan
    Then import succeeds for matched SKUs
    And response includes: { skus_not_found: ["Unknown Product XYZ"] }
    And unmatched SKUs are ignored without blocking the import
```

---

## Feature: Price & Competitor Monitoring

### Happy Path

```gherkin
Feature: Price Monitoring

  Scenario: View competitor price dynamics
    Given competitor SKUs are configured
    When I GET /api/v1/prices?sku_id=comp_001&platform=WB&date_from=2026-03-01
    Then I receive daily price points with fields: date, price, discount_pct, is_promo

  Scenario: Competitor promo alert triggered
    Given alert config: "notify when competitor discount ≥ 5% on WB"
    When WB scraper collects 15% discount on competitor SKU "comp_001"
    Then within 4 hours an email is sent with:
      Subject: "⚠️ Конкурент снизил цену: [SKU name] на Wildberries"
      Body: sku_name, previous_price, new_price, discount_pct, platform, direct_url
    And alert appears in /api/v1/prices/alerts endpoint
```

### Edge Cases

```gherkin
  Scenario: Price fluctuation within threshold does not alert
    Given threshold is 5%
    When competitor price changes by 3%
    Then NO alert is sent

  Scenario: Price returns to normal after alert
    Given alert was sent for 15% discount yesterday
    When today's price returns to original (0% discount)
    Then a "price normalized" notification is sent (optional, if configured)
```

---

## Feature: Excel Export — Content Report

### Happy Path

```gherkin
Feature: Excel Export

  Scenario: Export Content Report
    Given data exists for period 2026-03-10 to 2026-03-17
    When I GET /api/v1/content/export?format=xlsx&date_from=2026-03-10&date_to=2026-03-17
    Then I receive Content_Report_2026-03-17.xlsx
    And file has exactly 2 sheets: "Total" and "Score card"
    And "Total" sheet has columns: Магазин | Content total | Image:Front | Description | Composition
    And "Score card" sheet matches template column order exactly
    And export completes in < 30 seconds

  Scenario: Export Reviews Report
    When I GET /api/v1/reviews/export?format=xlsx
    Then I receive Reviews_Report_YYYY-MM-DD.xlsx with 4 sheets:
      "Сводная", "Тотал по брендам", "Тотал по брендам и категориям", "Тексты отзывов"
```

### Error Handling

```gherkin
  Scenario: Export with no data in date range
    When I request export for a period with no data
    Then I receive an empty xlsx with headers but no data rows
    And a warning message: "No data found for selected period"

  Scenario: Large export (10,000 SKUs)
    When I request export for 10,000 SKUs
    Then the job is queued asynchronously
    And response 202 with job_id
    And when complete, file is available via download URL for 24 hours
```

---

## Feature: Scraper Health Monitoring

### Happy Path

```gherkin
Feature: Platform Health

  Scenario: View scraper status
    When I GET /api/v1/system/status
    Then I see per-platform status:
      { platform, last_run, status, skus_collected, duration_minutes }
    And status is one of: "ok", "partial", "failed", "running", "scheduled"

  Scenario: Failed platform triggers alert
    Given WB scraper has status "failed" for > 2 hours
    When the monitoring check runs
    Then admin receives email: "Сбой сбора данных: Wildberries — 2+ часа"
    And system continues collecting from other platforms
```

### Edge Cases

```gherkin
  Scenario: Platform temporarily unavailable (HTTP 503)
    When platform returns 503 during collection
    Then scraper retries 3 times with exponential backoff (2s, 4s, 8s)
    Then if still failing, marks collection as "partial" with note
    And existing data from previous run is retained and shown with staleness flag
```

---

## Non-Functional BDD Scenarios

```gherkin
Feature: Performance Requirements

  Scenario: Content dashboard load time
    Given 1000 SKUs with data on 10 platforms
    When I load the Content Score dashboard
    Then page renders in < 2 seconds (p95)

  Scenario: API response time
    When I call any GET endpoint
    Then response time is < 500ms (p95)

  Scenario: Full collection cycle time
    Given 1000 SKUs configured on 5-10 platforms
    When daily collection starts
    Then all data is collected within 4 hours

  Scenario: Excel generation performance
    When I export Stock Report for 1000 SKUs
    Then file is generated in < 30 seconds

Feature: Multi-Tenant Isolation

  Scenario: Complete tenant data isolation
    Given tenant A has 500 SKUs and tenant B has 300 SKUs
    When tenant A user queries any endpoint
    Then only tenant A data is returned
    And no tenant B identifiers appear in any response

  Scenario: Database query uses tenant-scoped connection
    Given a request from tenant A
    When any DB query executes
    Then query uses SET LOCAL app.current_tenant_id = 'tenant_a'
    And all queries return only tenant A rows via RLS
```

---

## Test Coverage Summary

| Feature Area | Happy Path | Error Handling | Edge Cases | Security |
|-------------|-----------|----------------|------------|----------|
| Authentication | 2 | 3 | 0 | 3 |
| SKU Management | 3 | 3 | 2 | 1 |
| Content Scores | 4 | 2 | 0 | 1 |
| Content Alerts | 2 | 2 | 2 | 0 |
| Distribution | 4 | 1 | 0 | 0 |
| Price Monitoring | 2 | 0 | 2 | 0 |
| Excel Export | 2 | 2 | 0 | 0 |
| Scraper Health | 2 | 0 | 1 | 0 |
| NFR (Perf + MT) | 4+2 | — | — | — |
| **Total** | **27** | **13** | **7** | **5** |

**Total scenarios: 52**
