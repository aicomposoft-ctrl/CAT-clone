# Implementation Checklist — Alert Config UI

## Pre-Implementation

- [ ] SPARC docs reviewed (PRD, Spec, Architecture, Pseudocode, Refinement)
- [ ] Existing `src/api/alerts.ts` read
- [ ] Existing `src/pages/Alerts/index.tsx` read
- [ ] Existing `src/api/catalog.ts` (skusApi, platformsApi) checked

## Implementation Tasks

### Step 1: API Client
- [ ] Add `AlertConfig`, `AlertConfigPage`, `AlertConfigCreateRequest`, `AlertConfigUpdateRequest`, `AlertCheckResult` types to `src/api/alerts.ts`
- [ ] Add `alertConfigsApi` object (list, create, update, remove, check)
- [ ] Verify existing `alertsApi` (events) is not broken

### Step 2: Hooks
- [ ] Create `src/pages/Alerts/hooks/useAlertConfigs.ts`
  - [ ] `useQuery` for list with pagination
  - [ ] `createMutation` with cache invalidation
  - [ ] `updateMutation` with optimistic update for is_active toggle
  - [ ] `removeMutation` with cache invalidation
- [ ] Create `src/pages/Alerts/hooks/useAlertCheck.ts`
  - [ ] `useMutation` for POST /check
  - [ ] 60s cooldown with second-level countdown

### Step 3: AlertConfigModal
- [ ] Create `src/pages/Alerts/components/AlertConfigModal.tsx`
  - [ ] Form with Ant Design Form
  - [ ] alert_type Select (disabled in edit mode)
  - [ ] sku_id Select with search (disabled in edit mode)
  - [ ] platform_id Select (disabled in edit mode)
  - [ ] threshold: Slider + InputNumber, synced, visible only for content_drop
  - [ ] email_recipients: Select[mode=tags] with email validation
  - [ ] is_active Switch
  - [ ] Pre-fill form in edit mode
  - [ ] Omit threshold from payload when alert_type === 'oss'

### Step 4: AlertConfigTable
- [ ] Create `src/pages/Alerts/components/AlertConfigTable.tsx`
  - [ ] Columns: Тип (Tag), Охват (SKU+Platform names), Порог, Получатели, Активен (Switch), Действия
  - [ ] Fetch skuMap and platformMap from React Query cache
  - [ ] Switch triggers PATCH with optimistic update
  - [ ] Edit/Delete buttons hidden for viewer
  - [ ] Pagination
  - [ ] Empty state text

### Step 5: AlertCheckButton
- [ ] Create `src/pages/Alerts/components/AlertCheckButton.tsx`
  - [ ] 60s cooldown timer (interval, cleanup)
  - [ ] Loading state during POST
  - [ ] Success message with events_created + emails_sent
  - [ ] 429 error handling

### Step 6: AlertConfigTab
- [ ] Create `src/pages/Alerts/components/AlertConfigTab.tsx`
  - [ ] Toolbar: "+ Добавить" (canManage) + AlertCheckButton (canCheck)
  - [ ] AlertConfigTable
  - [ ] Modal state management (open/close, create/edit mode)
  - [ ] Delete confirmation modal

### Step 7: AlertEventTab
- [ ] Create `src/pages/Alerts/components/AlertEventTab.tsx`
  - [ ] Move all existing event logic from `index.tsx`
  - [ ] No functional changes

### Step 8: Update index.tsx
- [ ] Replace content with Tabs component
- [ ] Tab 1: "События" → AlertEventTab
- [ ] Tab 2: "Конфигурации" → AlertConfigTab
- [ ] Preserve Title "Алерты"

## Testing

- [ ] Unit: AlertConfigModal — threshold visibility
- [ ] Unit: AlertConfigModal — email validation
- [ ] Unit: AlertConfigModal — edit mode disabled fields
- [ ] Unit: AlertConfigTable — RBAC button visibility
- [ ] Unit: AlertCheckButton — cooldown countdown
- [ ] Integration: full create flow with MSW mock
- [ ] Integration: delete with confirmation
- [ ] Integration: viewer sees read-only table
- [ ] Regression: Events tab still works

## Quality Gates

- [ ] `org_id` not hardcoded anywhere in frontend (inferred from JWT by backend)
- [ ] No `console.log` in production code
- [ ] All API errors handled with user-facing messages
- [ ] Ant Design components used consistently (no custom HTML tables)
- [ ] TypeScript: no `any` types added
- [ ] All new files follow `PascalCase` component naming
- [ ] React Query keys follow existing pattern: `['alert-configs', {...}]`
