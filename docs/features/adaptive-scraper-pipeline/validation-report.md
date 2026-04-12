# Validation Report — Adaptive Scraper Pipeline

**Date:** 2026-04-12
**Iteration:** 1 (pre-fix)

---

## Scores Summary

| Agent | Dimension | Score | Status |
|-------|-----------|-------|--------|
| 1 | User Story Completeness (INVEST) | 80/100 avg | PASS |
| 2 | BDD Scenario Coverage | 42/100 | **BLOCKED** |
| 3 | Acceptance Criteria Clarity | 82/100 | PASS |
| 4 | Technical Feasibility | 58/100 | **BLOCKED** |
| 5 | Security / Multi-tenant | 71/100 | **BLOCKED** |

---

## BLOCKED Issues (must fix before implementation)

### BLOCK-1 (Security CRITICAL): api_token_encrypted on global platforms table

**Problem:** `platforms` is a global reference table (no `org_id`). Storing `api_token_encrypted` on it means Org B using WB platform will have access to Org A's decrypted WB Seller API token — their scraping jobs decrypt and use Org A's token, charging Org A's API quota and exposing Org A's catalog access.

**Fix:** Create `org_platform_credentials` table:
```sql
CREATE TABLE org_platform_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    platform_id UUID NOT NULL REFERENCES platforms(id),
    api_token_encrypted TEXT,
    api_token_type VARCHAR(20),
    fallback_chain JSONB,
    selectors JSONB,
    UNIQUE (org_id, platform_id)
);
```
Remove `api_token_encrypted`, `api_token_type`, `fallback_chain`, `selectors` from the global `platforms` table. Keep `scraper_mode` as global default; per-org override goes in `org_platform_credentials`.

ScraperRouter must load credentials from `org_platform_credentials` filtered by `org_id`.

---

### BLOCK-2 (Feasibility CRITICAL): page.accessibility.snapshot() unavailable in Python

**Problem:** `page.accessibility.snapshot()` exists in Playwright **Node.js** only. The Python bindings do not expose this API (removed in recent versions).

**Fix:** Use `page.locator("body").aria_snapshot()` (Playwright Python ≥ 1.41) which returns an ARIA tree string directly. Alternative: `await page.content()` + BeautifulSoup to extract semantic structure.

```python
# WRONG (Node.js API):
snapshot = await page.accessibility.snapshot(interesting_only=True)

# CORRECT (Python Playwright ≥ 1.41):
aria_snapshot = await page.locator("body").aria_snapshot()
```

---

### BLOCK-3 (Feasibility CRITICAL): BrowserPool singleton incompatible with Celery prefork

**Problem:** The collector uses prefork pool. Chromium processes are not fork-safe — a BrowserPool initialized via `@worker_init` signal will be forked into child processes, causing undefined browser state and crashes.

**Fix:** Separate service `collector-playwright` using Celery **solo** pool (single-threaded, safe for asyncio):
```yaml
# docker-compose.yml addition:
collector-playwright:
  image: mcr.microsoft.com/playwright/python:v1.44.0-jammy
  command: celery -A app.celery_app worker -Q playwright --pool=solo --concurrency=1
```
BrowserPool initialized once per process (safe in solo pool). L2/L3 tasks routed to `playwright` queue.

---

### BLOCK-4 (BDD): Zero happy-path scenarios

**Problem:** All 7 edge case scenarios cover failure paths only. No success-path BDD scenarios exist.

**Fix:** Add to Specification.md:

```
Scenario: L0 success — WB Seller API returns product data
  Given platform WB has valid api_token_encrypted and scraper_mode='auto'
  When ScraperRouter.collect(WB_PLATFORM_ID, nm_id, DataType.CONTENT, org_id)
  Then returns ContentData with title, description, image_url
  And result.scraper_level == 0
  And duration < 2000ms

Scenario: L2 XHR interception resolves product JSON
  Given platform has scraper_mode='playwright'
  And page emits XHR with Content-Type: application/json containing price field
  When PlaywrightScraper.collect(url, DataType.PRICE)
  Then PriceData parsed from intercepted JSON
  And DOM selectors NOT queried (interception took priority)

Scenario: L3 agent extracts data from accessibility tree
  Given platform has scraper_mode='agent'
  When AgentScraper.collect(url, DataType.CONTENT)
  Then page.locator("body").aria_snapshot() called
  And snapshot sent to claude-haiku-4-5 model
  And response JSON validated against ContentData schema
  And result cached in Redis for 1 hour
```

---

## MAJOR Issues (fix before merge, not blocking planning)

### MAJOR-1: PLATFORM_SECRET_KEY rotation — no MultiFernet

**Problem:** Fernet key rotation requires re-encrypting all tokens simultaneously. No `MultiFernet` usage, no `key_version` column, no migration script.

**Fix:** Use `cryptography.fernet.MultiFernet` with key list from env:
```python
from cryptography.fernet import MultiFernet, Fernet
keys = [Fernet(k) for k in settings.PLATFORM_SECRET_KEYS.split(",")]
f = MultiFernet(keys)  # tries keys in order, encrypts with first
```

### MAJOR-2: Prompt injection via accessibility tree

**Problem:** Scraped page content is concatenated directly into the Claude prompt. Hostile pages can embed injection text.

**Fix:** Wrap tree in XML delimiters and use system prompt for instructions:
```python
messages=[{
    "role": "user",
    "content": f"<accessibility_tree>\n{snapshot[:8000]}\n</accessibility_tree>"
}]
# Move extraction instructions to system= parameter
```

---

## MINOR Issues (document as follow-up)

- US-03: Claude API cost budget per org not specified (Refinement R-02 covers it at 100 calls/day, needs cross-reference in Specification)
- NFR-01: Latency thresholds need percentile definition (p95 recommended)
- NFR-03: PII definition for L3 prompts not enumerated
- L1 level not covered by any BDD scenario
- Alert deduplication for repeated L0 failures not specified

---

## Next Steps

1. Update `Architecture.md` — add `org_platform_credentials` table, separate playwright service
2. Update `Pseudocode.md` — fix `page.accessibility.snapshot()` → `page.locator("body").aria_snapshot()`, fix ScraperRouter to load from `org_platform_credentials`
3. Update `Specification.md` — add happy-path BDD scenarios
4. Update `Refinement.md` — add MAJOR-1 MultiFernet fix, MAJOR-2 prompt injection fix
5. Re-run validation (iteration 2)
