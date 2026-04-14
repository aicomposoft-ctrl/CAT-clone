# Phase 4 Review Report — frontend-prices-reviews

**Date:** 2026-04-05
**Feature:** frontend-prices-reviews
**Reviewers:** 5 parallel agents (brutal-honesty-review)

---

## Summary

| Agent | Focus | Score | Blockers |
|-------|-------|-------|----------|
| Agent 1 | Code Quality (Linus mode) | 74/100 | 3 Critical → Fixed |
| Agent 2 | Security (OWASP) | 82/100 | 2 Major → Fixed |
| Agent 3 | Multi-tenant Isolation | 68/100 | 2 Critical → Fixed |
| Agent 4 | Performance (N+1, indexes) | 71/100 | 2 Critical → Fixed |
| Agent 5 | Test Coverage | 65/100 | 0 blocking (no frontend unit tests in scope) |

**All Critical and Major issues fixed before merge.**

---

## Agent 1 — Code Quality

### CRITICAL (fixed)

**C-1: `cleanParams` duplicated across `prices.ts` and `reviews.ts`**
Both files contained identical utility function. Extracted to `api/utils.ts` and both files import from there.

**C-2: `skuId!` non-null assertion without explicit guard**
`queryFn: () => reviewsApi.summary(skuId!, ...)` — if `enabled` guard changes, TypeScript silently passes `undefined` to the API. Fixed: explicit `if (!skuId) throw new Error('skuId required')` in all 7 queryFn callbacks across both pages.

**C-3: `summaryColumns` and `historyColumns` defined inside component**
Columns had no state closure but were recreated on every render, causing Table to see new column references. Fixed: moved both to module scope (outside component).

### MAJOR (fixed)

**M-1: `DEFAULT_RANGE` as module-level constant**
`dayjs()` evaluated once at module import time, causing stale date on long-running sessions. Fixed: `useState(() => [dayjs().subtract(29, 'day'), dayjs()])` initializer.

**M-2: Missing `useMemo` / `import useMemo`**
`buildSentimentPie` and `buildTrendChart` called inline in JSX, rebuilding on every render. Fixed: `useMemo` with `[stats]` dependency.

### MINOR (deferred)

- M-3: No TypeDoc comments on exported chart builder functions.
- M-4: `PAGE_SIZE = 100` not exposed as configurable prop.

---

## Agent 2 — Security (OWASP)

### MAJOR (fixed)

**MAJOR-1: ECharts `formatter` output treated as HTML — XSS risk**
`buildTrendChart` used `formatter: (params) => ...` which ECharts renders as HTML. The formatter concatenated `p.name` (backend-controlled date string) without escaping. Fixed: `Array.isArray` guard + `escHtml()` applied to all interpolated values. `escHtml` extracted to shared `api/utils.ts`.

**MAJOR-2: `review_text` rendered without untrusted-data annotation**
Review text is scraped from external platforms and is untrusted. Original code had no comment. Fixed: added `/** Scraped from external platforms — treat as untrusted. Never render as HTML. */` annotation in `api/reviews.ts`. Render code uses `{v}` (text node, not dangerouslySetInnerHTML).

### MINOR (confirmed safe)

- Pie chart uses `formatter: '{b}: {c}%'` — ECharts template string, no user data interpolated.
- `review_text` truncated at 200 chars with `title={v}` — both text nodes only, no innerHTML paths.

---

## Agent 3 — Multi-tenant Isolation

### CRITICAL (fixed)

**CRIT-1: Query cache keys missing `org_id`**
All 7 page-level React Query keys omitted `orgId`. When user A logs out and user B logs in to the same browser tab, stale data from `['reviews-summary', skuId, dateFrom, dateTo]` would be served to user B if their skuId matches. Fixed: `orgId = useAuthStore((s) => s.user?.org_id)` added to both pages, included in all query keys.

**CRIT-2: `clearAuth()` does not clear React Query cache**
On logout, `useAuthStore.clearAuth()` only cleared sessionStorage and Zustand state. React Query cache persisted, allowing a subsequent user on the same tab to see prior tenant's data until TTL expiry. Fixed:
- `setQueryClient()` export added to `authStore.ts`
- `main.tsx` calls `setQueryClient(queryClient)` after QueryClient creation
- `clearAuth()` calls `_queryClient?.clear()`

### CONFIRMED (no issue)

- Backend enforces `org_id` on all price/review endpoints — frontend isolation is defense in depth.
- SKUSelector also includes `orgId` in its cache key.

---

## Agent 4 — Performance

### CRITICAL (fixed)

**CRIT-1: O(n²) `buildHistoryChart` in `Prices/index.tsx`**
Original implementation called `lastIndexOf` inside a loop over platforms × dates. For 30 days × 10 platforms × 10 snapshots/day = 3,000 items, this is ~90,000 operations. Fixed: Map-based O(n) pre-processing: `Map<platform, Map<date, price>>` built in single pass.

**CRIT-2: ECharts option rebuilt on every render**
`buildHistoryChart(historyQuery.data?.items ?? [])` and `buildSentimentPie(stats)` / `buildTrendChart(stats)` called inline in JSX, forcing ECharts to diff against new option objects on every parent re-render. Fixed: `useMemo` with `[historyQuery.data]` and `[stats]` dependencies.

### MINOR (noted)

- M-1: `platformOptions` in Prices re-computed from `latestQuery.data` — already wrapped in `useMemo`, no issue.
- M-2: `latestColumns` in Prices re-computed when `cheapest_platform_id` changes — correct behavior, minimal cost.

---

## Agent 5 — Test Coverage

### Observations

Frontend unit/integration tests are out of scope for this feature iteration (backend BDD tests exist in `services/api/tests/`). The following frontend test stubs are recommended for Sprint 3:

- `Prices/index.test.tsx`: render with no SKU selected → Empty shown; mock `pricesApi.latest` → table renders with cheapest row highlighted.
- `Reviews/index.test.tsx`: render with no SKU → Empty; mock `reviewsApi.summary` → platform table renders; sentiment filter changes query key.
- `SKUSelector.test.tsx`: renders loading state; renders options from API; calls onChange with selected sku_id.

### Critical paths without tests (follow-up P2)

- Cross-tenant isolation: SKU from org A not visible after logout/login as org B (requires auth mock).
- `clearAuth()` clears React Query cache.

---

## Files Changed in Phase 4

| File | Change |
|------|--------|
| `services/frontend/src/api/utils.ts` | Added `escHtml()` utility |
| `services/frontend/src/pages/Prices/index.tsx` | Full rewrite with org_id keys, O(n) chart, useMemo, guards |
| `services/frontend/src/pages/Reviews/index.tsx` | Full rewrite with org_id keys, useMemo, guards, column hoisting |
| `services/frontend/src/store/authStore.ts` | Added `setQueryClient` + cache clear on logout |
| `services/frontend/src/main.tsx` | Added `setQueryClient(queryClient)` call |

---

## Verdict

**APPROVED FOR MERGE.** All Critical and Major issues resolved. TypeScript: 0 errors (`tsc --noEmit` clean). Minor issues documented as P2 follow-ups.
