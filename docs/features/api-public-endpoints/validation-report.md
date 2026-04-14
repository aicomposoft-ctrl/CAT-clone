# Validation Report — API Public Endpoints

> **Date:** 2026-04-04 | **Status:** PASS | **Overall Score: 83.3/100**

---

## Summary

| Agent | Dimension | Score | Status |
|-------|-----------|-------|--------|
| A1 | User Story Completeness | 82.8 | ✅ PASS |
| A2 | BDD Scenario Coverage | 78.0 | ✅ PASS |
| A3 | Acceptance Criteria Clarity | 79.8 | ✅ PASS |
| A4 | Technical Feasibility | 88.0 | ✅ PASS |
| A5 | Security / Multi-tenant | 88.0 | ✅ PASS |
| **Average** | | **83.3** | ✅ **PASS** |

Gate: ≥ 70/100 per dimension. Zero BLOCKED items. → **Cleared for Phase 3.**

---

## Critical Issues (fix during implementation)

### C1: Potential Timing Attack on Hash Lookup (Security A5)
- **Location:** `get_org_by_api_key` dependency — hash lookup branch
- **Risk:** DB query timing difference between "found" vs "not found" could theoretically reveal key existence
- **Fix:** Wrap hash comparison with `secrets.compare_digest()` or add constant-delay sentinel response path

---

## Major Issues (fix during implementation)

### M1: Query Endpoints Missing Error Paths in Acceptance Criteria (A1, A3)
- US-06 through US-10 lack explicit error path acceptance criteria
- **Fix:** Implement explicit 422 on invalid filter, 200 with empty list when no data — add comments in router code

### M2: US-10 Clarity Too Low (A3 — score 68)
- `alert_type` values not enumerated, timezone handling missing, HTTP status codes absent
- **Fix:** Add Pydantic enum for `alert_type` in schemas.py; always return UTC timestamps

### M3: fire-and-forget Exception Handling (A4)
- `asyncio.create_task()` for `last_used_at` can fail silently on shutdown
- **Fix:** Wrap in try/except with `logger.warning()`, never propagate

### M4: Rate Limit Prefix Sharing (A5)
- 8-char prefix collision means two keys could theoretically share a rate limit counter
- **Fix:** Rate limit key should be based on `key_hash[:16]` (first 16 chars of hash) rather than `key_prefix` — avoids collision while still avoiding full hash exposure in Redis keys

---

## Minor Issues (follow-up tasks)

- A2: Add cross-org test for alerts endpoint (not just SKUs)
- A2: Add pagination edge case tests (page=0, from_date > to_date)
- A3: US-07 response schema needs explicit field types
- A4: `last_used_at` exception should be logged with key prefix (masked)

---

## Validation Sign-off

All 5 dimensions above minimum threshold (70). Zero BLOCKED user stories. Two Critical/Major items are implementation-level fixes, not design blockers.

**Proceed to Phase 3: Implementation.**
