# Architecture: Distribution Dashboard

**Feature:** `distribution-dashboard`
**Date:** 2026-04-01

---

## Component Hierarchy

```
pages/Distribution/
├── index.tsx                    # Route entry, layout, URL param sync
├── components/
│   ├── DistributionFilters.tsx  # Platform / Week / Year selectors
│   ├── DistributionTable.tsx    # Ant Design Table with delete controls
│   ├── UploadPlanButton.tsx     # CSV upload modal (Ant Design Upload)
│   └── PlanRowActions.tsx       # Delete icon + popconfirm per row
├── hooks/
│   ├── useDistributionPlans.ts  # React Query fetch + pagination
│   └── useDeletePlan.ts         # React Query mutation for DELETE
└── types.ts                     # Local TypeScript interfaces
```

---

## API Contracts (consumed)

### GET /api/v1/stock/distribution-plan

```
Query params:
  platform_id?: UUID
  week_number?: int (1-53)
  year?: int (2000-2100)
  page?: int (default 1)
  size?: int (default 50, max 200)

Response: {
  items: DistributionPlanRow[],
  total: int,
  page: int,
  size: int
}

DistributionPlanRow: {
  id: string (UUID)
  sku_id: string (UUID)
  platform_id: string (UUID)
  group_name: string
  plan_tt_count: int
  week_number: int
  year: int
}
```

**Note:** API returns `platform_id` UUID, not platform name. Dashboard needs a separate lookup for platform names OR the API needs to be extended to include `platform_name` in the row. **Decision: extend `DistributionPlanRow` schema to include `platform_name` (string) and `sku_barcode` (string) via JOIN — see Specification.md.**

### DELETE /api/v1/stock/distribution-plan/{id}

```
Response: 204 No Content
Error: 404 { detail: "PLAN_NOT_FOUND" }
```

### POST /api/v1/stock/distribution-plan

```
Body: multipart/form-data
  file: File (.csv, text/csv)

Response: {
  imported: int,
  errors: RowError[]
}
```

---

## State Management

```
URL query params (single source of truth for filters):
  ?platform_id=<uuid>&week=12&year=2026&page=1

React Query cache:
  queryKey: ['distribution-plans', filters]
  staleTime: 30s (plans change infrequently)
  
Local state (component only):
  - upload modal open/closed
  - delete loading state per row
```

---

## Routing

Route registered at `/distribution` in the main router.

```typescript
// App router
<Route path="/distribution" element={<DistributionPage />} />
```

Navigation link added to the main sidebar (Ant Design Menu).

---

## Data Flow

```
User changes filter
  → DistributionFilters emits onChange
  → index.tsx updates URL params
  → useDistributionPlans re-fetches with new params (React Query)
  → DistributionTable receives new data → renders

User clicks delete
  → PlanRowActions shows popconfirm
  → User confirms
  → useDeletePlan.mutate(id)
  → On success: invalidate ['distribution-plans'] query → table refetches
  → Toast: "Plan row deleted"

User uploads CSV
  → UploadPlanButton calls POST /distribution-plan
  → On success: show result (imported count + errors)
  → invalidate ['distribution-plans'] → table refetches
```

---

## API Schema Extension Required

`DistributionPlanRow` in `services/api/app/stock/schemas.py` must be extended with:
- `platform_name: str` — from JOIN with platforms
- `sku_barcode: str` — from JOIN with skus

`repository.list_plans()` must be updated to include these joined fields.

This avoids N+1 lookups in the frontend for display names.

---

## File Locations

| File | Path |
|------|------|
| Page component | `services/frontend/src/pages/Distribution/index.tsx` |
| API client | `services/frontend/src/api/stock.ts` |
| React Query hooks | `services/frontend/src/pages/Distribution/hooks/` |
| Components | `services/frontend/src/pages/Distribution/components/` |
| Types | `services/frontend/src/pages/Distribution/types.ts` |
| Backend schema | `services/api/app/stock/schemas.py` |
| Backend repository | `services/api/app/stock/repository.py` |
