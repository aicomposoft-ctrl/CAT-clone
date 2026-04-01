# Refinement: Distribution Dashboard

**Feature:** `distribution-dashboard`
**Date:** 2026-04-01

---

## Edge Cases

### Backend

| Case | Handling |
|------|---------|
| `list_plans` returns 0 rows | Returns `{ items: [], total: 0 }` — service does not raise |
| Platform or SKU deleted after plan created | JOIN returns 0 rows for that plan (CASCADE/RESTRICT constraints prevent orphans) |
| Org has no plans yet | Empty list, no error |
| Invalid UUID in `platform_id` query param | FastAPI validates UUID type — returns 422 before hitting service |
| `page` beyond total pages | Returns empty items list (offset > total), not 404 |
| `size` beyond 200 | Clamped to 200 in service |

### Frontend

| Case | Handling |
|------|---------|
| URL param `week=99` (out of range) | Backend returns 422 from Query(ge=1, le=53) → dashboard shows error alert |
| File dropped is not CSV | `accept=".csv"` attribute + MIME check before POST |
| User rapidly changes filters | React Query debounce: no need — keepPreviousData prevents flicker |
| Delete while table is loading | Disable delete button during any active delete mutation |
| Multiple concurrent deletes | Each mutation is independent; table refetches on each success |
| Token expires mid-session | Axios 401 interceptor redirects to /login |

---

## Security Considerations

### Backend

- Tenant isolation via `SKU.org_id` JOIN — same logic as existing `list_plans`. No change to isolation model.
- No new endpoints — only schema and query changes.
- Platform name is from our own catalog — no XSS risk.
- SKU barcode is from our own DB — no XSS risk.

### Frontend

- RBAC enforced client-side (hide controls) AND server-side (API returns 403).
- Never store JWT in memory/closure beyond what `useAuth` already manages.
- CSV file upload: client-side 5MB check is UX only — server enforces limit.
- No eval/dangerouslySetInnerHTML used anywhere.

---

## Performance Considerations

### Backend

- `list_plans` query: JOINs on `skus.id` (PK — O(1)) and `platforms.id` (PK — O(1)).
- `WHERE SKU.org_id = :org_id` — covered by existing `idx_skus_org_barcode` (org_id, barcode). The org_id prefix is useful even without barcode filter.
- Count subquery: same filters, EXPLAIN ANALYZE expected < 50ms for orgs with < 50k plans.
- Add index `idx_distribution_plans_year_week` on `(year, week_number)` if filtering performance is slow in production — defer until measured.

### Frontend

- `staleTime: 30_000` — avoids re-fetch on tab switch for 30s.
- `keepPreviousData` — prevents table flash between filter changes.
- Page size 50 rows — no virtualisation needed.
- No client-side sort — avoids loading all pages.

---

## Testing Strategy

### Backend Unit Tests

```python
# test_stock_repository.py
class TestListPlansWithJoin:
    async def test_returns_platform_name_and_sku_barcode(self, db_session, ...):
        # Create plan with known platform + sku
        # Call list_plans
        # Assert result[0]["platform_name"] == "Wildberries"
        # Assert result[0]["sku_barcode"] == "1234567890"

    async def test_platform_filter_narrows_results(self, db_session, ...):
        # Create plans for 2 platforms
        # Filter by platform_id of platform A
        # Assert only platform A plans returned

    async def test_pagination_offset_correct(self, db_session, ...):
        # Create 5 plans, request page=2 size=2
        # Assert 2 items returned, offset respected

    async def test_cross_tenant_isolation_via_join(self, db_session, ...):
        # Org A plan, query as Org B → empty list
```

### Backend Schema Tests

```python
# test_stock_service.py
class TestListDistributionPlansService:
    async def test_returns_distribution_plan_rows_with_names(self, ...):
        # Mock repository to return dicts with platform_name + sku_barcode
        # Assert service constructs DistributionPlanRow correctly
```

### Frontend Component Tests (React Testing Library)

```typescript
// DistributionTable.test.tsx
test('renders platform_name column', () => {
    render(<DistributionTable data={[mockRow]} ... />)
    expect(screen.getByText('Wildberries')).toBeInTheDocument()
})

test('hides delete column for viewer role', () => {
    render(<DistributionTable canDelete={false} ... />)
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument()
})

// UploadPlanButton.test.tsx
test('shows error count on upload with partial errors', async () => {
    server.use(rest.post('/stock/distribution-plan',
        (_, res, ctx) => res(ctx.json({ imported: 2, errors: [{ row: 3, field: 'sku_barcode', message: 'not found' }] }))
    ))
    // Upload a file, verify "2 rows imported" and error list visible
})

// DistributionFilters.test.tsx
test('reset clears week and year', () => {
    // Render with week=12, year=2026
    // Click Reset
    // Assert onChange called with { week: undefined, year: undefined, page: 1 }
})
```

### E2E Tests (httpx)

```python
# test_stock_api.py — append to TestListDistributionPlans
async def test_list_returns_platform_name_and_sku_barcode(client, manager_user, ...):
    # Create plan with known sku + platform
    # GET /distribution-plan
    # Assert items[0].platform_name and items[0].sku_barcode present

async def test_list_filter_by_week_returns_correct_rows(client, manager_user, ...):
    # Create plans for week 10 and week 20
    # GET ?week_number=10
    # Assert only week 10 rows returned
```

---

## Migration Required?

**No new migration.** Only schema (Pydantic) and query (repository) changes. The database table `distribution_plans` is unchanged.
