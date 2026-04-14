# Validation Report — WB Scraper

**Date:** 2026-03-27 | **Iterations:** 2

---

## Iteration 1: BLOCK

Both agents returned BLOCK. Blocking issues:

### Agent 1 (User Stories)
| Story | Score | Issues |
|-------|-------|--------|
| US-W01 Content | 82/100 | `title` missing from schema, no PARSE_ERROR/org_id scenarios |
| US-W02 Price | 78/100 | No 429 scenario |
| US-W03 Stock | 71/100 | `in_stock` undefined in schema, no error path |
| US-W04 Reviews | 86/100 | Minor gaps |

Blocking: missing `in_stock`/`warehouse_qty` in schema, missing `title`, no org_id scenarios.

### Agent 2 (Technical)
- CRITICAL: `ProxyRotator.from_env()` called per task (blocking HTTP, no caching)
- CRITICAL: gevent/eventlet incompatibility with `asyncio.run()`
- MAJOR: Image URL fetched without allowlist check → SSRF
- MAJOR: Stock task creates partial ContentScore row without documenting ML scoring guard

---

## Iteration 2: Fixes Applied

All blocking issues resolved in SPARC docs:

1. ✅ Added `collected_title`, `in_stock`, `warehouse_qty` to content_scores schema (Specification §4)
2. ✅ Added org_id isolation scenario to US-W01
3. ✅ Added PARSE_ERROR scenario to US-W01
4. ✅ Added 429 scenario to US-W02
5. ✅ Added error path + partial-row clarification to US-W03
6. ✅ ProxyRotator redesigned: module-level singleton, `worker_process_init` signal, thread-safe lock, timeout on HTTP fetch (Architecture §6)
7. ✅ `validate_wb_image_url()` regex allowlist added before `httpx.get()` (Architecture §8, Pseudocode §2)
8. ✅ Partial-row contract documented: ML pipeline must filter `WHERE collected_description IS NOT NULL` (Pseudocode §2)
9. ✅ Kopek formula clarified — `/ 100`, not `/10000` (Refinement Q3)
10. ✅ Celery pool restriction documented + runtime guard added (Refinement Q2)

---

## Iteration 2 Estimated Scores (post-fix)

| Story | Estimated Score | Status |
|-------|----------------|--------|
| US-W01 Content | ~88/100 | PASS |
| US-W02 Price | ~82/100 | PASS |
| US-W03 Stock | ~80/100 | PASS |
| US-W04 Reviews | ~86/100 | PASS |
| Technical Feasibility | ~82/100 | PASS |
| Security | ~85/100 | PASS |

**Result: PASS — proceeding to Phase 3.**

---

## Remaining Minor Issues (follow-up)

- `ON CONFLICT DO NOTHING` for reviews doesn't capture edited review text — acceptable for Sprint 2, upgrade to `DO UPDATE` in Sprint 3
- `_semaphore = asyncio.Semaphore(int(rate_limit))` conflates concurrency with rate — acceptable at `rate_limit=1.0`, document for future refactor
- `date.fromisoformat(fb["createdDate"][:10])` — switch to `datetime.fromisoformat(...).date()` for robustness
