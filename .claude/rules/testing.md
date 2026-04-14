# Testing Rules — CAT

## Test Organization

```
services/api/tests/
├── unit/             # Pure logic tests (no DB, no HTTP)
│   ├── test_content_scorer.py
│   ├── test_sentiment.py
│   └── test_alert_rules.py
├── integration/      # Tests with real DB (use pytest fixtures with rollback)
│   ├── test_sku_repository.py
│   ├── test_content_service.py
│   └── test_auth.py
└── e2e/              # Full HTTP stack tests (httpx + TestClient)
    ├── test_content_api.py
    ├── test_stock_api.py
    └── test_auth_api.py

services/collector/tests/
└── test_scrapers.py  # Scraper unit tests (mock HTTP responses)

services/frontend/src/
└── **/__tests__/     # Jest + React Testing Library
```

## Coverage Targets

| Type | Target | Minimum |
|------|--------|---------|
| Unit | 85% | 70% |
| Integration | 70% | 60% |
| E2E critical paths | 100% | 100% |

Critical paths that MUST have E2E tests:
- Auth login + token refresh
- SKU creation + reference upload
- Content score retrieval (with org_id isolation)
- Distribution plan upload
- Excel export (Content + Stock)
- Alert triggering

## Test Naming

```python
# Pattern: test_{action}_{context}_{expected_result}
def test_get_content_scores_with_org_isolation_returns_only_own_data()
def test_login_with_invalid_password_returns_401()
def test_bulk_upload_with_invalid_rows_reports_errors_and_imports_valid()
```

## Multi-Tenant Test Rule

**Every repository/service test MUST include a cross-tenant isolation test:**

```python
@pytest.mark.asyncio
async def test_content_scores_cross_tenant_isolation(db_session):
    # Create data for org_a
    org_a_sku = await create_test_sku(db_session, org_id=ORG_A_ID)
    await create_test_score(db_session, sku_id=org_a_sku.id)

    # Query as org_b — must get empty result
    scores = await content_repo.get_scores(db_session, org_id=ORG_B_ID)
    assert len(scores) == 0, "Cross-tenant data leakage detected!"
```

## Scraper Testing

```python
# Always mock HTTP responses — never hit real platforms in tests
@pytest.fixture
def mock_wb_response(respx_mock):
    respx_mock.get("https://card.wb.ru/...").mock(
        return_value=httpx.Response(200, json=FIXTURE_WB_RESPONSE)
    )

async def test_wb_scraper_parses_price(mock_wb_response):
    scraper = WildberriesScraper()
    result = await scraper.collect_price(test_sku)
    assert result.price == Decimal("299.00")
```

## Pytest Fixtures (shared)

```python
# conftest.py
@pytest.fixture
async def db_session():
    """Async session with rollback after each test."""
    async with AsyncSession(engine) as session:
        async with session.begin():
            yield session
            await session.rollback()

@pytest.fixture
def auth_headers(test_user):
    """JWT headers for authenticated requests."""
    token = create_access_token(test_user.id, test_user.org_id)
    return {"Authorization": f"Bearer {token}"}
```

## Frontend Testing

```typescript
// Use React Testing Library, not Enzyme
// Test behavior, not implementation

test("content score table shows red for scores below 50", () => {
  render(<ContentScoreTable scores={[{ content_total: 42, ... }]} />)
  const row = screen.getByRole("row", { name: /42/ })
  expect(row).toHaveClass("score-red")
})

// Mock API calls with msw
server.use(
  rest.get("/api/v1/content/scores", (req, res, ctx) =>
    res(ctx.json(mockScores))
  )
)
```
