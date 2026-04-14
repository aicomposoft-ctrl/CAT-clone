# CAT Development Guide

## Quick Start

```bash
# 1. Clone and configure
git clone <repo-url> cat-clone && cd cat-clone
cp .env.example .env
# Edit .env — fill in all required secrets

# 2. Start all services
docker compose up --build -d

# 3. Run DB migrations
docker compose exec api alembic upgrade head

# 4. Verify
docker compose ps
curl http://localhost:8000/health
```

**Local endpoints:**
| Service | URL |
|---------|-----|
| API docs | http://localhost:8000/docs |
| Frontend | http://localhost:3000 |
| Flower (Celery monitor) | http://localhost:5555 |
| MinIO console | http://localhost:9001 |
| MailHog | http://localhost:8025 |

---

## Project Structure

```
cat-clone/
├── services/
│   ├── api/                    # FastAPI backend
│   │   ├── app/
│   │   │   ├── main.py         # App entry, startup validation
│   │   │   ├── core/           # Config, DB, deps, security
│   │   │   ├── auth/           # Authentication + RBAC
│   │   │   ├── content/        # Content scoring domain
│   │   │   ├── stock/          # Stock distribution domain
│   │   │   ├── prices/         # Price monitoring domain
│   │   │   ├── reviews/        # Reviews + sentiment domain
│   │   │   ├── reports/        # Excel export domain
│   │   │   └── alerts/         # Alert rules + dispatch domain
│   │   ├── tests/
│   │   │   ├── unit/
│   │   │   ├── integration/
│   │   │   └── e2e/
│   │   └── Dockerfile
│   ├── collector/              # Celery workers + scrapers
│   │   ├── tasks/              # Celery task definitions
│   │   ├── scrapers/           # Platform-specific scrapers
│   │   │   ├── base.py         # BaseScraper with rate limiting
│   │   │   ├── wildberries.py
│   │   │   ├── ozon.py
│   │   │   └── ...             # 110+ platform scrapers
│   │   └── Dockerfile
│   ├── processor/              # ML pipeline
│   │   ├── clip_scorer.py      # CLIP image scoring
│   │   ├── text_scorer.py      # multilingual-e5 text scoring
│   │   ├── sentiment.py        # ruBERT sentiment analysis
│   │   └── Dockerfile
│   └── frontend/               # React + TypeScript
│       ├── src/
│       │   ├── pages/          # One dir per feature page
│       │   ├── components/     # Shared components
│       │   ├── api/            # Typed API client
│       │   ├── hooks/          # Global hooks
│       │   └── types/          # TypeScript types
│       └── Dockerfile
├── infrastructure/
│   ├── nginx/                  # Reverse proxy config + SSL
│   ├── postgres/               # Alembic migrations
│   └── clickhouse/             # ClickHouse schema + migrations
├── docs/                       # SPARC documentation
├── .claude/                    # Claude Code toolkit
│   ├── agents/                 # @planner, @code-reviewer, @architect
│   ├── commands/               # /feature, /plan, /deploy, etc.
│   ├── rules/                  # Security, coding style, testing rules
│   └── skills/                 # sparc-prd-mini, brutal-honesty-review, etc.
├── docker-compose.yml
├── .env.example
├── CLAUDE.md
└── DEVELOPMENT_GUIDE.md        # This file
```

---

## Development Workflow

### Adding a New Feature

```bash
/feature <feature-name>
```

This runs the 4-phase lifecycle: Plan → Validate → Implement → Review.

For quick tasks:
```bash
/plan <task description>   # generates implementation plan
```

### Running Tests

```bash
# All tests
docker compose exec api pytest

# With coverage
docker compose exec api pytest --cov=app --cov-report=term-missing

# Specific module
docker compose exec api pytest tests/unit/test_content_scorer.py -v

# Frontend tests
docker compose exec frontend npm test
```

### Database Migrations

```bash
# Create new migration
docker compose exec api alembic revision --autogenerate -m "add_price_alerts_table"

# Apply migrations
docker compose exec api alembic upgrade head

# Rollback one step
docker compose exec api alembic downgrade -1

# Check current revision
docker compose exec api alembic current
```

### Working with Scrapers

```bash
# Test a scraper manually (dry run)
docker compose exec collector python -m scrapers.wildberries --sku-id 12345 --dry-run

# Monitor Celery tasks
open http://localhost:5555

# Force scraping job
docker compose exec beat celery -A tasks call collect_sku_data --args='["<sku-id>"]'
```

---

## Architecture Decisions

### Multi-Tenancy

Every DB query MUST be scoped to `org_id`. No exceptions.

```python
# CORRECT
skus = await db.execute(select(SKU).where(SKU.org_id == user.org_id))

# WRONG — security bug
skus = await db.execute(select(SKU))
```

PostgreSQL RLS is the last line of defense. Application-level filtering is mandatory.

### Service Layer Pattern

```
Router (HTTP) → Service (business logic) → Repository (DB queries)
```

- Routers are thin — parse request, call service, return response
- Services contain business rules — no HTTP, no raw DB sessions
- Repositories own all DB queries — always filtered by `org_id`

### Content Scoring Formula

```
content_total = 0.40 × image_clip_cosine_sim
              + 0.35 × desc_e5_cosine_sim
              + 0.25 × comp_e5_cosine_sim
```

Do not change weights without explicit PRD approval.

---

## Environment Variables

All required secrets are in `.env.example`. Copy and fill before starting.

| Variable | Description |
|----------|-------------|
| `JWT_SECRET` | JWT signing secret (32 hex chars minimum) |
| `POSTGRES_URL` | PostgreSQL connection string |
| `CLICKHOUSE_URL` | ClickHouse connection string |
| `REDIS_URL` | Redis connection string |
| `MINIO_ACCESS_KEY` | MinIO/S3 access key |
| `MINIO_SECRET_KEY` | MinIO/S3 secret key |
| `MINIO_ENDPOINT` | MinIO endpoint (e.g. `minio:9000`) |
| `SMTP_HOST` | SMTP server host |
| `SMTP_PORT` | SMTP server port |
| `SMTP_USER` | SMTP username |
| `SMTP_PASSWORD` | SMTP password |
| `SMTP_FROM_EMAIL` | From address for alert emails |
| `PROXY_USER` | Scraper proxy username |
| `PROXY_PASS` | Scraper proxy password |

Generate JWT secret:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## Common Issues

| Problem | Fix |
|---------|-----|
| API fails to start | Check `.env` — all `REQUIRED_SECRETS` present? |
| `alembic upgrade` fails | Is Postgres running? Check `docker compose logs postgres` |
| Celery workers idle | Check Redis connection in `REDIS_URL` |
| CLIP model download on restart | Pre-download to Docker volume (see gotchas in `CLAUDE.md`) |
| Playwright scraper crashes | Ensure `--ipc=host` flag in collector service |
| Beat scheduling duplicates | Check only 1 replica of `beat` service is running |
| MinIO bucket not found | Run bucket initialization script on first startup |

---

## Code Quality Standards

See full rules in `.claude/rules/`:
- `coding-style.md` — Python/FastAPI and TypeScript/React conventions
- `security.md` — Multi-tenant isolation, JWT, RBAC, rate limiting
- `testing.md` — Test organization, coverage targets, fixture patterns
- `git-workflow.md` — Commit format, branch strategy

### Pre-commit Checklist

Before every commit:
- [ ] No secrets or API keys in staged files
- [ ] `org_id` filter present in all new DB queries
- [ ] Pydantic validation on all new request bodies
- [ ] No `print()` in Python (use `logging`)
- [ ] No `console.log()` in production React code
- [ ] Tests pass: `docker compose exec api pytest`

---

## Resources

- SPARC Docs: `docs/PRD.md`, `docs/Architecture.md`, `docs/Specification.md`
- BDD Scenarios: `docs/test-scenarios.md`
- Validation Report: `docs/validation-report.md`
- DB Schema: `docs/Architecture.md` (Section 5)
- ML Pipeline: `docs/Architecture.md` (Section 6)
- Scraper Design: `docs/Architecture.md` (Section 7)
- Claude Code Toolkit: `.claude/` directory
