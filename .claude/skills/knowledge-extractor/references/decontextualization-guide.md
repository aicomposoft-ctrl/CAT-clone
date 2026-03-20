# Decontextualization Guide

How to transform project-specific artifacts into universal, reusable toolkit entries.

---

## Core Principle

> **Decontextualization is NOT renaming variables. It's extracting the PRINCIPLE
> and providing an implementation that works in any context.**

The goal is to separate the **universal insight** from the **project-specific implementation**.

---

## The Decontextualization Checklist

For every artifact, verify each item before it enters the toolkit:

### 1. Names & References
- [ ] No company/product names → replaced with `{{PROJECT_NAME}}` or generic
- [ ] No team member names → removed or replaced with roles
- [ ] No project-specific variable names → use descriptive generic names
- [ ] No internal URLs → removed or parameterized
- [ ] No specific database/table names → generic schema references

### 2. Paths & Configuration
- [ ] No absolute paths → relative or `{{PROJECT_ROOT}}`
- [ ] No hardcoded ports → `{{PORT}}` or env variable
- [ ] No hardcoded API keys → `{{API_KEY}}` with note about secure storage
- [ ] No environment-specific configs → parameterized with defaults
- [ ] Config values documented in parameter table

### 3. Dependencies
- [ ] External dependencies listed explicitly
- [ ] Version constraints documented
- [ ] Alternative libraries mentioned (if applicable)
- [ ] No implicit dependencies (things that "just work" because of project setup)

### 4. Context
- [ ] Works without the original project's other modules
- [ ] Import/require statements are generic or documented
- [ ] No circular dependencies with project code
- [ ] Can be copy-pasted into new project and work (with documented setup)

---

## Decontextualization Techniques

### Technique 1: Extract Interface

**Before:**
```typescript
// Tightly coupled to UserService
function rateLimitMiddleware(userService: UserService) {
  return (req: Request) => {
    const user = userService.getUser(req.userId);
    if (user.requestCount > user.plan.limit) {
      throw new RateLimitError();
    }
  };
}
```

**After:**
```typescript
// Generic — works with any identity provider
interface RateLimitSubject {
  id: string;
  currentCount: number;
  limit: number;
}

interface RateLimitProvider {
  getSubject(requestId: string): Promise<RateLimitSubject>;
  increment(subjectId: string): Promise<void>;
}

function rateLimitMiddleware(provider: RateLimitProvider) {
  return async (req: Request) => {
    const subject = await provider.getSubject(req.headers['x-subject-id']);
    if (subject.currentCount >= subject.limit) {
      throw new RateLimitError(subject.id, subject.limit);
    }
    await provider.increment(subject.id);
  };
}
```

**What changed:** Replaced concrete `UserService` with generic `RateLimitProvider` interface.

### Technique 2: Parameterize

**Before:**
```yaml
# docker-compose.yml for the e-commerce project
services:
  api:
    build: ./backend
    ports:
      - "3000:3000"
    environment:
      DATABASE_URL: postgres://ecommerce:secret@db:5432/ecommerce_dev
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: ecommerce_dev
      POSTGRES_PASSWORD: secret
```

**After:**
```yaml
# Template: Node.js + PostgreSQL Docker Compose
# Parameters: {{SERVICE_NAME}}, {{PORT}}, {{DB_NAME}}, {{DB_PASSWORD}}
services:
  {{SERVICE_NAME}}:
    build: ./backend
    ports:
      - "${PORT:-3000}:${PORT:-3000}"
    environment:
      DATABASE_URL: postgres://${DB_USER:-app}:${DB_PASSWORD}@db:5432/${DB_NAME}
  db:
    image: postgres:${POSTGRES_VERSION:-15}
    environment:
      POSTGRES_DB: ${DB_NAME}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
```

**What changed:** All project-specific values → environment variables with defaults.

### Technique 3: Document the Principle

**Before (code comment in project):**
```
// HACK: Don't use Promise.all for Stripe API calls — it triggers rate limit
```

**After (toolkit rule):**
```markdown
# Rule: Sequential External API Calls for Rate-Limited Services

## Rule
When calling rate-limited external APIs (Stripe, Twilio, etc.),
use sequential execution instead of Promise.all/parallel.

## Why
Rate-limited APIs count requests per time window. Parallel requests
arrive simultaneously and exceed the limit, causing failures that
are hard to debug (they appear intermittent).

## Example (what goes wrong)
\`\`\`typescript
// ❌ BAD — triggers rate limit
const results = await Promise.all(
  items.map(item => stripeApi.createCharge(item))
);
// Error: Rate limit exceeded (429) — but only sometimes!
\`\`\`

## Correct Approach
\`\`\`typescript
// ✅ GOOD — respects rate limits
const results = [];
for (const item of items) {
  results.push(await externalApi.call(item));
  // Optional: add small delay for strict rate limits
}
\`\`\`

## Scope
Universal — applies to any rate-limited external API

## Variants
- With retry + backoff for transient failures
- With queue for high-volume scenarios
- With batch endpoint if API supports it
```

**What changed:** Specific Stripe hack → universal rule about rate-limited APIs.

### Technique 4: Provide Variants

When the original implementation is language/framework-specific,
provide multiple variants:

```markdown
# Pattern: Retry with Exponential Backoff

## Variant A: TypeScript (Node.js)
\`\`\`typescript
async function retry<T>(fn: () => Promise<T>, maxRetries = 3): Promise<T> {
  for (let i = 0; i < maxRetries; i++) {
    try { return await fn(); }
    catch (e) {
      if (i === maxRetries - 1) throw e;
      await sleep(Math.pow(2, i) * 1000);
    }
  }
  throw new Error('unreachable');
}
\`\`\`

## Variant B: Python
\`\`\`python
async def retry(fn, max_retries=3):
    for i in range(max_retries):
        try: return await fn()
        except Exception as e:
            if i == max_retries - 1: raise
            await asyncio.sleep(2 ** i)
\`\`\`

## Variant C: Rust
\`\`\`rust
async fn retry<F, T, E>(f: F, max_retries: u32) -> Result<T, E>
where F: Fn() -> Pin<Box<dyn Future<Output = Result<T, E>>>> {
    // ...
}
\`\`\`
```

---

## Red Flags (Incomplete Decontextualization)

| Red Flag | Problem | Fix |
|----------|---------|-----|
| `import { UserModel } from '../models'` | Project-specific import | Use interface/generic |
| `const API_URL = 'https://api.mycompany.com'` | Hardcoded URL | Use env variable |
| `// Works because we use Express 4.x` | Implicit dependency | Document explicitly |
| Function name `handleStripeWebhook` | Too specific | Rename to `handleWebhook` |
| `config.ecommerceSettings.taxRate` | Domain-specific config | Extract to parameters |
| Only works with PostgreSQL | Missing variants | Add alternative DB support |

---

## Decontextualization by Category

| Category | Key Focus |
|----------|-----------|
| **Skills** | Remove domain context, keep methodology |
| **Commands** | Parameterize paths and args, document tool deps |
| **Hooks** | Make trigger event configurable |
| **Rules** | State universal principle, not project symptom |
| **Templates** | Replace ALL hardcoded values with `{{PLACEHOLDERS}}` |
| **Patterns** | Describe the APPROACH with multiple implementations |
| **Snippets** | Ensure standalone execution, document dependencies |
