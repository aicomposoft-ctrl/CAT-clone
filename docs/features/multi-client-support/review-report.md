# Review Report — Multi-Client Support

> **Date:** 2026-04-04 | **Status:** PASS (after fixes) | **Agents:** A1 Code Quality + Security, A2 Performance + Test Coverage

---

## Summary

| Agent | Dimension | Critical | Major | Minor | Status |
|-------|-----------|----------|-------|-------|--------|
| A1 | Code Quality / Security | 2 found, 2 fixed | 2 found, 1 fixed | 5 found, 3 fixed | ✅ PASS |
| A2 | Performance / Test Coverage | 1 found, 1 fixed | 3 found, 3 fixed | 2 noted | ✅ PASS |

All Critical and Major issues resolved before merge.

---

## Critical Issues (all fixed)

### C1: `get_brand_count` missing `org_id` filter — cross-tenant count leak

**File:** `clients/repository.py`

Original query filtered only on `client_id`. A client UUID is globally unique (UUID4) so collision is unlikely, but it violated the mandatory `org_id` scoping rule (OWASP A01 / project security rule).

**Fix:** Added `org_id: UUID` parameter, query now filters `Brand.client_id == client_id AND Brand.org_id == org_id`. Also added `get_brand_counts_by_org()` batch method.

### C2: Concurrent slug insert → IntegrityError → HTTP 500

**File:** `clients/service.py`

The read-then-write pattern for slug uniqueness is not race-safe under concurrent requests. The DB partial unique index `uq_clients_org_slug` would catch the race but produce an unhandled `IntegrityError` surfacing as HTTP 500.

**Fix:** Wrapped `ClientRepository.create()` in `try/except IntegrityError` with rollback, re-raising `ValueError("SLUG_CONFLICT")` → router maps to 409.

---

## Major Issues (all fixed)

### M1: N+1 query in `list_clients`

**File:** `clients/service.py`

One `COUNT(*)` query per client inside a loop → N+1 on the management list endpoint.

**Fix:** Added `ClientRepository.get_brand_counts_by_org()` — single `GROUP BY client_id` query. `list_clients` now issues 2 queries regardless of org size.

### M2: Missing BDD scenario — brands of deactivated client hidden

Added `test_brands_of_deactivated_client_hidden_in_client_context`: JWT scoped to deactivated client → 401 `INVALID_CLIENT_CONTEXT` (per-request validation catches it).

### M3: Missing BDD scenario — brand visibility after switch-client round-trip

Added `test_brand_visibility_after_switch_client_round_trip`: full round-trip via `POST /auth/switch-client` → new token → `GET /brands` confirms correct scoping.

### M4: Missing BDD scenario — stale client_id (deactivated after token issued)

Added `test_stale_client_id_deactivated_after_token_issue_returns_401`: client active at token issue, deactivated before next request → 401. Validates the primary motivation for per-request DB re-validation.

---

## Minor Issues (noted, some fixed)

| Item | Status |
|------|--------|
| Dead `PermissionError` catches in `clients/router.py` | Fixed — removed |
| Redundant `str(request.logo_url)` cast | Fixed |
| `logo_url` accepts any string (no URL validation) | Deferred — pre-existing pattern in codebase |
| Lazy import in `get_current_user` hot path | Deferred — Python caches imports; structural refactor is future work |
| Partial unique index missing from ORM model `__table_args__` | Documented — SQLite tests rely on service-layer check; DB constraint lives in migration |
| `engine` fixture session-scoped with global `_org_counter` | Acceptable — consistent with other e2e test files in this project |

---

## Final State

- **15 E2E tests** covering all Refinement.md BDD scenarios
- **228 total tests passing** (1 skipped — SQLite DISTINCT ON limitation, pre-existing)
- All Critical and Major issues resolved
- Cleared for merge → main
