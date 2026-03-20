# Security Patterns Library

Reference library of security patterns extracted from real-project harvest insights.
Used by toolkit generator modules (03, 04, 05) when generating security.md rules,
secrets-management.md, security-patterns/ skill, and code-reviewer agent.

## Critical Patterns (Must-Have for Multi-Tenant Systems)

### S-01: RLS Bypass Prevention — Pool vs Client Query

**Problem:** Tenant middleware sets `app.tenant_id` via `SET LOCAL` on a dedicated
PoolClient (`req.dbClient`), but repositories use `pool.query()` (shared pool).
The query runs on a different connection without tenant context — RLS is bypassed.

**Pattern:**
```
RULE: NEVER use pool.query() in multi-tenant systems with RLS.
ALWAYS pass the tenant-scoped dbClient from middleware through service layer to repository.
Every database query MUST use the same connection where SET LOCAL was executed.
```

**Detection:** Search for `pool.query()` in repository files when RLS is enabled.

**Generated Rule (security.md):**
```markdown
- Multi-tenant RLS: All database queries MUST use tenant-scoped connection (req.dbClient),
  NEVER the shared pool. Verify by grepping for pool.query() — any hit is a security bug.
```

---

### S-02: SQL Injection via SET LOCAL

**Problem:** String interpolation in `SET LOCAL app.tenant_id = '${tenantId}'`
is an SQL injection vector even with UUID validation.

**Pattern:**
```
RULE: NEVER use string interpolation for SET LOCAL.
ALWAYS use parameterized set_config():
  SELECT set_config('app.tenant_id', $1, true)
```

**Detection:** Search for `SET LOCAL` with template literals or string concatenation.

**Generated Rule (security.md):**
```markdown
- Parameterized config: Use `set_config('key', $1, true)` instead of
  `SET LOCAL key = '${value}'`. Applies to all session-level config.
```

---

### S-03: Fail-Fast Secret Validation at Startup

**Problem:** Service A falls back to `'dev-secret-change-me'` when JWT_SECRET is
missing, while Service B uses `process.env.JWT_SECRET!`. Creates split-brain:
signing uses weak fallback, verification uses undefined.

**Pattern:**
```
RULE: NEVER provide fallback values for security-critical secrets.
ALWAYS validate at startup and exit with process.exit(1) if missing or too short.

Required checks:
- JWT_SECRET: exists AND length >= 32 characters
- DATABASE_URL: exists AND not localhost in production
- API keys: exist AND not placeholder values
```

**Generated Rule (security.md):**
```markdown
- Startup secret guard: All security secrets (JWT_SECRET, API keys, encryption keys)
  MUST be validated at application startup. Missing or weak secrets MUST cause
  immediate process.exit(1). NEVER use fallback defaults for secrets.
```

---

### S-04: Cross-Tenant Entity Ownership

**Problem:** API endpoint accepts an entity ID (e.g., operatorId) without
verifying that the entity belongs to the requesting tenant. RLS on the target
table may not cover this cross-reference.

**Pattern:**
```
RULE: Before using any entity ID from request params in a cross-table operation,
verify the entity belongs to the same tenant:
  1. Load entity by ID
  2. Check entity.tenantId === request.tenantId
  3. Return 403 if mismatch
```

**Generated Rule (security.md):**
```markdown
- Cross-tenant ownership: When an API accepts entity IDs (operatorId, userId, etc.),
  ALWAYS verify entity.tenantId matches the requesting tenant before any operation.
  RLS alone may not protect cross-table references.
```

---

### S-05: Webhook Signature Verification

**Problem:** Webhook endpoints accept any POST without HMAC/signature verification.
Attackers can inject fake messages if webhook URLs are discovered.

**Pattern:**
```
RULE: Every webhook endpoint MUST verify the request signature:
- Telegram: verify X-Telegram-Bot-Api-Secret-Token header
- Stripe: verify Stripe-Signature header with webhook secret
- GitHub: verify X-Hub-Signature-256 header
- Generic: verify HMAC-SHA256 of body with shared secret
```

**Generated Rule (security.md):**
```markdown
- Webhook HMAC: Every webhook endpoint MUST verify request signature/HMAC.
  NEVER accept unsigned webhook requests. Log and reject unsigned payloads.
```

---

## High-Priority Patterns

### S-06: Singleton Service Instances

**Problem:** Creating service instances per-request (e.g., `Service.fromEnv()` in
route handler) means stateful components like circuit breakers never accumulate
failure state and never trigger protection.

**Pattern:**
```
RULE: Services with stateful protection mechanisms (circuit breakers, rate limiters,
connection pools) MUST be created as singletons at application startup.
NEVER create per-request instances of stateful services.
```

**Impact on Generated Code:**
- In architect.md agent: include singleton pattern for infrastructure services
- In coding-style.md rule: "stateful services are singletons, injected at startup"

---

### S-07: Environment-Specific Security Posture

**Pattern:**
```
RULE: Security posture MUST match environment:
- Development: relaxed CORS, verbose errors, debug logging
- Staging: production-like security, sanitized test data
- Production: strict CORS, generic errors, structured logging only

NEVER: same security config across all environments
NEVER: expose stack traces in production error responses
```

---

## Integration Patterns for Generated Toolkit

### How Patterns Map to Generated Files

| Pattern | security.md | secrets-management.md | code-reviewer.md | architect.md |
|---------|------------|----------------------|-------------------|--------------|
| S-01 RLS Bypass | Rule | — | Check | Architecture note |
| S-02 SQL Injection | Rule | — | Check | — |
| S-03 Secret Validation | Rule | Primary content | Check | Startup validation |
| S-04 Cross-Tenant | Rule | — | Check | — |
| S-05 Webhook HMAC | Rule | Secret storage | Check | — |
| S-06 Singleton | — | — | Check | Architecture pattern |
| S-07 Env Security | Rule | Env-specific rules | — | Environment guide |

### Usage in Module 03 (Generate P0)

When generating `security.md` rule (Item 2), include applicable patterns:
- IF multi-tenant detected: S-01, S-02, S-04
- IF has_external_apis: S-03, S-05
- IF has_database: S-01, S-02
- ALWAYS: S-03, S-07

### Usage in Module 04 (Generate P1)

When generating `code-reviewer.md` agent (Step 2b), add security review checklist
from applicable patterns to the agent's review criteria.

When generating `architect.md` agent (Step 2c), include S-06 singleton pattern
and S-07 environment posture in architecture guidelines.

### Usage in brutal-honesty-review

When reviewing code in Linus Mode, check for violations of all S-01 through S-07
patterns as CRITICAL findings. Security violations should always trigger
Level 3 (Brutal) calibration.
