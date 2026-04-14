# Architecture — Alert Config UI

## 1. Overview

Чисто frontend-фича. Backend API полностью готов. Изменения затрагивают:

```
services/frontend/src/
├── api/alerts.ts              ← добавить 4 новых метода
├── pages/Alerts/
│   ├── index.tsx              ← добавить Tabs, переструктурировать
│   └── components/            ← 4 новых компонента
└── (нет изменений в backend)
```

## 2. Существующая структура (до фичи)

```
pages/Alerts/
└── index.tsx        ← монолит: таблица событий + фильтры + acknowledge
    
api/alerts.ts        ← AlertEvent тип + list() + acknowledge()
```

## 3. Целевая структура (после фичи)

```
pages/Alerts/
├── index.tsx                     ← Tabs: [События | Конфигурации]
├── components/
│   ├── AlertEventTab.tsx          ← вынесенное содержимое текущего index.tsx
│   ├── AlertConfigTab.tsx         ← новая вкладка целиком
│   ├── AlertConfigTable.tsx       ← таблица с колонками
│   ├── AlertConfigModal.tsx       ← форма create/edit в Modal
│   └── AlertCheckButton.tsx       ← кнопка + cooldown логика
└── hooks/
    ├── useAlertConfigs.ts          ← React Query + mutations
    └── useAlertCheck.ts            ← mutation + 60s cooldown state

api/alerts.ts                      ← + AlertConfig types + configsApi object
```

## 4. Data Flow

```
AlertConfigTab
  ├── useAlertConfigs() → GET /alerts/configs → AlertConfigTable
  │                                              └── row actions → openModal(edit) / confirmDelete()
  ├── AlertConfigActions
  │   ├── "+ Добавить" → openModal(create)
  │   └── AlertCheckButton → POST /alerts/check → показать результат
  └── AlertConfigModal (create | edit)
        ├── при mount: load skus + platforms (useQuery, staleTime=5min)
        ├── форма Antd Form + Controller
        ├── submit → configsApi.create() | configsApi.update()
        └── onSuccess → invalidate ['alert-configs'] + close modal
```

## 5. API Client Design

```typescript
// src/api/alerts.ts — новый раздел

export const alertConfigsApi = {
  list: (params?: { page?: number; size?: number }) =>
    apiClient.get<AlertConfigPage>('/alerts/configs', { params }).then(r => r.data),

  create: (data: AlertConfigCreateRequest) =>
    apiClient.post<AlertConfig>('/alerts/configs', data).then(r => r.data),

  update: (id: string, data: AlertConfigUpdateRequest) =>
    apiClient.patch<AlertConfig>(`/alerts/configs/${id}`, data).then(r => r.data),

  remove: (id: string) =>
    apiClient.delete(`/alerts/configs/${id}`),

  check: () =>
    apiClient.post<AlertCheckResult>('/alerts/check').then(r => r.data),
}
```

## 6. Hook Design

```typescript
// hooks/useAlertConfigs.ts

export function useAlertConfigs(page = 1) {
  const queryClient = useQueryClient()
  const queryKey = ['alert-configs', { page }]

  const query = useQuery({
    queryKey,
    queryFn: () => alertConfigsApi.list({ page, size: 50 }),
    staleTime: 2 * 60 * 1000,
  })

  const createMutation = useMutation({
    mutationFn: alertConfigsApi.create,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alert-configs'] }),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: AlertConfigUpdateRequest }) =>
      alertConfigsApi.update(id, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alert-configs'] }),
  })

  const removeMutation = useMutation({
    mutationFn: alertConfigsApi.remove,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alert-configs'] }),
  })

  return { query, createMutation, updateMutation, removeMutation }
}
```

## 7. Form Architecture (AlertConfigModal)

Используется Ant Design Form c `useForm()`:

```
<Form>
  <Form.Item name="alert_type">
    <Select onChange={handleTypeChange} disabled={isEdit} />
  </Form.Item>
  
  <Form.Item name="sku_id">
    <Select showSearch allowClear disabled={isEdit}
            options={skus.map(s => ({ value: s.id, label: s.name }))} />
  </Form.Item>
  
  <Form.Item name="platform_id">
    <Select allowClear disabled={isEdit}
            options={platforms.map(p => ({ value: p.id, label: p.name }))} />
  </Form.Item>
  
  {/* Conditionally rendered */}
  {alertType === 'content_drop' && (
    <Form.Item name="threshold" rules={[{ required: true }]}>
      <Row>
        <Slider min={0} max={100} style={{ flex: 1 }} />
        <InputNumber min={0} max={100} style={{ width: 60 }} />
      </Row>
    </Form.Item>
  )}
  
  <Form.Item name="email_recipients"
             rules={[{ required: true, min: 1 }]}>
    <Select mode="tags" tokenSeparators={[',']}
            validator={validateEmails} />
  </Form.Item>
  
  <Form.Item name="is_active" valuePropName="checked">
    <Switch />
  </Form.Item>
</Form>
```

## 8. AlertCheckButton Cooldown

```typescript
// hooks/useAlertCheck.ts

export function useAlertCheck() {
  const [cooldownUntil, setCooldownUntil] = useState<number>(0)
  
  const mutation = useMutation({
    mutationFn: alertConfigsApi.check,
    onSuccess: (data) => {
      setCooldownUntil(Date.now() + 60_000)
      message.success(`Создано событий: ${data.events_created}, отправлено писем: ${data.emails_sent}`)
    },
    onError: (err) => {
      const status = (err as AxiosError).response?.status
      if (status === 429) {
        message.warning('Слишком много запросов, подождите 1 минуту')
      } else {
        message.error('Ошибка при запуске проверки')
      }
    }
  })

  const isCooling = Date.now() < cooldownUntil

  return { run: mutation.mutate, isLoading: mutation.isPending, isCooling }
}
```

## 9. No Backend Changes

Фича не требует изменений в:
- `services/api/` — все endpoints уже реализованы
- `services/collector/` — не затрагивается
- БД / миграции — не нужны
- Docker Compose — не нужны

## 10. File Change Summary

| File | Action | Scope |
|------|--------|-------|
| `src/api/alerts.ts` | Edit | Добавить AlertConfig types + alertConfigsApi |
| `src/pages/Alerts/index.tsx` | Edit | Обернуть в Tabs, вынести event-часть |
| `src/pages/Alerts/components/AlertEventTab.tsx` | Create | Содержимое текущего index.tsx |
| `src/pages/Alerts/components/AlertConfigTab.tsx` | Create | Контейнер вкладки |
| `src/pages/Alerts/components/AlertConfigTable.tsx` | Create | Таблица + actions |
| `src/pages/Alerts/components/AlertConfigModal.tsx` | Create | Modal форма |
| `src/pages/Alerts/components/AlertCheckButton.tsx` | Create | Кнопка с cooldown |
| `src/pages/Alerts/hooks/useAlertConfigs.ts` | Create | Query + mutations |
| `src/pages/Alerts/hooks/useAlertCheck.ts` | Create | Check mutation |
