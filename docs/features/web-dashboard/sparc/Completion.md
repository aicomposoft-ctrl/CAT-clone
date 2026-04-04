# Completion — Web Dashboard
> Feature: web-dashboard | SPARC Phase 7 | CAT Project

---

## 1. Pre-Deployment Checklist

- [ ] All E2E tests pass (Playwright)
- [ ] All unit + integration tests pass (Jest, coverage ≥ 80%)
- [ ] Bundle size checked: `npm run build` → dist < 2MB gzipped
- [ ] Environment variables set in `.env` (VITE_API_URL)
- [ ] Nginx config proxies `/api/v1/*` to `api` service
- [ ] CSP headers configured in Nginx
- [ ] ECharts resize tested in all drawers/modals
- [ ] Accessibility audit: axe-core scan, no critical violations
- [ ] Cross-tenant isolation verified: viewer from org_a cannot see org_b data
- [ ] Token refresh flow tested: token expire → auto-refresh → continue

---

## 2. Deployment Sequence

```
1. Build frontend image:
   docker compose build frontend

2. Start with other services:
   docker compose up -d

3. Verify nginx routing:
   curl http://localhost/api/v1/health → 200

4. Verify frontend loads:
   open http://localhost → /login page visible

5. Smoke test:
   - Login as test user
   - Check Dashboard KPIs load
   - Check Content table loads with data
   - Check Export downloads file
```

---

## 3. Rollback Procedure

```bash
# If frontend breaks after deploy:
docker compose stop frontend
docker compose up -d frontend --scale frontend=0

# Or roll back to previous image:
docker tag cat-frontend:previous cat-frontend:latest
docker compose up -d frontend
```

---

## 4. CI/CD Configuration (GitHub Actions sketch)

```yaml
name: Frontend CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: npm ci
        working-directory: services/frontend
      - run: npm run lint
        working-directory: services/frontend
      - run: npm test -- --coverage
        working-directory: services/frontend
      - run: npm run build
        working-directory: services/frontend

  e2e:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - run: docker compose up -d
      - run: npx playwright test
        working-directory: services/frontend
```

---

## 5. Monitoring & Alerting

| Metric | Threshold | Alert |
|--------|-----------|-------|
| Frontend 5xx rate | > 1% of requests | Slack |
| LCP (Core Web Vitals) | > 2.5s | Dashboard annotation |
| JS bundle load time | > 3s | Log warning |
| API response p95 | > 500ms | PagerDuty |
| 401 rate (token expiry storm) | > 5% | Slack — potential refresh bug |

---

## 6. Logging Strategy

- Nginx access logs: structured JSON, retained 30 days
- Frontend errors: `console.error` → Sentry (add `@sentry/react` in Sprint 2)
- API calls: logged by FastAPI middleware (request_id, duration, status)
- Auth events: login, logout, token refresh logged to PostgreSQL `audit_log`

---

## 7. Handoff Checklists

### For Development Team
- [ ] Read `docs/features/web-dashboard/sparc/Architecture.md` — folder structure
- [ ] Run `npm install` in `services/frontend/`
- [ ] Set up `.env` from `.env.example`
- [ ] Run `npm run dev` → http://localhost:5173
- [ ] Read `.claude/rules/coding-style.md` for TypeScript/React conventions

### For QA Team
- [ ] E2E scenarios in `Refinement.md` Section 2 — run via Playwright
- [ ] Test with 3 different role accounts: admin, manager, viewer
- [ ] Verify cross-tenant isolation (2 test orgs needed)
- [ ] Test export files open correctly in Excel

### For Operations Team
- [ ] Frontend container: `cat-frontend`, port 80 behind Nginx
- [ ] No persistent state in frontend container (stateless)
- [ ] Logs via `docker compose logs frontend`
- [ ] Scale: single replica is sufficient (stateless SPA)
