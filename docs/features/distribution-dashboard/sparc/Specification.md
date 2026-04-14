# Specification: Distribution Dashboard

**Feature:** `distribution-dashboard`
**Date:** 2026-04-01

---

## API Changes (Backend)

### Extended DistributionPlanRow Schema

Add `platform_name` and `sku_barcode` to the schema for display:

```python
# services/api/app/stock/schemas.py
class DistributionPlanRow(BaseModel):
    id: UUID
    sku_id: UUID
    platform_id: UUID
    platform_name: str        # NEW — from JOIN with platforms
    sku_barcode: str          # NEW — from JOIN with skus
    group_name: str
    plan_tt_count: int
    week_number: int
    year: int

    model_config = {"from_attributes": False}  # uses dict mapping now
```

### Updated Repository Query

`repository.list_plans()` must be updated to JOIN platforms and skus:

```python
# services/api/app/stock/repository.py
async def list_plans(db, org_id, platform_id, week_number, year, limit, offset):
    stmt = (
        select(
            DistributionPlan,
            Platform.name.label("platform_name"),
            SKU.barcode.label("sku_barcode"),
        )
        .join(SKU, DistributionPlan.sku_id == SKU.id)
        .join(Platform, DistributionPlan.platform_id == Platform.id)
        .where(SKU.org_id == org_id)
    )
    # apply optional filters...
    # return list of row dicts (not ORM objects) to include joined fields
```

Returns `list[dict]` (not ORM objects) since joined fields cannot come from `from_attributes`.

Service must construct `DistributionPlanRow` from dicts:
```python
rows = [DistributionPlanRow(**r) for r in items]
```

---

## Frontend API Client

```typescript
// services/frontend/src/api/stock.ts

export interface DistributionPlanRow {
  id: string
  sku_id: string
  platform_id: string
  platform_name: string
  sku_barcode: string
  group_name: string
  plan_tt_count: number
  week_number: number
  year: number
}

export interface DistributionPlanPage {
  items: DistributionPlanRow[]
  total: number
  page: number
  size: number
}

export interface UploadResult {
  imported: number
  errors: Array<{ row: number; field: string; message: string }>
}

export interface DistributionFilters {
  platform_id?: string
  week_number?: number
  year?: number
  page?: number
  size?: number
}

export const distributionApi = {
  list: (filters: DistributionFilters): Promise<DistributionPlanPage> =>
    apiClient.get('/stock/distribution-plan', { params: filters }).then(r => r.data),

  deletePlan: (id: string): Promise<void> =>
    apiClient.delete(`/stock/distribution-plan/${id}`),

  uploadCSV: (file: File): Promise<UploadResult> => {
    const form = new FormData()
    form.append('file', file)
    return apiClient.post('/stock/distribution-plan', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },
}
```

---

## Filter Component Specification

```
DistributionFilters props:
  value: DistributionFilters
  onChange: (filters: DistributionFilters) => void

Controls:
  - Week: InputNumber, min=1, max=53, placeholder="Week"
  - Year: Select, options=[currentYear-1, currentYear, currentYear+1]
  - Platform: Select, options derived from unique platform_name in current data
             (populated after first load — show all if no data yet)
  - Reset button: clears week, year, platform_id; resets to defaults
```

---

## Table Column Specification

| Column | Source Field | Width | Sortable |
|--------|-------------|-------|---------|
| SKU Barcode | sku_barcode | 160px | No |
| Platform | platform_name | 140px | No |
| Group | group_name | 180px | No |
| Plan Qty | plan_tt_count | 100px | No |
| Week | week_number | 70px | No |
| Year | year | 70px | No |
| Actions | — | 60px | No (manager only) |

Pagination: `showSizeChanger=false`, `showTotal=(total) => \`${total} rows\``

---

## Upload Modal Specification

```
Trigger: "Upload Plan" button (primary, top-right of page header)
         Only visible to manager/admin roles

Modal content:
  - Ant Design Dragger upload zone ("Click or drag CSV file here")
  - Accepted: .csv, text/csv only
  - Max: 5MB (enforced client-side before POST)
  - On upload success:
      Show result card:
        - "✓ N rows imported"
        - If errors: expandable list of row errors (field, message, row number)
  - "Done" button closes modal and refreshes table

Error handling:
  - HTTP 422 (file-level): show detail message in modal
  - HTTP 500: show generic "Upload failed — try again"
```

---

## URL Query Param Mapping

```
?week=12&year=2026&platform_id=<uuid>&page=2

Defaults: week=currentWeek, year=currentYear, page=1
On mount: read params from URL, initialise filters
On filter change: push updated params to URL (replace, not push)
```

---

## RBAC Enforcement (Frontend)

```typescript
const { role } = useAuth()
const canEdit = role === 'manager' || role === 'admin'

// Conditional render
{canEdit && <Button onClick={openUpload}>Upload Plan</Button>}
{canEdit && <Popconfirm onConfirm={() => deleteMutation.mutate(row.id)}>
  <DeleteOutlined />
</Popconfirm>}
```

---

## Error States

| Scenario | UI Treatment |
|----------|-------------|
| API fetch fails | Red Alert: "Failed to load plans — retry" with Retry button |
| Delete fails | Toast error: "Failed to delete — try again" |
| Upload 422 (bad file) | Inline error in upload modal |
| Upload 500 | Toast error: "Server error — contact support" |
| Empty result | Empty state: "No plans found for this filter. Upload a CSV to get started." |
| Token expired (401) | Redirect to /login |
