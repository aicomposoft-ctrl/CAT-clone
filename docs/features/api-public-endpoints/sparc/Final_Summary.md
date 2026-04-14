# Final Summary — API Public Endpoints

> **Feature:** api-public-endpoints | **Date:** 2026-04-04

---

## Overview

Adds an external integration API to CAT. Brands and agencies can generate API keys through the admin UI and use them to pull monitoring data programmatically — no browser, no JWT refresh, no manual exports.

## Problem & Solution

**Problem:** CAT data is trapped in the web dashboard. BI tools, ERP systems, and automation pipelines cannot authenticate with 15-minute JWT tokens.

**Solution:** Org-scoped API keys (`cat_live_...`) stored as SHA-256 hashes. One `X-API-Key` header unlocks six read-only endpoints covering all CAT domains. Rate-limited at 60 req/min per key via Redis.

## New Endpoints (MVP)

| Method | Path | Purpose |
|--------|------|---------|
| POST | /api/v1/api-keys | Create key (admin/manager) |
| GET | /api/v1/api-keys | List keys |
| DELETE | /api/v1/api-keys/{id} | Revoke key |
| GET | /api/v1/public/skus | SKUs + content scores |
| GET | /api/v1/public/skus/{id}/content-score | Detailed score |
| GET | /api/v1/public/stock | Stock distribution |
| GET | /api/v1/public/prices | Price snapshots |
| GET | /api/v1/public/reviews/summary | Sentiment summary |
| GET | /api/v1/public/alerts | Triggered alerts |

## Technical Approach

- **New domain:** `app/api_keys/` (models, repo, service, router)
- **New domain:** `app/public/` (router + schemas reusing existing repos)
- **1 migration:** `api_keys` table with hash + prefix indexes
- **Auth dependency:** `get_org_by_api_key` in `core/deps.py`
- **Rate limiting:** Redis sliding window, same infra as Celery

## Key Security Properties

- Full key shown exactly once; stored only as SHA-256
- `org_id` derived from key — client cannot spoof another org
- Revocation takes effect immediately (no caching)
- All logs mask key to `cat_live_xxxxxxxx****`

## Implementation Tasks (Phase 3)

```
A: DB migration (api_keys table)           ← independent
B: api_keys domain + deps.py update       ← independent
C: public/ router                          ← depends on B
D: Tests (unit + integration + e2e)        ← depends on B + C
E: main.py wiring                          ← depends on B + C
```

A and B run in parallel. Estimated: 1 implementation session.

## Documentation Package

- PRD.md — Product requirements
- Specification.md — 10 user stories + acceptance criteria
- Architecture.md — Component design + DB schema
- Pseudocode.md — Algorithms + API contracts
- Refinement.md — Edge cases + test plan
- Solution_Strategy.md — Design decisions + TRIZ
- Completion.md — Deployment checklist + monitoring
