# Security — Alert Config UI

## 1. RBAC Enforcement

### Frontend (UI layer — defense in depth)

```typescript
const canManage = user?.role === 'admin' || user?.role === 'manager'
const canCheck = user?.role === 'admin'
```

- Кнопки "+ Добавить", "Изменить", "Удалить" рендерятся только при `canManage`
- Кнопка "Запустить проверку" рендерится только при `canCheck`
- Switch в таблице задизейблен для viewer

**Важно:** Это UI-ограничение — не замена серверной проверки. Backend обязан проверять роль
через `Depends(require_role("admin", "manager"))` на каждом endpoint.

### Backend (уже реализовано)

| Endpoint | Requires |
|----------|----------|
| POST /alerts/configs | admin / manager |
| PATCH /alerts/configs/{id} | admin / manager |
| DELETE /alerts/configs/{id} | admin / manager |
| GET /alerts/configs | any authenticated |
| POST /alerts/check | admin only |

## 2. Multi-Tenant Isolation

**Backend (уже реализовано):**
- Все запросы к AlertConfig фильтруются по `org_id = current_user.org_id`
- DELETE/PATCH: проверяют принадлежность к org перед изменением → 404 если чужой
- Это предотвращает IDOR (Insecure Direct Object Reference)

**Frontend (нет дополнительных мер нужно):**
- Фронтенд не знает org_id других организаций
- Все запросы идут через apiClient с JWT токеном — backend определяет org_id из токена

## 3. Input Validation

| Field | Client-side | Server-side |
|-------|-------------|-------------|
| alert_type | Enum check | ✅ frozenset check |
| threshold | 0–100 range | ✅ Pydantic Field(ge=0, le=100) |
| email_recipients | Regex per tag | ✅ EmailStr validation |
| sku_id | Valid UUID format | ✅ FastAPI UUID type |
| platform_id | Valid UUID format | ✅ FastAPI UUID type |

**XSS Prevention:**
- React автоматически escapes все строки в JSX — нет dangerouslySetInnerHTML
- Email поля: только текст, не HTML
- Имена SKU/Platform из API отображаются как text nodes

## 4. Sensitive Data

- Email получателей отображаются в UI (не чувствительные данные для admin/manager)
- org_id не отображается в UI
- JWT токен не экспонируется в компонентах (только через apiClient interceptor)

## 5. Rate Limit Awareness

- POST /alerts/check: limit 5 req/min per org
- Frontend реализует 60s cooldown для предотвращения повторных нажатий
- При получении 429: показывать предупреждение, не блокировать другие действия

## 6. OWASP Checklist для этой фичи

- [x] A01 Broken Access Control: RBAC в UI + backend enforcement
- [x] A02 Cryptographic Failures: нет хранения секретов во фронтенде
- [x] A03 Injection: React escapes output; нет eval/innerHTML
- [x] A04 Insecure Design: confirmation modal для destructive actions
- [x] A05 Security Misconfiguration: нет новых endpoints, нет новых конфигов
- [x] A07 Auth Failures: все вызовы через apiClient с JWT (Bearer token)
- [x] A10 SSRF: нет user-supplied URLs в этой фиче
