# /run [mvp|all] — Autonomous Development Loop

## Usage
```
/run          # MVP features only (priority 1-2)
/run mvp      # Same as /run
/run all      # ALL features until done
```

## What It Does

Autonomous loop: `/start` → `/next` → `/go` → repeat until done.

```
/run
  ├── /start              — read docs, verify env
  ├── loop:
  │     ├── /next         — pick next feature from roadmap
  │     ├── /go <feature> — complexity score → /plan | /feature
  │     ├── commit + push — after each feature
  │     └── repeat until: no more features (or mvp done)
  └── /docs               — generate bilingual documentation
```

## Complexity Scoring (used by /go)

```
Score 1-3  → /plan  — quick implementation, no full SPARC lifecycle
Score 4-6  → /feature — full 4-phase lifecycle (plan → validate → implement → review)
Score 7-10 → /feature + swarm agents — 5 validation + 5 review agents
```

Factors: number of services touched, DB schema changes, ML pipeline changes,
security implications, multi-tenant scope.

## MVP Feature Set (priority 1-2)

From `.claude/feature-roadmap.json` — pick features with `"priority": 1` or `"priority": 2`:

1. Auth (JWT, RBAC, multi-tenant orgs)
2. SKU management (CRUD, CSV import, reference upload)
3. Content scoring (CLIP + e5, nightly pipeline)
4. Stock distribution (plan/fact monitoring)
5. Price monitoring (snapshots, anomaly detection)
6. Excel reports (Content + Stock templates)
7. Alerts (rules engine + email dispatch)

## ALL Feature Set (priority 1-5)

Adds:
8. Reviews + sentiment (ruBERT pipeline)
9. Frontend dashboard (React + Ant Design)
10. Scraper platform coverage (110+ platforms)
11. ClickHouse analytics
12. Admin panel

## Loop Control

- After each feature: auto-commit `feat(<name>): <summary>`
- After every 3 features: run full test suite
- On test failure: fix before continuing
- On Critical review finding: fix before continuing
- On user interrupt (`Ctrl+C`): save checkpoint to `docs/plans/run-checkpoint.md`

## Checkpoint Format

```markdown
# /run checkpoint — 2026-03-21 14:30

## Completed
- [x] auth — JWT + RBAC + multi-tenant (commit: abc1234)
- [x] skus — CRUD + CSV import (commit: def5678)

## In Progress
- [ ] content-scoring — 40% done, stopped at ML pipeline

## Remaining
- [ ] stock-distribution
- [ ] price-monitoring
- [ ] excel-reports
- [ ] alerts
```

## Starting /run

1. Verify `/start` has been run (docs loaded, env healthy)
2. Load `.claude/feature-roadmap.json`
3. Filter features by scope (`mvp` or `all`)
4. Sort by priority, then by dependency order
5. Begin loop

## Example Output

```
🚀 /run mvp — 7 features queued

[1/7] auth — complexity: 6 → /feature auth
  Phase 1: SPARC planning... ✅
  Phase 2: Validation (5 agents)... ✅ score 82/100
  Phase 3: Implementation...
    ├── Alembic migration: users, orgs, refresh_tokens ✅
    ├── JWT encode/decode ✅
    ├── RBAC middleware ✅
    └── Integration tests (5 scenarios) ✅
  Phase 4: Review (5 agents)... ✅ 0 critical, 2 minor
  Commit: feat(auth): JWT auth with RBAC and multi-tenant orgs
  Push: ✅

[2/7] skus — complexity: 4 → /feature skus
  ...
```
