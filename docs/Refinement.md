# Refinement — Commerce Analytics Tool (CAT)

> **SPARC Phase 6: Refinement** | Edge Cases, Testing, Performance, Security Hardening

---

## 1. Edge Cases Matrix

| Scenario | Input | Expected Behavior | Handling |
|----------|-------|-------------------|----------|
| SKU has no reference image | Reference image = NULL | Skip image score, compute only text scores | Nullify image_front, adjust weights |
| Collected image URL 404 | Image download fails | Log warning, score image_front = 0, flag for review | HTTP retry × 3, then score as 0 |
| Empty description on platform | Collected description = "" | Description score = 0, flag "content missing" | Zero score + alert |
| Platform changes HTML structure | Scraper returns null fields | Log "schema_changed" alert to admin, skip scoring | Health check + admin notification |
| Rate limit from platform | 429 HTTP | Exponential backoff (2, 4, 8, 16s), proxy rotate | Celery retry with countdown |
| Concurrent writes for same SKU | Two scrapers running simultaneously | Upsert with conflict resolution on (sku_id, platform_id, date) | DB-level UNIQUE + ON CONFLICT DO UPDATE |
| Distribution plan not set for SKU | Plan count = 0 | Distribution % = NULL (not 0%) | Distinguish "not planned" from "0%" |
| Review with no text | Review text = "" or NULL | sentiment = "neutral", score = 0.5 | Skip ML, default neutral |
| New platform added mid-cycle | Platform added during collection run | Process from next scheduled run | Config reload on next beat tick |
| Client uploads wrong CSV format | CSV with wrong headers | Return 422 with list of missing headers | Strict schema validation |
| S3 storage full | Image upload fails | Alert admin, log SKU as "storage_error", skip image | Storage monitoring + capacity alerts |
| ML model unavailable | Processor service down | Queue ML tasks, process when recovered | Celery retry + DLQ |
| Excel with 100K+ rows | Large export request | Stream chunked response, timeout = 300s | openpyxl streaming mode |
| User login from new country | JWT issued | No geo-restriction (B2B SaaS); log for audit | Audit log only |
| Tenant A accesses Tenant B data | org_id mismatch | 403 Forbidden | RLS + middleware check |
| Time zone issues in scheduling | Platform in different TZ | All times stored as UTC, converted for display | UTC-first design |

---

## 2. Testing Strategy

### Unit Tests (pytest)

**Target Coverage: 85%**

```python
# Content Scorer Tests
class TestContentScorer:
    def test_identical_images_score_100(self):
        """Identical image embeddings → image_front = 100"""
        score = compute_image_similarity(emb_A, emb_A)
        assert score == pytest.approx(100.0, abs=0.1)

    def test_empty_description_scores_zero(self):
        score = compute_text_similarity("reference text", "")
        assert score == 0.0

    def test_weights_sum_to_100(self):
        """Content total weights must sum correctly"""
        total = compute_content_total(img=80, desc=60, comp=40)
        expected = 0.40 * 80 + 0.35 * 60 + 0.25 * 40
        assert total == pytest.approx(expected, abs=0.01)

    def test_null_reference_image_adjusts_weights(self):
        score = ContentScorer(sku_with_no_reference_image)
        # Only text weights should contribute
        assert score.image_front is None
        assert score.content_total <= 100

# Distribution Tests
class TestDistributionReport:
    def test_100_percent_when_plan_equals_fact(self):
        plan, fact = 66, 66
        assert compute_distribution_pct(plan, fact) == 100.0

    def test_zero_plan_returns_null(self):
        assert compute_distribution_pct(0, 5) is None

    def test_partial_distribution(self):
        assert compute_distribution_pct(66, 33) == pytest.approx(50.0, abs=0.1)

# Alert Tests
class TestAlertDetection:
    def test_content_drop_triggers_alert(self):
        yesterday_score = 85.0
        today_score = 45.0  # Below 70% threshold
        alert = check_content_alert(config, today_score, yesterday_score)
        assert alert is not None
        assert alert.alert_type == "content_drop"

    def test_no_duplicate_alerts_same_day(self):
        trigger_alert(config, sku_platform)
        trigger_alert(config, sku_platform)  # Second call same day
        assert count_alerts_today(config, sku_platform) == 1
```

### Integration Tests

```python
# API Integration Tests
class TestContentAPI:
    def test_export_content_report_xlsx(self, client, auth_headers):
        response = client.post("/api/v1/reports/export",
            json={"report_type": "content", "date_from": "2025-03-10", ...},
            headers=auth_headers)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/vnd.openxmlformats..."
        wb = openpyxl.load_workbook(BytesIO(response.content))
        assert "Total" in wb.sheetnames
        assert "Score card" in wb.sheetnames

    def test_org_isolation(self, client, org_a_headers, org_b_data):
        """Org A cannot access Org B's scores"""
        response = client.get(f"/api/v1/content/scores?sku_id={org_b_data.sku_id}",
            headers=org_a_headers)
        assert response.status_code == 404  # Not found for this org

# Scraper Integration Tests
class TestScraper:
    @pytest.mark.integration
    def test_wildberries_scraper_collects_content(self, wb_scraper, test_sku):
        """Requires real network access - marked as integration"""
        result = wb_scraper.collect_content(test_sku)
        assert result.image_url is not None
        assert result.description is not None
        assert result.price > 0
```

### BDD Scenarios (Gherkin)

```gherkin
Feature: Content Score Monitoring

  Background:
    Given a brand manager is authenticated
    And SKU "3927" is configured with reference image and description
    And platform "Samokat_APP" is active for this SKU

  Scenario: Happy path - Score displayed correctly
    Given the scraper collected content for SKU "3927" on "Samokat_APP" today
    When I navigate to "Content" section
    Then I see SKU "3927" with platform "Samokat_APP"
    And content_total score is displayed as a percentage
    And color coding reflects the score level

  Scenario: Error handling - Platform scraper failed
    Given the Samokat_APP scraper failed today for SKU "3927"
    When I navigate to "Content" section
    Then I see SKU "3927" with status "Collection failed"
    And the last successful score is still displayed with its date

  Scenario: Edge case - Reference image missing
    Given SKU "3927" has no reference image uploaded
    When content score is computed
    Then image_front column shows "—" (not applicable)
    And content_total is computed from description and composition only
    And a warning "Reference image missing" is shown

  Scenario: Security - Cross-tenant access denied
    Given user from organization "Brand A" is authenticated
    When they request content scores for a SKU belonging to "Brand B"
    Then the response is 404 Not Found
    And no Brand B data is returned

Feature: Excel Report Generation

  Scenario: Content Report matches template
    Given data exists for the last 7 days
    When I export Content Report for date range "2025-03-10" to "2025-03-17"
    Then I receive an xlsx file
    And sheet "Total" has columns: Магазин | Content total | Image:Front | Description | Composition
    And sheet "Score card" has columns: Магазин | Бренд | Артикул | RPC | Название продукта | Ссылка | Картинка | Эталонная картинка
    And explanation rows are present at the bottom of Score card

  Scenario: Stock Report matches template
    Given distribution plan and stock data exist
    When I export Stock Report
    Then xlsx contains exactly 7 sheets:
      | Sheet Name |
      | План Факт по сети |
      | Все SKU, категория_бренд |
      | SKU на ДС по городам |
      | Доля в асс-те по городам |
      | SKU по адресам |
      | План_Факт ТОП города |
      | SKU на ТТ |
```

---

## 3. Performance Optimizations

### Database

```sql
-- Indexes for common query patterns
CREATE INDEX idx_content_scores_date ON content_scores(scored_at DESC);
CREATE INDEX idx_content_scores_sku_platform ON content_scores(sku_platform_id, scored_at DESC);
CREATE INDEX idx_reviews_brand_sentiment ON reviews(brand_id, sentiment, review_date DESC);
CREATE INDEX idx_price_snapshots_collected ON price_snapshots(sku_platform_id, collected_at DESC);

-- Partial index for alert checking (only unsent)
CREATE INDEX idx_alert_events_unsent ON alert_events(triggered_at) WHERE is_sent = FALSE;

-- PostgreSQL Row-Level Security
ALTER TABLE content_scores ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_isolation ON content_scores
    USING (EXISTS (
        SELECT 1 FROM sku_platforms sp
        JOIN skus s ON sp.sku_id = s.id
        WHERE sp.id = content_scores.sku_platform_id
          AND s.org_id = current_setting('app.org_id')::uuid
    ));
```

### Caching Strategy

```
L1: In-process (FastAPI startup)
  → ML model weights (loaded once at startup, ~500MB RAM)
  → Platform configs (reloaded every 5 min)

L2: Redis cache
  → Reference embeddings: TTL=24h (invalidated on reference update)
  → Dashboard aggregates: TTL=1h
  → User sessions: TTL=15min (JWT duration)

L3: Database query cache
  → ClickHouse materialized views for weekly aggregates
  → PostgreSQL prepared statements
```

### Scraper Optimizations

```python
# Async scraping with concurrency control
async def collect_platform(platform: Platform, skus: list[SKU]):
    semaphore = asyncio.Semaphore(10)  # Max 10 concurrent requests per platform

    async def collect_one(sku):
        async with semaphore:
            await asyncio.sleep(1 / platform.rate_limit)  # Rate limiting
            return await scraper.collect_content(sku)

    results = await asyncio.gather(*[collect_one(sku) for sku in skus],
                                   return_exceptions=True)
    return [r for r in results if not isinstance(r, Exception)]
```

---

## 4. Security Hardening

### Input Validation

```python
# Strict Pydantic models for all inputs
class ContentScoreFilter(BaseModel):
    date_from: date = Field(..., ge=date(2020, 1, 1))
    date_to: date = Field(..., le=date.today())
    brand_ids: list[UUID] = Field(default=[], max_items=100)
    platform_ids: list[UUID] = Field(default=[], max_items=200)

    @validator('date_to')
    def date_range_max_90_days(cls, v, values):
        if 'date_from' in values and (v - values['date_from']).days > 90:
            raise ValueError('Date range cannot exceed 90 days')
        return v
```

### Rate Limiting

```python
# Per-user rate limits via Redis
RATE_LIMITS = {
    "basic": {"requests": 100, "window": 60},   # 100 req/min
    "professional": {"requests": 500, "window": 60},
    "enterprise": {"requests": 2000, "window": 60},
    "export": {"requests": 10, "window": 3600}  # 10 exports/hour
}
```

### Audit Logging

```python
# Log all data access for compliance
@app.middleware("http")
async def audit_log(request: Request, call_next):
    response = await call_next(request)
    if request.method in ["GET", "POST", "PUT", "DELETE"]:
        audit_logger.info({
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": request.state.user_id,
            "org_id": request.state.org_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "ip": request.client.host
        })
    return response
```

---

## 5. Technical Debt Tracker

| Item | Priority | Sprint | Notes |
|------|----------|--------|-------|
| Migrate to async DB driver (asyncpg) | Medium | Sprint 3 | Currently using sync SQLAlchemy |
| Add E2E tests (Playwright) | High | Sprint 5 | After UI is stable |
| Extract scraper modules to plugins | Low | v2.0 | For easier 3rd-party additions |
| Implement GraphQL alongside REST | Low | v2.0 | For complex dashboard queries |
| Add OpenTelemetry tracing | Medium | Sprint 8 | For production observability |
