# Architecture — Web Dashboard
> Feature: web-dashboard | SPARC Phase 5 | CAT Project

---

## 1. Frontend Architecture Overview

**Style:** Single-Page Application (SPA) — React 18 + TypeScript
**Pattern:** Feature-based folder structure, React Query for server state, Zustand for UI state
**Communication:** REST API via Axios with JWT interceptor
**UI:** Ant Design 5 components, Apache ECharts for charts

---

## 2. Component Architecture

```
services/frontend/src/
├── pages/
│   ├── Auth/
│   │   ├── LoginPage.tsx
│   │   └── hooks/useLogin.ts
│   ├── Dashboard/
│   │   ├── index.tsx              # Main dashboard
│   │   ├── components/
│   │   │   ├── KpiCard.tsx        # Stat cards
│   │   │   ├── RedZoneTable.tsx   # Top-5 low score SKUs
│   │   │   └── AlertsFeedWidget.tsx
│   │   └── hooks/useDashboard.ts
│   ├── Content/
│   │   ├── index.tsx              # Content score table
│   │   ├── components/
│   │   │   ├── ContentScoreTable.tsx
│   │   │   ├── ContentScoreFilters.tsx
│   │   │   └── ContentDrillDrawer.tsx  # Side-by-side comparison
│   │   └── hooks/useContentScores.ts
│   ├── Stock/
│   │   ├── index.tsx
│   │   ├── components/
│   │   │   ├── DistributionTable.tsx
│   │   │   └── DistributionHeatmap.tsx
│   │   └── hooks/useDistribution.ts
│   ├── Prices/
│   │   ├── index.tsx
│   │   ├── components/
│   │   │   ├── PricesTable.tsx
│   │   │   └── PriceTrendDrawer.tsx
│   │   └── hooks/usePrices.ts
│   ├── Reviews/
│   │   ├── index.tsx
│   │   ├── components/
│   │   │   ├── SentimentChart.tsx
│   │   │   ├── ReviewsList.tsx
│   │   │   └── SentimentTrendChart.tsx
│   │   └── hooks/useReviews.ts
│   ├── Alerts/
│   │   ├── index.tsx
│   │   ├── components/
│   │   │   └── AlertsTable.tsx
│   │   └── hooks/useAlerts.ts
│   └── Settings/
│       ├── SKUs/
│       │   ├── index.tsx
│       │   ├── components/
│       │   │   ├── SKUTable.tsx
│       │   │   ├── SKUFormDrawer.tsx
│       │   │   └── BulkUploadModal.tsx
│       │   └── hooks/useSKUs.ts
│       └── Profile/
│           └── index.tsx
├── components/                    # Shared
│   ├── AppLayout.tsx              # Ant Design Layout with sidebar nav
│   ├── ProtectedRoute.tsx         # Auth guard
│   ├── ScoreBadge.tsx             # Green/yellow/red score display
│   ├── ExportButton.tsx           # Reusable export trigger
│   └── ErrorBoundary.tsx
├── api/
│   ├── client.ts                  # Axios instance + JWT interceptor
│   ├── auth.ts                    # login, logout, refresh
│   ├── content.ts                 # getContentScores, getContentDrilldown
│   ├── stock.ts                   # getDistribution
│   ├── prices.ts                  # getPrices, getPriceHistory
│   ├── reviews.ts                 # getReviews, getSentiment
│   ├── alerts.ts                  # getAlerts, acknowledgeAlert
│   ├── reports.ts                 # triggerExport (content, stock, reviews, prices)
│   └── skus.ts                    # createSKU, updateSKU, deleteSKU, bulkUpload
├── hooks/
│   ├── useAuth.ts                 # Auth state, token management
│   └── useOrg.ts                  # Current org context
├── store/
│   └── authStore.ts               # Zustand: user, tokens, org
├── types/
│   ├── api.ts                     # Response types matching backend Pydantic schemas
│   ├── content.ts
│   ├── stock.ts
│   ├── prices.ts
│   ├── reviews.ts
│   └── alerts.ts
└── App.tsx                        # Router + QueryClientProvider
```

---

## 3. Routing

```typescript
// React Router v6 routes
/login                    → LoginPage (public)
/dashboard                → DashboardPage (protected)
/content                  → ContentPage (protected)
/stock                    → StockPage (protected)
/prices                   → PricesPage (protected)
/reviews                  → ReviewsPage (protected)
/alerts                   → AlertsPage (protected)
/settings/skus            → SKUSettingsPage (admin + manager only)
/settings/profile         → ProfilePage (protected)
*                         → redirect to /dashboard
```

---

## 4. State Management

```
React Query (server state)      ← API data, caching, background refresh
Zustand (auth store)            ← user object, access token, org_id
React useState (local UI)       ← filters, pagination, drawer open/closed
URL params (filter persistence) ← ?platform=wb&score_max=50&date=2026-04-01
```

**React Query config:**
- `staleTime`: 5 minutes for most queries
- `refetchInterval`: 5 minutes on Dashboard KPIs
- `retry`: 1 (fast fail on 4xx, retry on 5xx)

---

## 5. API Client Design

```typescript
// api/client.ts
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api/v1',
  timeout: 30000,
})

// Request interceptor: inject access token
apiClient.interceptors.request.use(config => {
  const token = authStore.getState().accessToken
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Response interceptor: handle 401 with token refresh
// Uses single refresh promise to handle concurrent 401s (race condition fix)
let refreshPromise: Promise<string> | null = null

apiClient.interceptors.response.use(
  res => res,
  async error => {
    if (error.response?.status === 401 && !error.config._retry) {
      if (!refreshPromise) {
        refreshPromise = refreshAccessToken().finally(() => { refreshPromise = null })
      }
      const newToken = await refreshPromise
      error.config._retry = true
      error.config.headers.Authorization = `Bearer ${newToken}`
      return apiClient(error.config)
    }
    return Promise.reject(error)
  }
)
```

---

## 6. Authentication Flow

```
1. User enters email + password on /login
2. POST /api/v1/auth/login → { access_token, refresh_token, user }
3. access_token stored in Zustand (in-memory)
4. refresh_token stored in sessionStorage (per-tab)
5. On 401: auto-refresh via interceptor (transparent to components)
6. On logout: clear Zustand + sessionStorage, redirect /login
```

---

## 7. Ant Design Layout

```typescript
// Sidebar navigation items
const navItems = [
  { key: '/dashboard',  icon: <DashboardOutlined />, label: 'Дашборд' },
  { key: '/content',    icon: <FileTextOutlined />,  label: 'Контент' },
  { key: '/stock',      icon: <ShopOutlined />,      label: 'Дистрибуция' },
  { key: '/prices',     icon: <DollarOutlined />,    label: 'Цены' },
  { key: '/reviews',    icon: <StarOutlined />,       label: 'Отзывы' },
  { key: '/alerts',     icon: <BellOutlined />,      label: 'Алерты', badge: alertCount },
  { key: '/settings',   icon: <SettingOutlined />,   label: 'Настройки' },
]
```

---

## 8. Charts (ECharts)

All charts via `echarts-for-react` wrapper:

| Chart | Location | Type |
|-------|----------|------|
| Content score trend | Drill-down drawer | Line |
| Sentiment distribution | Reviews page | Pie + Bar |
| Sentiment trend | Reviews Trend tab | Line (multi-series) |
| Distribution heatmap | Stock Heatmap tab | Heatmap |
| Price history | Price drill-down | Line (multi-series) |
| Dashboard KPI trend | KPI cards | Sparkline |

**ECharts resize rule:** call `chart.resize()` on:
- window `resize` event
- Ant Design drawer `afterOpenChange`
- Sider collapse event

---

## 9. Docker / Build

```dockerfile
# services/frontend/Dockerfile (multi-stage)
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

Nginx proxies `/api/v1/*` to the `api` service, serves static files from `/dist`.

---

## 10. Environment Variables

```bash
# services/frontend/.env.example
VITE_API_URL=http://localhost:8000/api/v1   # Dev; prod uses relative /api/v1
VITE_APP_TITLE=CAT — Commerce Analytics
```
