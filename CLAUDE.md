# Project: Commerce Analytics Tool (CAT)

## Overview

CAT — SaaS-платформа мониторинга онлайн-полки для FMCG-производителей и digital commerce агентств. Ежедневно собирает данные о карточках товаров, ценах, остатках и отзывах на 110+ цифровых платформах (маркетплейсы, дарксторы, интернет-магазины), сравнивает с эталонными стандартами и генерирует Excel-отчёты + алёрты.

**Ключевое:** Ориентирован на **производителей/бренды** (не продавцов). ML-оценка контента (CLIP + ruBERT), мониторинг дистрибуции план/факт, Excel-отчёты в формате клиента.

## Problem & Solution

FMCG-бренды не контролируют, что происходит с их товарами на 110+ платформах ежедневно: контент деградирует, дистрибуция непрозрачна, конкуренты непредсказуемы, отзывы без систематики. Ручной мониторинг нескалируем: 100+ ч/нед на 1000 SKU × 10 платформ.

CAT автоматизирует сбор через Playwright/Scrapy + Celery, оценивает контент через CLIP/ruBERT embeddings, выявляет аномалии и отправляет алёрты в течение 2-4 часов.

## Architecture

**Distributed Monolith (Monorepo) on Docker Compose / VPS**

```
cat-clone/
├── services/
│   ├── api/          # FastAPI backend (auth, content, stock, reviews, prices, reports, alerts)
│   ├── collector/    # Celery workers + Playwright/Scrapy scrapers (110+ platforms)
│   ├── processor/    # ML pipeline (CLIP image scoring + ruBERT sentiment)
│   └── frontend/     # React + TypeScript + Ant Design dashboard
├── infrastructure/
│   ├── nginx/        # Reverse proxy + SSL
│   ├── postgres/     # Alembic migrations
│   ├── clickhouse/   # Time-series schema
│   └── redis/        # Config
└── docs/             # SPARC documentation
```

**Docker services:** nginx, api, collector, processor, beat, flower, frontend, postgres, clickhouse, redis, minio, mailhog

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend API | FastAPI + Python 3.11 |
| Task Queue | Celery 5.x + Redis |
| Scraping | Playwright (JS-heavy) + Scrapy (high-volume) |
| Primary DB | PostgreSQL 16 + Alembic |
| Analytics DB | ClickHouse (time-series) |
| Cache/Queue | Redis 7.x |
| Image Storage | MinIO (S3-compatible) |
| ML Images | CLIP via HuggingFace |
| ML Text/NLP | multilingual-e5 + rubert-base-cased-sentiment |
| Excel Gen | openpyxl 3.x |
| Frontend | React 18 + TypeScript + Ant Design 5 + ECharts |
| Auth | python-jose + passlib (JWT + RBAC) |
| Proxy | Nginx + SSL termination |

## Key Algorithms

```python
# Content scoring
content_total = 0.40 × image_clip_cosine_sim + 0.35 × desc_e5_cosine_sim + 0.25 × comp_e5_cosine_sim

# Reference embeddings cached at upload time (S3 URLs → embedding vectors in Redis)
# Collected embeddings computed nightly during scraping cycle

# Sentiment pipeline: rubert-base-cased-sentiment, batch=32
# Output: {positive, negative, neutral} + score → aggregate by brand/category/platform
```

## Security Rules

- **Multi-tenant isolation:** Every DB query MUST be filtered by `org_id`. PostgreSQL RLS policies enforce this.
- **JWT:** Access token 15 min / Refresh token 7 days. No fallback defaults for JWT_SECRET.
- **RBAC:** admin (full) | manager (CRUD + export) | viewer (read-only)
- **Secrets:** All secrets validated at startup — missing = `sys.exit(1)`. Never in code.
- **S3:** Reference images stored with private access only. No public URLs.
- **Rate limiting:** Auth endpoints limited to 10 req/min per IP.
- **Scraping APIs:** External platforms — use proxy rotation, rate limits from `BaseScraper.rate_limit`.
- **See:** `.claude/rules/security.md` and `.claude/rules/secrets-management.md`

## Parallel Execution Strategy

Always use parallel Task calls when implementing independent work:

```
# Example: implementing scraper + scoring pipeline simultaneously
Task("Implement WB scraper", ...) || Task("Implement content scorer", ...)
Task("Write API endpoints", ...) || Task("Write DB migrations", ...)
```

- Read all relevant SPARC docs FIRST before coding (anti-hallucination)
- Each Task reads its assigned docs independently
- Merge results after parallel Tasks complete

## Swarm Agents

Available for complex tasks:
- `/feature` — runs 5 parallel validation agents (Phase 2) + 5 review agents (Phase 4)
- `/go` — smart pipeline selection (complexity scoring)
- Use `@architect` for cross-service decisions
- Use `@planner` for implementation sequencing

## Git Workflow

```
feat(api): add content score endpoint
fix(collector): retry logic for WB scraper timeout
refactor(processor): extract CLIP embedding cache
test(api): add BDD scenarios for distribution plan upload
docs: update architecture with ClickHouse schema
chore(docker): add healthcheck for collector service
```

Commit after each logical unit. See `.claude/rules/git-workflow.md`.

## Available Agents

| Agent | Trigger | Purpose |
|-------|---------|---------|
| `@planner` | "plan", "sequence", "how to implement" | Implementation planning from SPARC docs |
| `@code-reviewer` | "review", "check code", "проверь" | Multi-criteria code review |
| `@architect` | "architecture", "design", "cross-service" | System design decisions |

## Available Skills

| Skill | Purpose |
|-------|---------|
| `sparc-prd-mini` | Feature planning (9 SPARC documents) |
| `explore` | Task clarification (Socratic questioning) |
| `goap-research-ed25519` | Verified research with anti-hallucination |
| `problem-solver-enhanced` | TRIZ + first principles for complex problems |
| `requirements-validator` | INVEST/SMART + BDD scenario generation |
| `brutal-honesty-review` | Unvarnished technical review |
| `project-context` | Deep project domain knowledge |
| `coding-standards` | Python/FastAPI/React coding conventions |
| `testing-patterns` | Test patterns from BDD scenarios |
| `feature-navigator` | Sprint roadmap navigation |
| `security-patterns` | API key, S3, JWT security patterns |

## Quick Commands

| Command | Purpose |
|---------|---------|
| `/start` | Full project bootstrap (read docs → scaffold → docker up) |
| `/feature <name>` | 4-phase feature lifecycle (plan → validate → implement → review) |
| `/next` | Show sprint progress + next 3 actions |
| `/plan <task>` | Quick implementation plan (saved to docs/plans/) |
| `/test [scope]` | Run tests with coverage |
| `/deploy [env]` | Deploy checklist + docker compose |
| `/go [feature]` | Autonomous feature implementation |
| `/run [mvp|all]` | Full autonomous development loop |
| `/docs [rus|eng]` | Generate bilingual documentation |
| `/myinsights` | Capture/browse knowledge base |
| `/review` | Code quality review (brutal-honesty) |

## Development Insights

Knowledge base: `myinsights/` (auto-managed via `/myinsights`)

Before debugging any issue: `grep -r "KEYWORD" myinsights/` first.

Key insights captured so far: _none yet — start building your knowledge base with `/myinsights`_

## Toolkit Artifacts

Extracted via `/harvest` — reusable artifacts from this project.

### Patterns
| Pattern | Maturity | Description | Source |
|---------|----------|-------------|--------|
| multi-tenant-saas-isolation | 🔴 Alpha | org_id filtering + RLS for SaaS DB isolation | CAT, 2026-03-27 |
| fastapi-domain-driven-layering | 🔴 Alpha | Router/Service/Repository separation for FastAPI | CAT, 2026-03-27 |
| cache-aside-expensive-computations | 🔴 Alpha | Redis cache-aside for ML inference and slow ops | CAT, 2026-03-27 |

### Snippets
| Snippet | Maturity | Description | Source |
|---------|----------|-------------|--------|
| startup-secrets-validation.py | 🔴 Alpha | Fail-fast env var validation at app startup | CAT, 2026-03-27 |
| async-retry-exponential-backoff.py | 🔴 Alpha | Async decorator for retry with exponential backoff | CAT, 2026-03-27 |
| excel-bytesio-streaming.py | 🔴 Alpha | Excel report generation without disk I/O | CAT, 2026-03-27 |
| pytest-async-db-rollback-fixture.py | 🔴 Alpha | Per-test DB rollback fixture for async SQLAlchemy | CAT, 2026-03-27 |
| sliding-window-rate-limiter-redis.py | 🔴 Alpha | Distributed rate limiter using Redis sorted sets | CAT, 2026-03-27 |

### Templates
| Template | Maturity | Description | Source |
|----------|----------|-------------|--------|
| python-node-docker.gitignore | 🔴 Alpha | Comprehensive .gitignore for Python+Node+Docker+ML | CAT, 2026-03-27 |

Last harvest: 2026-03-27 | Total artifacts: 9 | Report: `docs/harvest-report-2026-03-27.md`

## Feature Development Lifecycle

```
/feature <name>
  Phase 0: Pre-flight (verify skills exist)
  Phase 1: PLAN   → sparc-prd-mini → 9 SPARC docs in docs/features/<name>/sparc/
  Phase 2: VALIDATE → requirements-validator swarm (5 agents) → score >= 70
  Phase 3: IMPLEMENT → read validated docs → parallel Tasks → modular code
  Phase 4: REVIEW  → brutal-honesty-review swarm (5 agents) → fix criticals
```

Rule: Never implement from memory. Always read SPARC docs first. See `.claude/rules/feature-lifecycle.md`.

## Feature Roadmap

Status tracked in `.claude/feature-roadmap.json`

Quick navigation:
- `/next` — sprint progress + top 3 next actions
- `/next <feature-id>` — mark done, cascade unblocking
- `/next update` — scan codebase, suggest status updates

SessionStart hook auto-injects current sprint context.

## Implementation Plans

Plans saved to `docs/plans/` via `/plan` command.
Auto-committed on session end via Stop hook.

## Automation Commands

```
/go <feature>    → complexity scoring → pick /plan | /feature → execute autonomously
/run             → /start → /next → /go loop (MVP features)
/run all         → implement ALL features until done
/docs            → generate 7-file bilingual documentation set
```

Command hierarchy: `/run` → `/start` → `/next` → `/go` → `/plan` | `/feature`

## Resources

- SPARC Docs: `docs/PRD.md`, `docs/Architecture.md`, `docs/Specification.md`, `docs/Pseudocode.md`
- Validation: `docs/validation-report.md`, `docs/test-scenarios.md`
- DB Schema: `docs/Architecture.md` (Section 5)
- ML Pipeline: `docs/Architecture.md` (Section 6)
- Scraper Design: `docs/Architecture.md` (Section 7)
- BDD Scenarios: `docs/test-scenarios.md`
