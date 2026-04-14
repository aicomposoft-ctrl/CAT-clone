# Specification — Alert Config UI

## 1. API Contracts (уже реализованы в backend)

### GET /api/v1/alerts/configs

**Query params:** `page: int = 1`, `size: int = 50`

**Response 200:**
```json
{
  "items": [
    {
      "id": "uuid",
      "org_id": "uuid",
      "sku_id": "uuid | null",
      "platform_id": "uuid | null",
      "alert_type": "content_drop | oos",
      "threshold": "70.00 | null",
      "email_recipients": ["admin@brand.ru"],
      "is_active": true,
      "created_at": "2026-04-05T10:00:00Z"
    }
  ],
  "total": 5,
  "page": 1,
  "size": 50
}
```

### POST /api/v1/alerts/configs

**Body:**
```json
{
  "alert_type": "content_drop",
  "sku_id": "uuid | null",
  "platform_id": "uuid | null",
  "threshold": 70,
  "email_recipients": ["admin@brand.ru"],
  "is_active": true
}
```

**Validations:**
- `alert_type` ∈ {"content_drop", "oos"}
- `threshold` required when `alert_type == "content_drop"`, range 0–100
- `email_recipients` min 1, max 20 valid EmailStr
- `sku_id` / `platform_id` optional; null = "all"

**Response 201:** AlertConfigResponse

**Errors:**
- 422: validation failure (threshold missing for content_drop, invalid email)
- 401: unauthenticated
- 403: viewer role

### PATCH /api/v1/alerts/configs/{id}

**Body (all optional):**
```json
{
  "threshold": 60,
  "email_recipients": ["new@brand.ru"],
  "is_active": false
}
```

**Response 200:** AlertConfigResponse  
**Errors:** 404 if config not found OR belongs to different org

### DELETE /api/v1/alerts/configs/{id}

**Response 204 No Content**  
**Errors:** 404 if not found or wrong org

### POST /api/v1/alerts/check

**Response 200:**
```json
{
  "events_created": 3,
  "emails_sent": 2,
  "errors": []
}
```

**Errors:**
- 403: non-admin role
- 429: rate limit exceeded (5 req/min per org)

---

## 2. Frontend TypeScript Types

```typescript
// src/api/alerts.ts additions

export interface AlertConfig {
  id: string
  org_id: string
  sku_id: string | null
  platform_id: string | null
  alert_type: 'content_drop' | 'oos'
  threshold: number | null
  email_recipients: string[]
  is_active: boolean
  created_at: string
}

export interface AlertConfigPage {
  items: AlertConfig[]
  total: number
  page: number
  size: number
}

export interface AlertConfigCreateRequest {
  alert_type: 'content_drop' | 'oos'
  sku_id?: string | null
  platform_id?: string | null
  threshold?: number | null
  email_recipients: string[]
  is_active?: boolean
}

export interface AlertConfigUpdateRequest {
  threshold?: number | null
  email_recipients?: string[]
  is_active?: boolean
}

export interface AlertCheckResult {
  events_created: number
  emails_sent: number
  errors: string[]
}
```

---

## 3. Component Architecture

```
pages/Alerts/
├── index.tsx                  ← Tabs wrapper (Events + Configs)
├── components/
│   ├── AlertEventTable.tsx     ← Существующая таблица событий (перенос)
│   ├── AlertConfigTable.tsx    ← Новая: таблица конфигураций
│   ├── AlertConfigModal.tsx    ← Новая: модал создания/редактирования
│   └── AlertConfigActions.tsx  ← Новая: toolbar (+ Добавить, Проверить)
└── hooks/
    ├── useAlertConfigs.ts      ← useQuery для configs + мутации
    └── useAlertCheck.ts        ← useMutation для POST /check
```

---

## 4. State Management

### React Query keys

```typescript
['alert-configs', { page, size }]    // list
['alert-configs', configId]           // single (не нужен — нет GET /configs/{id})
['alerts', filters]                   // events (существующий)
```

### Modal state

```typescript
type ModalState =
  | { mode: 'closed' }
  | { mode: 'create' }
  | { mode: 'edit'; config: AlertConfig }
```

---

## 5. Validation Rules (client-side)

| Field | Rule |
|-------|------|
| alert_type | required |
| threshold | required if alert_type === 'content_drop'; range 0–100; integer |
| threshold | hidden + not validated if alert_type === 'oos' |
| email_recipients | min 1; each must match email regex; max 20 |
| sku_id | optional UUID |
| platform_id | optional UUID |

Email regex: `/^[^\s@]+@[^\s@]+\.[^\s@]+$/`

---

## 6. RBAC in UI

| Action | admin | manager | viewer |
|--------|-------|---------|--------|
| Видеть вкладку "Конфигурации" | ✅ | ✅ | ✅ |
| Видеть таблицу конфигураций | ✅ | ✅ | ✅ (read-only) |
| Кнопка "+ Добавить" | ✅ | ✅ | ❌ скрыта |
| Редактировать | ✅ | ✅ | ❌ |
| Удалить | ✅ | ✅ | ❌ |
| Кнопка "Запустить проверку" | ✅ | ❌ | ❌ |
| Toggle is_active | ✅ | ✅ | ❌ |

---

## 7. Error Handling

| Scenario | UI Response |
|----------|-------------|
| 422 validation error | Показать поля с ошибкой из response.detail |
| 404 при edit/delete | toast "Конфигурация не найдена — обновите список" |
| 429 при check | toast "Слишком много запросов, подождите 1 минуту" |
| 500 | toast "Ошибка сервера, попробуйте позже" |
| Network error | toast "Нет соединения с сервером" |

---

## 8. Constraints

- Не изменять `alert_type`, `sku_id`, `platform_id` после создания (только PATCH поддерживает threshold/emails/is_active)
- Форма создания использует `skusApi.list()` для поиска SKU — не более 200 в dropdown
- Форма создания использует `platformsApi.list()` для select платформы
- При создании конфигурации для oos — threshold не отправляется в body (undefined, не null)
