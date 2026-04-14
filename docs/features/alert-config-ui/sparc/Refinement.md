# Refinement — Alert Config UI

## 1. Edge Cases & Corner Scenarios

### 1.1 SKU / Platform select при большом каталоге

**Проблема:** `skusApi.list({ limit: 200 })` может вернуть 200 записей — форма медленная.

**Решение:**
- Использовать `showSearch` с серверной фильтрацией через `debounce(300ms)`:
  ```typescript
  const [skuSearch, setSkuSearch] = useState('')
  const { data: skus } = useQuery(
    ['skus', { limit: 50, search: skuSearch }],
    () => skusApi.list({ limit: 50, search: skuSearch }),
    { enabled: skuSearch.length > 1 || true, staleTime: 30_000 }
  )
  ```
- Platforms: обычно < 20, грузить все сразу (`staleTime: 5min`)

### 1.2 Синхронизация Slider ↔ InputNumber

**Проблема:** Ant Design Slider и InputNumber — два разных поля.

**Решение:** Bind оба к одному Form field через Form.Item name="threshold" и
контролировать значение через `Form.useWatch`:
```typescript
const threshold = Form.useWatch('threshold', form)
// Slider value=threshold, onChange=(v) => form.setFieldValue('threshold', v)
// InputNumber value=threshold, onChange=(v) => form.setFieldValue('threshold', v)
```

### 1.3 Tags Input для email — потеря незавершённого тега

**Проблема:** Пользователь вводит email, не нажимает Enter, нажимает "Создать" — email теряется.

**Решение:** В `handleFinish` перед отправкой проверять inputValue у Select[mode=tags]:
- Использовать Ant Design Select `onBlur` или `onInputKeyDown` для автоматического подтверждения
- Альтернатива: инструктивный placeholder "Введите email, нажмите Enter"

### 1.4 Delete во время мутации

**Проблема:** Двойной клик "Удалить" отправит два DELETE запроса.

**Решение:** Кнопка "OK" в confirm modal переходит в `loading` состояние через
`removeMutation.isPending`.

### 1.5 Stale data после toggle is_active в таблице

**Проблема:** Клик по Switch в таблице отправляет PATCH, но таблица показывает старое значение
до invalidate.

**Решение:** Optimistic update через `onMutate` в useMutation:
```typescript
onMutate: async ({ id, data }) => {
  await queryClient.cancelQueries({ queryKey: ['alert-configs'] })
  const prev = queryClient.getQueryData(['alert-configs', { page }])
  queryClient.setQueryData(['alert-configs', { page }], (old) => ({
    ...old,
    items: old.items.map(item =>
      item.id === id ? { ...item, ...data } : item
    )
  }))
  return { prev }
},
onError: (_, __, ctx) => {
  queryClient.setQueryData(['alert-configs', { page }], ctx.prev)
}
```

---

## 2. UX Refinements

### 2.1 "Охват" колонка — отображение имён

AlertConfig хранит `sku_id` и `platform_id` как UUID. В таблице нужно показать имена.

**Подход:** Обогащать данные на стороне клиента из уже кешированных React Query данных:
```typescript
// В AlertConfigTable: получаем skus и platforms из кеша
const { data: skusData } = useQuery(['skus', { limit: 200 }], ...)
const { data: platforms } = useQuery(['platforms'], ...)

const skuMap = useMemo(() =>
  Object.fromEntries((skusData?.items ?? []).map(s => [s.id, s.name])),
  [skusData]
)
const platformMap = useMemo(() =>
  Object.fromEntries((platforms ?? []).map(p => [p.id, p.name])),
  [platforms]
)
```

### 2.2 Показ счётчика новых алертов на вкладке "События"

Из существующей страницы уже есть `queryKey: ['alerts-count']` для badge.
При ack mutation — invalidate этот ключ (уже реализовано).

### 2.3 Responsive: мобильный вид

Таблица конфигураций: на мобильном скрывать колонки "Охват" и "Получатели",
оставлять Тип + Активен + Действия.

---

## 3. Implementation Order

Рекомендуемый порядок реализации (минимальный риск):

```
Step 1: Обновить api/alerts.ts
  → Добавить типы AlertConfig, AlertConfigPage, etc.
  → Добавить alertConfigsApi объект
  → Не ломает существующий alertsApi

Step 2: Создать хуки
  → hooks/useAlertConfigs.ts
  → hooks/useAlertCheck.ts

Step 3: Создать AlertConfigModal
  → Изолированный компонент, легко тестировать

Step 4: Создать AlertConfigTable
  → Зависит от Modal для actions

Step 5: Создать AlertCheckButton

Step 6: Создать AlertConfigTab
  → Собирает Table + Modal + CheckButton

Step 7: Рефакторинг index.tsx
  → Вынести event-часть в AlertEventTab
  → Добавить Tabs, вставить AlertConfigTab

Step 8: Тесты
```

---

## 4. Testing Strategy

### Unit Tests

```typescript
// AlertConfigModal.test.tsx
describe('AlertConfigModal', () => {
  it('скрывает threshold при выборе oos')
  it('требует threshold при выборе content_drop')
  it('валидирует email формат в tags input')
  it('в режиме edit — alert_type и sku_id задизейблены')
  it('в режиме create — все поля редактируемы')
})

// AlertConfigTable.test.tsx  
describe('AlertConfigTable', () => {
  it('показывает кнопки Изм/Удал только для admin/manager')
  it('скрывает кнопки для viewer')
  it('показывает "--" в колонке Порог для oos')
  it('отображает имена SKU и платформ из маппинга')
})
```

### Integration Tests

```typescript
// AlertsPage.test.tsx
describe('AlertsPage', () => {
  it('переключение вкладок показывает нужный контент')
  it('создание конфигурации: форма → POST → таблица обновляется')
  it('удаление: confirm → DELETE → строка исчезает')
  it('toggle is_active: клик → PATCH → Switch обновляется')
})
```

### MSW Mocks

```typescript
server.use(
  rest.get('/api/v1/alerts/configs', (req, res, ctx) =>
    res(ctx.json(mockAlertConfigPage))
  ),
  rest.post('/api/v1/alerts/configs', (req, res, ctx) =>
    res(ctx.status(201), ctx.json(mockAlertConfig))
  ),
  rest.patch('/api/v1/alerts/configs/:id', (req, res, ctx) =>
    res(ctx.json({ ...mockAlertConfig, ...req.body }))
  ),
  rest.delete('/api/v1/alerts/configs/:id', (req, res, ctx) =>
    res(ctx.status(204))
  ),
  rest.post('/api/v1/alerts/check', (req, res, ctx) =>
    res(ctx.json({ events_created: 2, emails_sent: 1, errors: [] }))
  ),
)
```

---

## 5. Accessibility

- Все интерактивные элементы имеют `aria-label`
- Modal фокусируется на первом поле при открытии (Ant Design по умолчанию)
- Keyboard: Tab между полями, Enter для submit, Escape для cancel
- Switch в таблице: `aria-label="Активировать конфигурацию {type}"`

---

## 6. Performance Considerations

- SKU и Platform данные кешируются в React Query с `staleTime: 5min` — грузятся один раз
- Таблица конфигураций: server-side pagination (50/page) — не грузить все записи
- `invalidateQueries` только для `['alert-configs']` после mutations — не инвалидировать events
- AlertCheckButton cooldown реализован через local state + `Date.now()` — без setTimeout на 60 секунд
