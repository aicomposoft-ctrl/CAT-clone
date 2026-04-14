# Feature Architecture: Auth (JWT + RBAC)

**Feature ID:** auth-jwt-rbac
**Last Updated:** 2026-03-27

---

## 1. File Structure

```
services/api/
├── app/
│   ├── main.py                    # startup: validate_secrets() called here
│   ├── core/
│   │   ├── config.py              # Settings (pydantic-settings), JWT_SECRET validation
│   │   ├── database.py            # AsyncSession factory, engine
│   │   ├── deps.py                # get_db, get_current_user, require_role
│   │   └── security.py            # JWT encode/decode, bcrypt, lockout logic
│   └── auth/
│       ├── models.py              # User, Organization, RefreshToken ORM models
│       ├── schemas.py             # LoginRequest, TokenResponse, UserResponse
│       ├── service.py             # authenticate_user, refresh_token, revoke_token
│       ├── repository.py          # DB queries (users, refresh_tokens)
│       └── router.py              # /login, /refresh, /logout, /me

infrastructure/
└── postgres/
    └── migrations/
        └── 0001_create_auth_tables.py   # Alembic migration
```

---

## 2. Component Diagram

```
┌─────────────────────────────────────────────────────────┐
│  Client (Frontend / API consumer)                        │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTPS
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Nginx (Rate Limiting: 10 req/min per IP on /auth/*)     │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  FastAPI Router (/api/v1/auth)                           │
│                                                          │
│  POST /login  → AuthService.authenticate()               │
│  POST /refresh → AuthService.refresh()                   │
│  POST /logout  → AuthService.revoke()                    │
│  GET  /me      → get_current_user dependency             │
└──────────────────────┬──────────────────────────────────┘
                       │
         ┌─────────────┼──────────────┐
         ▼             ▼              ▼
┌──────────────┐ ┌──────────┐ ┌────────────────┐
│ core/        │ │ auth/    │ │ PostgreSQL      │
│ security.py  │ │ repo.py  │ │                 │
│ (JWT/bcrypt) │ │ (DB)     │ │ users           │
└──────────────┘ └──────────┘ │ organizations   │
                              │ refresh_tokens  │
                              └────────────────┘
```

---

## 3. Core Module: security.py

Responsibilities:
- `create_access_token(user_id, org_id, role)` → signed JWT, 15 min TTL
- `create_refresh_token(user_id)` → signed JWT, 7 day TTL
- `decode_token(token)` → payload dict or raises JWTError
- `hash_password(plain)` → bcrypt hash (cost 12)
- `verify_password(plain, hashed)` → bool
- `check_lockout(failed_attempts, locked_until)` → bool

No direct DB access. Pure functions, easily testable in unit tests.

---

## 4. Core Module: deps.py

```python
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency: decode JWT → load user from DB → return User."""

def require_role(*roles: str):
    """Factory: returns dependency that raises 403 if user.role not in roles."""
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "INSUFFICIENT_PERMISSIONS")
        return user
    return checker
```

Usage in other routers:
```python
# viewer + manager + admin can GET
@router.get("/skus", dependencies=[Depends(get_current_user)])

# only manager + admin can DELETE
@router.delete("/skus/{id}")
async def delete_sku(user: User = Depends(require_role("admin", "manager"))):
    ...
```

---

## 5. Database Schema

```sql
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    plan VARCHAR(50) DEFAULT 'basic',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'viewer',
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_org_id ON users(org_id);
CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);
```

---

## 6. JWT Payload Structure

```json
// Access Token
{
  "sub": "user-uuid",
  "org_id": "org-uuid",
  "role": "manager",
  "type": "access",
  "iat": 1711584000,
  "exp": 1711584900
}

// Refresh Token
{
  "sub": "user-uuid",
  "jti": "unique-token-id",
  "type": "refresh",
  "iat": 1711584000,
  "exp": 1712188800
}
```

Algorithm: `HS256` (symmetric). Secret: `JWT_SECRET` env var (min 32 bytes).

---

## 7. Security Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Token algorithm | HS256 | Sufficient for single-service; RS256 needed only for multi-service |
| Refresh token storage | DB (hashed) | Enables explicit revocation on logout |
| Token hash | SHA256 | Store hash, not plaintext — DB breach doesn't leak valid tokens |
| Password hash | bcrypt cost 12 | ~250ms per hash — acceptable for login, blocks brute force |
| Lockout storage | `users` table columns | Simple; no Redis dependency for Sprint 1 |
| Rate limiting | Nginx | Handled at infrastructure level, not application level |

---

## 8. Startup Validation

In `services/api/app/main.py`:

```python
from app.core.config import validate_required_secrets

@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_required_secrets(["JWT_SECRET", "POSTGRES_URL"])
    yield

app = FastAPI(lifespan=lifespan)
```

Service refuses to start if `JWT_SECRET` or `POSTGRES_URL` are missing.
