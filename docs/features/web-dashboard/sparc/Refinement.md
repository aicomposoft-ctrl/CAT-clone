# Refinement — Web Dashboard
> Feature: web-dashboard | SPARC Phase 6 | CAT Project

---

## 1. Edge Cases Matrix

| Scenario | Input | Expected Behavior | Handling |
|----------|-------|-------------------|----------|
| No data for org | New org, 0 SKUs | Dashboard shows empty state with "Add SKU" CTA | `EmptyState` component with action button |
| Score = null | SKU scraped but scoring failed | Show "-" instead of 0, tooltip "Score not available" | Conditional render |
| Reference image missing | SKU has no reference | Drill-down shows placeholder image + "Upload reference" link | Fallback image + link to settings |
| Very long SKU name | >100 chars | Truncate with `...` in table cells, full name in tooltip | `ellipsis` prop on Ant Design Table |
| 0% distribution | fact_tt = 0, plan_tt > 0 | Coverage = 0% shown in red, not blank | Explicit 0 display |
| Platform returns 404 | Scraper couldn't access URL | Row with `status: "unavailable"` instead of scores | Status badge |
| Concurrent 401s | Multiple requests fire when token expires | Only one refresh request sent, all others queue | refreshPromise singleton |
| Large CSV upload | 10,000+ row file | Validate first 10,000 rows, reject file if >10,000 | Size check + row count check |
| Export timeout | Large dataset, slow generation | Loading spinner, 60s timeout, then error toast | Axios `timeout: 60000` for export |
| Chart resize in closed drawer | Drawer not visible during mount | Call chart.resize() only in `afterOpenChange` callback | Event-based resize |
| All scores green | No issues | Positive KPI card with trend | Normal render, no special handling needed |
| User has viewer role | Tries to access /settings/skus | 403 from API + ProtectedRoute redirects | Role-based route guard |

---

## 2. Testing Strategy

### Unit Tests (Jest + React Testing Library)

Coverage target: 80%

**ScoreBadge component:**
```typescript
test('renders green badge for score >= 80', () => {
  render(<ScoreBadge score={85} />)
  expect(screen.getByText('85%')).toHaveStyle('color: #52c41a')
})

test('renders yellow badge for score 50-79', () => {
  render(<ScoreBadge score={65} />)
  expect(screen.getByText('65%')).toHaveStyle('color: #faad14')
})

test('renders red badge for score < 50', () => {
  render(<ScoreBadge score={32} />)
  expect(screen.getByText('32%')).toHaveStyle('color: #ff4d4f')
})

test('renders dash for null score', () => {
  render(<ScoreBadge score={null} />)
  expect(screen.getByText('-')).toBeInTheDocument()
})
```

**filtersToParams utility:**
```typescript
test('converts filter object to URLSearchParams', () => {
  const params = filtersToParams({ platform_id: 'abc', score_max: 50, date: null })
  expect(params.get('platform_id')).toBe('abc')
  expect(params.get('score_max')).toBe('50')
  expect(params.has('date')).toBe(false)  // null excluded
})
```

**getScoreStyle utility:**
```typescript
test.each([
  [85, 'green'],
  [65, 'yellow'],
  [30, 'red'],
])('score %d maps to %s', (score, expected) => {
  expect(getScoreStyle(score).label).toBe(expected)
})
```

### Integration Tests (MSW + React Query)

**ContentScoreTable renders data:**
```typescript
test('renders content scores from API', async () => {
  server.use(
    rest.get('/api/v1/content/scores', (req, res, ctx) =>
      res(ctx.json({ items: mockScores, total: 5, page: 1, page_size: 50 }))
    )
  )
  render(<ContentPage />)
  await screen.findByText('Индейка Индилайт')
  expect(screen.getAllByRole('row')).toHaveLength(6) // 5 data + header
})
```

**Alert acknowledge updates UI:**
```typescript
test('acknowledge button updates alert status', async () => {
  server.use(
    rest.patch('/api/v1/alerts/:id/acknowledge', (req, res, ctx) =>
      res(ctx.json({ ...mockAlert, is_acknowledged: true }))
    )
  )
  render(<AlertsPage />)
  await userEvent.click(screen.getByRole('button', { name: 'Acknowledge' }))
  await waitFor(() => expect(screen.queryByText('New')).not.toBeInTheDocument())
})
```

### E2E Tests (Playwright)

**Critical paths — 100% coverage required:**

```gherkin
Scenario: Full login → dashboard → content drill-down flow
  Given API mock server is running
  When user navigates to /login
  And enters valid credentials
  Then redirected to /dashboard
  And KPI cards are visible
  When user navigates to /content
  And clicks on first red-zone SKU
  Then drill-down drawer opens with comparison
  And historical chart is rendered

Scenario: Excel export flow
  When user is on /content page
  And clicks "Export to Excel"
  And selects date in modal
  And clicks "Download"
  Then file download is triggered
  And toast "Export complete" appears

Scenario: Session expiry transparent refresh
  Given user is on /content page
  And access token expires (mocked)
  When user applies a filter
  Then token is auto-refreshed
  And content loads without redirect to /login
```

---

## 3. Performance Optimizations

### React Query Caching
```typescript
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,     // 5 minutes — no refetch on every mount
      gcTime: 10 * 60 * 1000,        // 10 minutes in cache after unmount
      retry: 1,
    },
  },
})
```

### Virtual Scroll for Large Tables
```typescript
// For content table with 1000+ rows: use Ant Design Table with virtual scroll
<Table
  virtual
  scroll={{ y: 600 }}
  dataSource={scores}
  rowKey="id"
/>
```

### Code Splitting (lazy routes)
```typescript
const ContentPage = lazy(() => import('./pages/Content'))
const ReviewsPage = lazy(() => import('./pages/Reviews'))
// Each domain page loaded on demand — Dashboard loads fast
```

### ECharts Dispose on Unmount
```typescript
// Prevent memory leaks when drawers close
useEffect(() => {
  return () => chart.current?.dispose()
}, [])
```

### Memoization
```typescript
// Expensive heatmap transformation
const heatmapData = useMemo(
  () => buildHeatmapData(distributionRows),
  [distributionRows]
)
```

---

## 4. Security Hardening

### Token Storage
- Access token: Zustand in-memory only (cleared on tab close)
- Refresh token: sessionStorage (per-tab, not shared)
- Never in localStorage (XSS risk)

### XSS Prevention
- All review text rendered via `{text}` JSX interpolation (auto-escaped)
- Never use `dangerouslySetInnerHTML` for user content
- CSP header from Nginx: `default-src 'self'; script-src 'self'`

### Role-Based Route Guard
```typescript
// components/ProtectedRoute.tsx
const ProtectedRoute: React.FC<{ allowedRoles?: Role[] }> = ({ allowedRoles }) => {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" />
  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/dashboard" />
  }
  return <Outlet />
}
```

---

## 5. Accessibility (a11y)

- Score badges: don't use color alone — always include % value text
- Alert type icons: always have `aria-label`
- Tables: `<caption>` for screen readers
- Modals/Drawers: focus trap on open, return focus on close
- Keyboard nav: all filters accessible via Tab, charts have text summary

---

## 6. Technical Debt Items

| Item | Risk | Planned |
|------|------|---------|
| Polling (5 min) instead of WebSocket | Stale alerts for 5 min | v2: WebSocket via FastAPI |
| No offline support | Blank screen on network loss | v2: React Query offline mode |
| Mobile layout not implemented | Unusable on phone | v2 explicitly |
| Alert config UI missing | Users must configure alerts via API | v2: AlertRulesPage |
| No Sentry integration | JS errors silent | Sprint 2: add @sentry/react |
