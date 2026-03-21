# Git Workflow — CAT

## Commit Format

```
type(scope): description
```

## Types

| Type | When to use |
|------|-------------|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `refactor` | Code restructuring without behavior change |
| `test` | Adding or updating tests |
| `docs` | Documentation changes |
| `chore` | Build, CI, config, dependency changes |
| `perf` | Performance improvements |

## Scopes (from monorepo services)

| Scope | Path |
|-------|------|
| `api` | `services/api/` |
| `collector` | `services/collector/` |
| `processor` | `services/processor/` |
| `frontend` | `services/frontend/` |
| `docker` | `docker-compose.yml`, `Dockerfile` |
| `infra` | `infrastructure/` |
| `docs` | `docs/` |
| `migrations` | `infrastructure/postgres/` |

## Examples

```
feat(api): add content score endpoint with pagination
fix(collector): retry logic for WB scraper timeout
refactor(processor): extract CLIP embedding cache to Redis
test(api): add BDD scenarios for distribution plan upload
docs: update architecture with ClickHouse schema
chore(docker): add healthcheck for collector service
perf(processor): batch CLIP embeddings to 32 per call
feat(frontend): content score dashboard with color coding
fix(api): missing org_id filter in stock distribution query
migrations: add distribution_plans table
```

## Rules

1. Commit after each logical unit of work — not at end of day
2. Never combine unrelated changes in one commit
3. Write imperative mood: "add", "fix", "update" (not "added", "fixes")
4. Keep description under 72 characters
5. Reference issue/ticket in body if applicable: `Closes #42`
6. Never commit: `.env`, secrets, model weights, `__pycache__`, `node_modules`

## Branch Strategy

```
main          ← stable, always deployable
develop       ← integration branch (optional)
feature/*     ← feature branches (short-lived)
fix/*         ← bug fix branches
claude/*      ← AI-assisted implementation branches
```

## Pre-commit Checklist

Before every commit:
- [ ] No secrets or API keys in staged files
- [ ] `org_id` filter present in all new DB queries
- [ ] Pydantic validation on all new request bodies
- [ ] No `print()` statements in Python (use `logging`)
- [ ] No `console.log()` in production React code
