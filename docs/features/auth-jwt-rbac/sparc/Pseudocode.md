# Feature Pseudocode: Auth (JWT + RBAC)

**Feature ID:** auth-jwt-rbac
**Last Updated:** 2026-03-27

---

## 1. Data Structures

```
type Organization = {
  id: UUID
  name: string
  slug: string
  plan: string  // "basic" | "pro"
  created_at: Timestamp
}

type User = {
  id: UUID
  org_id: UUID
  email: string
  password_hash: string  // bcrypt
  role: string           // "admin" | "manager" | "viewer"
  failed_attempts: int
  locked_until: Timestamp | null
  created_at: Timestamp
}

type RefreshToken = {
  id: UUID
  user_id: UUID
  token_hash: string  // SHA256 of raw token
  expires_at: Timestamp
  revoked: bool
  created_at: Timestamp
}

type TokenPayload = {
  sub: UUID           // user_id
  org_id: UUID
  role: string
  type: "access" | "refresh"
  jti: UUID           // only refresh tokens
  iat: int
  exp: int
}

type LoginRequest = { email: string, password: string }
type TokenResponse = {
  access_token: string
  refresh_token: string
  token_type: "Bearer"
  expires_in: int      // seconds
  user: UserInfo
}
type UserInfo = { id, email, role, org_id, org_name }
```

---

## 2. Core Algorithms

### Algorithm: create_access_token

```
INPUT: user_id: UUID, org_id: UUID, role: string
OUTPUT: signed JWT string

STEPS:
1. now = current_timestamp()
2. payload = {
     "sub": str(user_id),
     "org_id": str(org_id),
     "role": role,
     "type": "access",
     "iat": now,
     "exp": now + 900  // 15 minutes
   }
3. token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
4. RETURN token
```

### Algorithm: create_refresh_token

```
INPUT: user_id: UUID
OUTPUT: (raw_token: string, token_hash: string, expires_at: Timestamp)

STEPS:
1. now = current_timestamp()
2. jti = generate_uuid()
3. payload = {
     "sub": str(user_id),
     "jti": str(jti),
     "type": "refresh",
     "iat": now,
     "exp": now + 604800  // 7 days
   }
4. raw_token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
5. token_hash = sha256(raw_token.encode()).hexdigest()
6. expires_at = now + 604800
7. RETURN (raw_token, token_hash, expires_at)
```

### Algorithm: decode_token

```
INPUT: token: string, expected_type: "access" | "refresh"
OUTPUT: TokenPayload OR raises AuthError

STEPS:
1. TRY:
   payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
2. CATCH ExpiredSignatureError:
   RAISE AuthError("TOKEN_EXPIRED")
3. CATCH JWTError:
   RAISE AuthError("INVALID_TOKEN")
4. IF payload["type"] != expected_type:
   RAISE AuthError("WRONG_TOKEN_TYPE")
5. RETURN payload
```

### Algorithm: authenticate_user (login flow)

```
INPUT: email: string, password: string, db: AsyncSession
OUTPUT: (access_token, refresh_token, user) OR raises AuthError

STEPS:
1. user = await user_repo.get_by_email(db, email)
2. IF user is None:
   RAISE AuthError("INVALID_CREDENTIALS")  // don't reveal "email not found"

3. IF user.locked_until IS NOT NULL AND user.locked_until > now():
   RAISE LockoutError(user.locked_until)

4. IF NOT verify_password(password, user.password_hash):
   new_attempts = user.failed_attempts + 1
   IF new_attempts >= 5:
     lockout_until = now() + 900  // 15 minutes
     await user_repo.set_lockout(db, user.id, new_attempts, lockout_until)
     RAISE LockoutError(lockout_until)
   ELSE:
     await user_repo.increment_failed_attempts(db, user.id, new_attempts)
     RAISE AuthError("INVALID_CREDENTIALS")

5. // Successful auth — reset lockout
   await user_repo.reset_failed_attempts(db, user.id)

6. access_token = create_access_token(user.id, user.org_id, user.role)
7. (raw_refresh, token_hash, expires_at) = create_refresh_token(user.id)
8. await refresh_token_repo.create(db, user.id, token_hash, expires_at)

9. org = await org_repo.get(db, user.org_id)

10. RETURN TokenResponse(
      access_token=access_token,
      refresh_token=raw_refresh,
      token_type="Bearer",
      expires_in=900,
      user=UserInfo(id, email, role, org_id, org_name=org.name)
    )
```

### Algorithm: refresh_access_token

```
INPUT: raw_refresh_token: string, db: AsyncSession
OUTPUT: new access_token string OR raises AuthError

STEPS:
1. payload = decode_token(raw_refresh_token, expected_type="refresh")
2. token_hash = sha256(raw_refresh_token.encode()).hexdigest()
3. stored = await refresh_token_repo.get_by_hash(db, token_hash)

4. IF stored is None:
   RAISE AuthError("INVALID_REFRESH_TOKEN")
5. IF stored.revoked:
   RAISE AuthError("INVALID_REFRESH_TOKEN")
6. IF stored.expires_at < now():
   RAISE AuthError("INVALID_REFRESH_TOKEN")

7. user = await user_repo.get(db, stored.user_id)
8. IF user is None:
   RAISE AuthError("INVALID_REFRESH_TOKEN")

9. new_access_token = create_access_token(user.id, user.org_id, user.role)
10. RETURN new_access_token
```

### Algorithm: revoke_refresh_token (logout)

```
INPUT: raw_refresh_token: string, db: AsyncSession
OUTPUT: void

STEPS:
1. token_hash = sha256(raw_refresh_token.encode()).hexdigest()
2. await refresh_token_repo.revoke(db, token_hash)
// If token not found — silently succeed (idempotent logout)
```

### Algorithm: get_current_user (FastAPI dependency)

```
INPUT: Authorization header (Bearer <token>), db: AsyncSession
OUTPUT: User object OR raises HTTPException

STEPS:
1. IF no Authorization header OR not "Bearer ":
   RAISE HTTPException(401, "UNAUTHORIZED")

2. token = header.split("Bearer ")[1]
3. TRY:
   payload = decode_token(token, expected_type="access")
4. CATCH AuthError:
   RAISE HTTPException(401, "UNAUTHORIZED")

5. user_id = UUID(payload["sub"])
6. user = await user_repo.get(db, user_id)
7. IF user is None:
   RAISE HTTPException(401, "UNAUTHORIZED")
8. RETURN user
```

---

## 3. RBAC Check Pattern

```
// In any router requiring specific roles:
@router.delete("/skus/{id}")
async def delete_sku(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "manager"))
):
    ...

// require_role factory:
FUNCTION require_role(*allowed_roles):
  FUNCTION checker(user = Depends(get_current_user)):
    IF user.role NOT IN allowed_roles:
      RAISE HTTPException(403, "INSUFFICIENT_PERMISSIONS")
    RETURN user
  RETURN checker
```

---

## 4. Startup Secrets Validation

```
FUNCTION validate_required_secrets(secrets: list[str]):
  missing = [s FOR s IN secrets IF NOT env.get(s)]
  IF missing:
    log.critical(f"Missing secrets: {missing}")
    sys.exit(1)

// Called in FastAPI lifespan:
validate_required_secrets(["JWT_SECRET", "POSTGRES_URL"])
```

---

## 5. Error Handling Map

| Condition | Exception | HTTP Status |
|-----------|-----------|-------------|
| Email not found | AuthError("INVALID_CREDENTIALS") | 401 |
| Wrong password (< 5 attempts) | AuthError("INVALID_CREDENTIALS") | 401 |
| Wrong password (5th attempt) | LockoutError(lockout_until) | 423 |
| Account currently locked | LockoutError(lockout_until) | 423 |
| Expired access token | AuthError("TOKEN_EXPIRED") | 401 |
| Invalid JWT signature | AuthError("INVALID_TOKEN") | 401 |
| Expired/revoked refresh token | AuthError("INVALID_REFRESH_TOKEN") | 401 |
| Insufficient role | PermissionError | 403 |
| Rate limit exceeded | (Nginx) | 429 |

---

## 6. Complexity Notes

- `verify_password` (bcrypt): O(1) but ~250ms wall time — acceptable for login, not for hot paths
- `create_access_token` / `decode_token` (JWT): O(1), < 1ms
- DB calls per login: 1 (get user) + 1 (update attempts OR insert refresh token) = 2 queries
- DB calls per API request: 1 (get user by id from JWT sub) or 0 if user cached
