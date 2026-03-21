# /plan <task> — Quick Implementation Plan

## Usage
```
/plan add price alert webhook
/plan refactor CLIP embedding cache
/plan fix WB scraper timeout
```

## Process

1. Read relevant SPARC docs from `docs/` based on task context
2. Identify affected services and files
3. Generate step-by-step implementation plan
4. Save to `docs/plans/<task-slug>.md`
5. Commit: `docs: implementation plan for <task-slug>`

## Plan Format

```markdown
# Plan: <task name>
Date: YYYY-MM-DD

## Context
What problem this solves + relevant SPARC doc sections.

## Affected Files
- `services/api/app/<domain>/router.py` — add endpoint
- `services/api/app/<domain>/service.py` — business logic
- `infrastructure/postgres/migrations/` — schema change if any

## Steps
1. Write Alembic migration (if DB change)
2. Update SQLAlchemy model
3. Implement repository method (with org_id filter)
4. Implement service logic
5. Add FastAPI route
6. Write unit tests
7. Write integration test (cross-tenant isolation)

## Security Checklist
- [ ] org_id filter on all new queries
- [ ] RBAC role check on route
- [ ] Input validated via Pydantic
- [ ] No secrets in code

## Commit Sequence
feat(<scope>): <description>
test(<scope>): <description>
```

## Notes
- Plans are auto-committed at session end via Stop hook
- Reference plan in commits: `See docs/plans/<slug>.md`
- Archive completed plans — don't delete
