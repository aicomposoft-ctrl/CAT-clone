# Feature Refinement: Auth (JWT + RBAC)

**Feature ID:** auth-jwt-rbac
**Last Updated:** 2026-03-27

---

## 1. Edge Cases Matrix

| # | Scenario | Input | Expected Behavior | Handling |
|---|----------|-------|-------------------|----------|
| 1 | Email with different case | `Manager@Brand.RU` | Normalize to lowercase before lookup | `email.lower()` in login handler |
| 2 | Login with unknown email | `nobody@fake.com` | 401 INVALID_CREDENTIALS (same as wrong password) | Don't reveal "user not found" |
| 3 | Lockout expires mid-request | Account locked, time passes | Unlock on next login attempt | Check `locked_until < now()` |
| 4 | JWT with tampered payload | Modified role in token | 401 INVALID_TOKEN | HMAC signature check |
| 5 | JWT from deleted user | Valid token but user deleted | 401 UNAUTHORIZED | Load user from DB on every request |
| 6 | Refresh token used after logout | Revoked token replayed | 401 INVALID_REFRESH_TOKEN | Check `revoked=True` in DB |
| 7 | Expired refresh token | `exp` in past | 401 INVALID_REFRESH_TOKEN | Check exp in JWT decode |
| 8 | Concurrent refresh requests | Two requests with same refresh token | Both succeed (token not single-use) | Refresh token is multi-use until revoked |
| 9 | Request with expired access + valid refresh | Frontend calls API | 401 from API; frontend triggers refresh silently | Frontend responsibility |
| 10 | `JWT_SECRET` changed, old tokens exist | All old tokens invalid | All logged-in users get 401, must re-login | Expected behavior on secret rotation |
| 11 | Admin deletes user mid-session | Token valid, user gone | 401 on next API call | User loaded from DB per request |
| 12 | `viewer` attempts GET on public endpoint | `/api/v1/content/scores` | 200 (viewers CAN read) | No role check on read endpoints |
| 13 | Password with special chars / Unicode | `P@ssw0rd!ÄÖÜ` | Bcrypt handles any byte string | No pre-processing needed |
| 14 | Very long email (>255 chars) | 300-char email | 422 Validation Error | Pydantic `EmailStr` max_length |
| 15 | Multiple orgs in DB, user queries another | Cross-org API call | 404 or empty results (not 403) | org_id filter silently scopes results |

---

## 2. Security Hardening

### Password Security
- Minimum 8 characters enforced via Pydantic (`min_length=8`)
- bcrypt cost factor 12 (not configurable at runtime — hardcoded)
- Never log passwords — logging middleware must strip `password` from request body logs
- Never return password_hash in any response schema

### Token Security
- `JWT_SECRET` minimum entropy: 32 random bytes (`secrets.token_hex(32)`)
- Access token deliberately short (15 min) — reduces blast radius of token theft
- Refresh token stored as SHA256 hash — DB breach doesn't yield usable tokens
- `Bearer` prefix required — prevents accidental token usage from cookies

### Rate Limiting
- Nginx handles rate limiting at `/api/v1/auth/` prefix
- Application layer adds no additional rate limiting (Nginx is sufficient for Sprint 1)
- Config: `limit_req_zone $binary_remote_addr zone=auth:10m rate=10r/m`

### Timing Attack Mitigation
- Always run `verify_password` even when user not found (with dummy hash)
- This prevents timing-based user enumeration

```python
DUMMY_HASH = "$2b$12$dummy.hash.to.prevent.timing.attacks.xxxxxx"

if user is None:
    verify_password("dummy", DUMMY_HASH)  # waste same time
    raise AuthError("INVALID_CREDENTIALS")
```

---

## 3. Testing Strategy

### Unit Tests (`services/api/tests/unit/`)

| Test | What to verify |
|------|---------------|
| `test_create_access_token` | Payload fields, expiry = now + 900 |
| `test_decode_token_valid` | Returns correct payload |
| `test_decode_token_expired` | Raises AuthError |
| `test_decode_token_tampered` | Raises AuthError (bad signature) |
| `test_hash_and_verify_password` | hash ≠ plain, verify returns True |
| `test_verify_wrong_password` | Returns False |
| `test_require_role_allowed` | Returns user when role matches |
| `test_require_role_blocked` | Raises HTTPException 403 |

### Integration Tests (`services/api/tests/integration/`)

| Test | What to verify |
|------|---------------|
| `test_login_success` | DB lookup + token generation + refresh token persisted |
| `test_login_wrong_password` | failed_attempts incremented |
| `test_login_lockout_after_5_attempts` | locked_until set, 423 returned |
| `test_login_lockout_expired` | Can login after lockout_until passes |
| `test_refresh_token_success` | New access token generated |
| `test_refresh_token_revoked` | 401 returned |
| `test_logout_revokes_token` | refresh_token.revoked = True in DB |
| `test_get_me_valid_token` | Returns user info |
| `test_get_me_expired_token` | 401 returned |

### E2E Tests (`services/api/tests/e2e/`)

Full HTTP stack via FastAPI TestClient:

```gherkin
Scenario: Complete login flow
  POST /login → 200 + tokens
  GET /me with access_token → 200 + user info
  POST /refresh with refresh_token → 200 + new access_token
  POST /logout → 200
  POST /refresh with same refresh_token → 401

Scenario: RBAC - viewer blocked from mutations
  POST /login as viewer → 200
  DELETE /skus/{id} with viewer token → 403

Scenario: Concurrent API requests with same token
  10 parallel GET /me with same access_token → all 200 (stateless JWT)
```

### Security Tests

```
Scenario: Brute force protection
  POST /login × 5 wrong passwords
  → 5th attempt returns 423 with lockout_until

Scenario: Token replay after logout
  Login → logout → use old access_token
  → GET /me returns 401 if token expired, 200 if still valid (access tokens not revoked)
  // Note: access tokens are stateless. Only refresh tokens are revocable.

Scenario: Cross-org isolation via JWT manipulation
  Login as manager org-001
  Manually modify JWT payload to org-002
  → Any API call returns 401 (HMAC signature fails)
```

---

## 4. Performance Notes

| Operation | Expected Latency | Bottleneck |
|-----------|-----------------|------------|
| bcrypt verify | ~250ms | CPU (intentional) |
| JWT decode | < 1ms | CPU |
| DB: get user by email | < 5ms | PG index on email |
| DB: insert refresh token | < 5ms | Write |
| Full login response | ~260ms | bcrypt dominates |
| Full /me response | < 10ms | JWT + DB user lookup |

Optimization notes:
- `/me` can cache user object in request state to avoid duplicate DB lookups within same request
- Bcrypt cost 12 is the minimum acceptable. Do NOT reduce it.
- Consider caching user-by-id in Redis (5 min TTL) once request volume justifies it (not Sprint 1)

---

## 5. Technical Debt (Known Sprint 1 Shortcuts)

| Item | Impact | Resolution Sprint |
|------|--------|------------------|
| Lockout stored in `users` table (not Redis) | Lockout not shared across API replicas if scaled | Sprint 6+ |
| No access token revocation | Logged-out user can still use access token until it expires (max 15 min) | Sprint 6+ |
| No user registration UI | Users created via admin or direct DB insert | Sprint 8 (admin panel) |
| No password complexity rules | Only min_length=8 | Sprint 3 |
| Email case normalization only at login | Not enforced at creation | Sprint 2 (user management) |

---

## 6. Observability

### Logs (structured, no sensitive data)

```python
# Login success
logger.info("auth.login.success", extra={"user_id": str(user.id), "org_id": str(user.org_id)})

# Login failure
logger.warning("auth.login.failure", extra={"email_domain": email.split("@")[1], "reason": "INVALID_CREDENTIALS"})

# Lockout triggered
logger.warning("auth.lockout.triggered", extra={"user_id": str(user.id), "attempts": new_attempts})

# Token refresh
logger.info("auth.token.refreshed", extra={"user_id": str(user.id)})
```

Never log: passwords, tokens, full email (log domain only for privacy), password hashes.

### Metrics (for future Prometheus integration)
- `auth_login_total{result="success|failure|locked"}` counter
- `auth_login_duration_seconds` histogram
- `auth_refresh_total{result="success|failure"}` counter
