# Completion — API Public Endpoints

> **Feature:** api-public-endpoints | **Phase:** SPARC Completion | **Date:** 2026-04-04

---

## Pre-Deployment Checklist

- [ ] Alembic migration `add_api_keys_table` tested on staging DB
- [ ] `api_keys.key_hash` index confirmed present
- [ ] Redis connection available in API container (already used by Celery)
- [ ] `cat_live_*` / `cat_test_*` key format documented in user-facing docs
- [ ] Rate limit (60/min) validated under load test
- [ ] Full key shown-once behavior confirmed in E2E test
- [ ] Cross-tenant isolation test passing
- [ ] No full API key values in any log output (manual check)
- [ ] Swagger UI updated with new `/public/` and `/api-keys/` endpoints

---

## Deployment Sequence

```
1. Deploy migration: alembic upgrade head
   → adds api_keys table
   → adds indexes on key_hash, key_prefix, org_id

2. Deploy API service (zero-downtime rolling restart)
   → new endpoints registered in main.py
   → no breaking changes to existing endpoints

3. Smoke test:
   a. POST /api/v1/api-keys (with admin JWT)
   b. GET  /api/v1/public/skus (with returned key)
   c. DELETE /api/v1/api-keys/{id}
   d. GET  /api/v1/public/skus (with revoked key → expect 401)
```

---

## Rollback Procedure

```
1. Deploy previous API image tag
2. Run: alembic downgrade -1  (drops api_keys table)
3. Verify existing JWT endpoints still functional
```

Note: Rolling back removes all created API keys. Communicate to users before rollback.

---

## Monitoring

| Metric | Threshold | Alert |
|--------|-----------|-------|
| 401 rate on `/api/v1/public/*` | > 10% of requests | Slack #alerts |
| 429 rate on `/api/v1/public/*` | > 5% of requests | Slack #alerts (legitimate spike) |
| p99 latency on `/api/v1/public/*` | > 300ms | PagerDuty |
| API key creation rate | > 50/hour per org | Review (potential abuse) |

---

## Implementation Order (for parallel Tasks in Phase 3)

```
Task A: DB + Migration
  - services/api/app/api_keys/models.py
  - infrastructure/postgres/migrations/versions/XXX_add_api_keys_table.py

Task B: API Key Domain
  - services/api/app/api_keys/schemas.py
  - services/api/app/api_keys/repository.py
  - services/api/app/api_keys/service.py
  - services/api/app/api_keys/router.py
  - services/api/app/core/deps.py  (add get_org_by_api_key)

Task C: Public Endpoints
  - services/api/app/public/schemas.py
  - services/api/app/public/router.py
  Depends on: Task B (needs get_org_by_api_key)

Task D: Tests
  - services/api/tests/unit/test_api_key_service.py
  - services/api/tests/integration/test_api_key_repository.py
  - services/api/tests/e2e/test_public_api.py
  Depends on: Task B + C

Task E: Wire up
  - services/api/app/main.py  (register new routers)
  Depends on: Task B + C
```

Tasks A and B can run in parallel. Task C depends on B. Task D depends on B+C. Task E is last.
