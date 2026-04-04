# Completion — Multi-Client Support

> **Feature:** multi-client-support | **Phase:** SPARC Completion | **Date:** 2026-04-04

---

## Pre-Deployment Checklist

- [ ] Migration `0012_add_clients_table` applied to staging
- [ ] Migration `0013_add_brands_client_id` applied to staging
- [ ] Existing orgs: all brands have `client_id = NULL` confirmed
- [ ] All existing e2e tests pass with no client_id in JWT
- [ ] `get_current_user` returns `AuthContext` (not bare `User`) — no broken callers
- [ ] All repo list queries updated with client_id guard
- [ ] `create_access_token` signature updated (client_id param)
- [ ] Frontend client selector deployed and tested

---

## Deployment Sequence

```
1. Deploy migration 0012: CREATE TABLE clients
2. Deploy migration 0013: ALTER TABLE brands ADD COLUMN client_id
3. Deploy API service (no breaking changes — JWT backward compat)
4. Deploy frontend with client selector
5. Smoke test:
   a. Create client
   b. Assign brand to client
   c. POST /auth/switch-client → get new token
   d. GET /skus → verify only client's SKUs returned
   e. GET /skus without client context → all SKUs visible
   f. Deactivate client → verify data hidden
```

---

## Rollback Procedure

```
1. Deploy previous API image
2. alembic downgrade -2 (removes client_id from brands, drops clients table)
3. Existing JWT tokens without client_id claim → unaffected
```

Note: Any tokens with `client_id` claim issued after deployment will fail after rollback (token claim not recognized). Users must re-login. Acceptable rollback tradeoff.

---

## Implementation Task Order (Phase 3)

```
Task A: DB + Migrations (independent)
  - services/api/app/clients/models.py
  - infrastructure/postgres/migrations/0012_create_clients_table.py
  - infrastructure/postgres/migrations/0013_add_brands_client_id.py

Task B: Clients Domain (independent)
  - services/api/app/clients/schemas.py
  - services/api/app/clients/repository.py
  - services/api/app/clients/service.py
  - services/api/app/clients/router.py
  - services/api/app/clients/__init__.py

Task C: Auth + Context (depends on B)
  - services/api/app/core/security.py  (update create_access_token, decode_token)
  - services/api/app/core/deps.py      (update get_current_user → AuthContext)
  - services/api/app/auth/router.py    (add switch-client endpoint)
  - services/api/app/auth/service.py   (add switch_client_context)

Task D: Domain query updates (depends on C)
  - services/api/app/catalog/repository.py  (brand + sku queries)
  - services/api/app/catalog/router.py      (brand PATCH for client assignment)
  All other domains: add client_id guard to list queries

Task E: Tests (depends on B + C + D)
  - services/api/tests/unit/test_client_service.py
  - services/api/tests/integration/test_client_repository.py
  - services/api/tests/e2e/test_multi_client_api.py

Task F: Wire up (depends on B + C)
  - services/api/app/main.py  (register clients router)
```

---

## Monitoring

| Metric | Threshold | Alert |
|--------|-----------|-------|
| 401 INVALID_CLIENT_CONTEXT rate | > 1% of authenticated requests | Investigate token forgery |
| Client switch latency | > 200ms | Check DB client lookup |
| Cross-client query log | Any occurrence | Critical incident |
