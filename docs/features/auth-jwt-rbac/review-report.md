# Review Report — Auth (JWT + RBAC)

**Date:** 2026-03-27
**Reviewed by:** 5 parallel brutal-honesty-review agents
**Branch:** claude/init-p-replicator-OZcDC

---

## Overall Verdict

**NOT production-ready as-is.** The architecture is sound and the security intent is correct, but there are 4 runtime bugs that will cause production failures, plus a cluster of security and correctness defects that must be resolved before this handles real traffic.

---

## Agent 1: Code Quality (Linus Mode)

### Critical

| # | Location | Issue | Fix |
|---|----------|-------|-----|
| C1 | `models.py:118` | `onupdate=datetime.utcnow` stores naive datetime into timezone-aware column — data corruption on Python 3.12+, deprecated | `onupdate=lambda: datetime.now(tz=timezone.utc)` |
| C2 | `database.py:38-47` | `get_db` defined twice (also in `deps.py`) — duplicate code, will diverge | Remove from `database.py`; keep in `deps.py` |
| C3 | `router.py` | `refresh_access_token` returns bare `str` but `response_model=RefreshResponse` — **ResponseValidationError on every successful refresh call** | Wrap: `return RefreshResponse(access_token=new_token)` |

### Major

| # | Location | Issue | Fix |
|---|----------|-------|-----|
| M1 | `service.py:99-120` | Magic number `5` and `900` for lockout threshold/duration — change-blind | Define `_LOCKOUT_THRESHOLD = 5`, `_LOCKOUT_DURATION_SECONDS = 900` |
| M2 | `service.py:131-132` | Silent org name degradation: `org_name = ""` if org not found masks DB integrity failure | Raise `AuthError("ORG_NOT_FOUND")` instead |
| M3 | `main.py:52-53` | Swagger UI (`/docs`, `/redoc`) exposed unconditionally including production | Gate on `APP_ENV != "production"` |
| M4 | `deps.py:82` | `require_role` inner `checker` is sync; should be `async def` for consistency | Change to `async def checker` |
| M5 | `config.py:65-70` | `BCRYPT_ROUNDS` is dead config — no runtime effect, misleads operators | Remove field |

### Minor

- `schemas.py:39` — `role` should be `Literal["admin", "manager", "viewer"]`, not bare `str`
- `models.py:48` — both `default` and `server_default` on `plan` column; pick one
- `repository.py` — docstring "org_id not filtered" reads as blanket permission; narrow the explanation

---

## Agent 2: Security (OWASP)

### Critical

| # | OWASP | Location | Issue | Fix |
|---|-------|----------|-------|-----|
| C4 | A04 | `main.py` | **No rate limiting on `/login` or `/refresh`** — credential stuffing unthrottled | Add `slowapi` middleware; 10 req/min per IP |
| C5 | A04/A05 | `main.py:52-53` | Swagger UI unconditionally exposes full API in production | Gate on `APP_ENV` |

### Major

| # | OWASP | Location | Issue | Fix |
|---|-------|----------|-------|-----|
| M6 | A07 | `service.py` | Refresh token not rotated — stolen token persists 7 days with no detection | Needs explicit tech-lead sign-off per RFC 6819 |
| M7 | A09 | `router.py:52-57` | HTTP 423 + `X-Lockout-Until` header leaks account existence (vs 401 for unknown email) | Design decision: accept and document, or return 401 for all auth failures |
| M8 | A07 | `service.py:99-104` | Lockout increment race condition — concurrent requests can bypass counter | Atomic SQL increment (see Agent 4) |
| M9 | A02 | `config.py:106` | `validate_required_secrets` only checks 2 of 5 required secrets | Add `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `SMTP_PASSWORD` |
| M10 | A02 | `requirements.txt:14` | `python-jose` has CVE-2024-33664 / CVE-2024-33663; unmaintained since 2022 | Replace with `PyJWT>=2.8.0` |

### Minor

- `service.py:79-85` — `email_domain` logged on failure; may be PII under GDPR
- `models.py:131` — `__repr__` includes `email`; leaks PII into logs
- `repository.py:128` — `token_hash[:8]` logged; minor oracle in debug logs

---

## Agent 3: Multi-Tenant Isolation

### Critical

None — the auth domain correctly sources `org_id` from JWT at login time from the DB record, never from user input.

### Major

| # | Location | Issue | Fix |
|---|----------|-------|-----|
| M11 | `router.py:97` / `service.py:198` | `revoke_refresh_token` accepts any token without verifying it belongs to `current_user` — user from org_A can DoS org_B's session | Check `stored.user_id == current_user.id` before revoking |
| M12 | `repository.py:35-40` | `get_by_id` has no `org_id` filter — safe for current callers (JWT sub) but no defense-in-depth | Add optional `org_id` parameter for future safety |

### Minor

- No composite index on `(user_id, token_hash)` — needed if ownership check is added
- `RefreshToken` table missing `(user_id, revoked)` index for future "list sessions" feature

---

## Agent 4: Performance

### Critical

| # | Location | Issue | Fix |
|---|----------|-------|-----|
| C6 | `service.py:80,97` | **bcrypt called synchronously in async event loop** — 250ms CPU block freezes all coroutines per login. 10 concurrent logins = 2.5s stall. Kubernetes liveness probes will time out. | `await asyncio.to_thread(verify_password, ...)` |
| C7 | `service.py:122-128` | Two sequential commits in login success path — partial state window between reset_attempts and token creation | Combine into single transaction |

### Major

| # | Location | Issue | Fix |
|---|----------|-------|-----|
| M13 | `repository.py:43-54` | `increment_failed_attempts` does read-modify-write in Python — race condition, counter falls behind under concurrent load | Atomic `UPDATE users SET failed_attempts = failed_attempts + 1 RETURNING failed_attempts` |
| M14 | `service.py:131,224` | Extra org query on every login AND every `/me` call — can be eliminated with JOIN | `joinedload(User.organization)` in `get_by_email` / `get_by_id` |
| M15 | `service.py:154-195` | Token refresh makes 2 sequential DB queries that could be 1 JOIN | Single query: JOIN refresh_tokens + users |

### Minor

- `models.py:77-78` — `idx_users_email` is a duplicate (unique constraint already creates index)
- `models.py:118` — `onupdate` fires only for ORM UPDATE calls, not `.execute(update(...))` — `updated_at` never updated by repository layer
- Pool timeout not configured (`pool_timeout` defaults to 30s — silent queue buildup under load)

---

## Agent 5: Test Coverage (Ramsay Mode)

### Critical

| # | Issue | What Bug It Catches |
|---|-------|---------------------|
| TC1 | No test for expired access token rejection | Regression where `ExpiredSignatureError` leaks as 500 |
| TC2 | No cross-tenant token abuse test | JWT `org_id` field is cosmetic — no server-side validation |
| TC3 | `require_role` RBAC dependency never exercised | Any regression in `checker` closure goes undetected |
| TC4 | Lockout counter reset after successful login untested | Regression in `reset_failed_attempts` not caught |
| TC5 | Revoked token DB path (revoked=True) not directly tested | Only HTTP revocation path covered |

### Major

| # | Issue |
|---|-------|
| TC6 | No test for expired refresh token DB path (`expires_at < now`) |
| TC7 | Rate limiting BDD scenario has zero coverage (also unimplemented — see C4) |
| TC8 | No `integration/` directory — repository layer untested in isolation |
| TC9 | SQLite dialect used for all E2E tests — timezone handling differs from PostgreSQL |
| TC10 | `test_login_locked_user_cannot_login_with_correct_password` missing |

### Minor

- BDD spec says `expires_in=3600`, implementation returns `900` — spec is wrong
- `test_get_me_unauthenticated` doesn't assert `WWW-Authenticate: Bearer` header
- Timing guard doesn't assert bcrypt takes measurable time

---

## Fix Priorities

### Must fix before merge (Critical)

- [x] C1 — `datetime.utcnow` naive datetime corruption
- [x] C3 — `router.py` RefreshResponse wrapping (ResponseValidationError on every refresh)
- [x] C5 — Swagger UI gated on `APP_ENV`
- [x] C6 — bcrypt in event loop (`asyncio.to_thread`)
- [x] C2 — duplicate `get_db` removed

### Should fix immediately (Major — addressed in this PR)

- [x] M1 — magic numbers extracted to constants
- [x] M5 — dead `BCRYPT_ROUNDS` config field removed
- [x] M11 — `revoke_refresh_token` ownership verification
- [x] M13 — atomic SQL increment for lockout counter

### Deferred (tracked as follow-up)

| Item | Reason |
|------|--------|
| C4 — Rate limiting | Separate feature (Redis middleware); not in Sprint 1 scope |
| C7 — Single-transaction login | Requires repository transaction model refactor |
| M6 — Token rotation | Requires spec decision; documented in Refinement.md |
| M7 — 423 vs 401 for lockout | Intentional spec decision; tests assert 423 |
| M9 — Full secrets validation | Requires MINIO/SMTP secrets to be configured |
| M10 — python-jose → PyJWT | Significant migration; separate PR |
| M14/M15 — Query optimization | Performance tuning; separate PR |
| TC1-TC10 — Test gaps | Follow-up test PR |

---

## What Was Done Well

- bcrypt cost hardcoded at 12 (not configurable — correct)
- Timing dummy hash is a real bcrypt hash (not a fake string)
- JWT type claim prevents token confusion between access/refresh
- Only SHA-256 hash of refresh token stored in DB (breach doesn't yield usable tokens)
- Secrets fail at startup with `sys.exit(1)`, no fallback defaults
- RBAC `require_role` dependency pattern is clean and reusable
- SQL injection surface is zero — pure SQLAlchemy ORM
- Error messages to clients are generic machine codes without stack traces
- Account lockout logic is correctly placed (check before verify → prevents timing oracle)
