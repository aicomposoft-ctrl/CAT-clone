# Feature PRD: Auth (JWT + RBAC)

**Feature ID:** auth-jwt-rbac
**Sprint:** 1
**Priority:** P0 (blocker for all other features)
**Story Points:** 5
**Last Updated:** 2026-03-27

---

## 1. Problem Statement

CAT is a multi-tenant SaaS platform. Without authentication, any user can access any org's data.
Without authorization (RBAC), any authenticated user can perform any action — including deleting SKUs or exporting sensitive competitor pricing data.

Both authentication and authorization must be in place before any other feature can be safely implemented.

## 2. Feature Scope

### In Scope (Sprint 1)

| Component | Description |
|-----------|-------------|
| User login | Email + password → JWT access token + refresh token |
| Token refresh | Refresh token → new access token (no re-login) |
| Logout | Invalidate refresh token |
| Get current user | `/me` endpoint for frontend session init |
| RBAC enforcement | Roles: `admin`, `manager`, `viewer` |
| Password hashing | bcrypt, cost factor 12 |
| Rate limiting | Auth endpoints: 10 req/min per IP |
| Account lockout | 5 failed attempts → 15 min lockout |
| Startup validation | JWT_SECRET missing → exit(1) |

### Out of Scope (Sprint 1)

- User registration (admin-only via direct DB insert or future admin panel)
- Password reset / forgot password flow
- OAuth2 / SSO (Google, SAML)
- 2FA / MFA
- Email verification
- Session management UI

## 3. User Personas

| Persona | Role | Primary Need |
|---------|------|-------------|
| Trade Marketing Manager | `manager` | Access dashboards, export reports |
| Brand Manager | `manager` | Full SKU CRUD, configure alerts |
| Read-only stakeholder | `viewer` | View dashboards, no mutations |
| System admin | `admin` | User management, full access |

## 4. RBAC Permission Matrix

| Action | admin | manager | viewer |
|--------|-------|---------|--------|
| Login / Logout | ✅ | ✅ | ✅ |
| View dashboards | ✅ | ✅ | ✅ |
| Export reports | ✅ | ✅ | ✅ |
| Create/edit/delete SKUs | ✅ | ✅ | ❌ |
| Upload reference materials | ✅ | ✅ | ❌ |
| Configure alerts | ✅ | ✅ | ❌ |
| Manage users | ✅ | ❌ | ❌ |
| View billing | ✅ | ❌ | ❌ |

## 5. Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| Login latency | < 300ms p99 |
| Token validation latency | < 5ms (in-process JWT decode) |
| Access token TTL | 15 minutes |
| Refresh token TTL | 7 days |
| Password hashing | bcrypt, cost 12 (~250ms) |
| Rate limit (auth) | 10 req/min per IP |
| Lockout threshold | 5 failed attempts |
| Lockout duration | 15 minutes |
| Secrets | JWT_SECRET validated at startup — no fallback |

## 6. Success Criteria

- All API endpoints return 401 when no/invalid token provided
- Viewer role cannot reach mutation endpoints (returns 403)
- Cross-org data access is impossible (org_id isolation)
- Account locks after 5 failed attempts, unlocks after 15 min
- `JWT_SECRET` missing → service refuses to start
