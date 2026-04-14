# /start Command Template

Use this template to generate the `/start` bootstrap command for any project.
Adapt all placeholders to the specific project's architecture, tech stack, and documentation.

---

```markdown
---
description: Bootstrap entire {{PROJECT_NAME}} project from documentation. Generates monorepo skeleton, all packages, Docker configs, {{IF_DATABASE: database schema,}} core modules, and basic tests. $ARGUMENTS: optional flags --skip-tests, --skip-seed, --dry-run.
---

# /start $ARGUMENTS

## Purpose

One-command project generation from documentation → working monorepo with `docker compose up`.

## Prerequisites

- Documentation in `docs/` directory (SPARC or idea2prd-manual output)
- CC toolkit in project root (CLAUDE.md, .claude/, .mcp.json)
- {{RUNTIME_PREREQUISITES}}
- Docker + Docker Compose installed
- Git initialized

## Process

### Phase 1: Foundation (sequential — everything depends on this)

1. **Read all project docs** to build full context:
{{DOCS_TO_READ}}

2. **Generate root configs:**
   - `package.json` {{ROOT_PACKAGE_DETAILS}}
   - `docker-compose.yml` (from Architecture)
   - `.env.example` (from Completion/deployment docs)
   - `.gitignore`
   - {{ADDITIONAL_ROOT_CONFIGS}}

3. **Git commit:** `chore: project root configuration`

### Phase 2: Packages (parallel via Task tool ⚡)

Launch {{NUM_TASKS}} parallel tasks:

{{FOR_EACH_PACKAGE}}
#### Task {{LETTER}}: {{PACKAGE_PATH}} ⚡

Read and use as source:
{{PACKAGE_DOC_REFERENCES}}

Generate:
{{PACKAGE_FILE_LIST}}

**Commits:** {{PACKAGE_COMMITS}}
{{/FOR_EACH_PACKAGE}}

### Phase 3: Integration (sequential)

1. **Verify cross-package imports** (shared modules used correctly)
2. **Docker build:** `docker compose build`
3. **Start services:** `docker compose up -d`
{{IF_DATABASE}}
4. **Database setup:**
   - `{{MIGRATION_COMMAND}}`
   - `{{SEED_COMMAND}}`
{{/IF_DATABASE}}
{{IF_NO_DATABASE}}
4. *No database migration needed for this project*
{{/IF_NO_DATABASE}}
5. **Health check:** `{{HEALTH_CHECK_COMMAND}}`
6. **Run tests:** {{TEST_COMMANDS}}
7. **Git commit:** `chore: verify docker integration`

### Phase 4: Finalize

1. Generate/update `README.md` with quick start instructions
2. Final git tag: `git tag v0.1.0-scaffold`
3. Report summary: files generated, services running, what needs manual attention

## Output

After /start completes:
```
{{PROJECT_STRUCTURE_AFTER_INIT}}
```

## Flags

- `--skip-tests` — skip test file generation (faster, not recommended)
{{IF_DATABASE}}
- `--skip-seed` — skip database seeding
{{/IF_DATABASE}}
- `--dry-run` — show plan without executing

## Estimated Time

- With parallel tasks: {{ESTIMATED_TIME}}
- Files generated: {{ESTIMATED_FILES}}
- Commits: {{ESTIMATED_COMMITS}}

## Error Recovery

If a task fails mid-generation:
- All completed phases are committed to git
- Re-run `/start` — it detects existing files and skips completed phases
- Or fix the issue manually and continue

## Swarm Agents Used

| Phase | Agents | Parallelism |
|-------|--------|-------------|
| Phase 1 | Main | Sequential |
| Phase 2 | {{NUM_TASKS}} Task tools | ⚡ Parallel |
| Phase 3 | Main | Sequential |
| Phase 4 | Main | Sequential |
```

---

## Fill Instructions

### DOCS_TO_READ

List ALL documentation files the /start should read.

**For SPARC pipeline:**
```markdown
   - `docs/Architecture.md` → monorepo structure, Docker Compose, tech stack
   - `docs/Specification.md` → data model, API endpoints, NFRs
   - `docs/Pseudocode.md` → core algorithms, business logic
   - `docs/Completion.md` → env config, deployment setup
   - `docs/PRD.md` → features, user personas (for README)
   - `docs/Refinement.md` → edge cases, testing strategy
```

**For idea2prd-manual docs, also include:**
```markdown
   - `docs/ddd/strategic/` → bounded contexts, context map
   - `docs/ddd/tactical/` → aggregates, entities, events
   - `docs/adr/` → technology decisions
   - `docs/tests/*.feature` → Gherkin test scenarios
```

### FOR_EACH_PACKAGE

Create one Task block per independent package/service from Architecture.
Each Task MUST include:
1. **Doc references** — which docs to read for this package
2. **File list** — all files to generate (source, configs, tests)
3. **Commits** — semantic commit messages per logical group

Mark tasks as ⚡ parallel when they have no cross-dependencies.
Tasks that depend on shared modules should note the dependency.

**For single-app monorepos (e.g. Next.js):**
Phase 2 may have only 1-2 tasks. This is normal — not all projects are multi-service.
Example: `⚡ Task A: apps/web` + `⚡ Task B: packages/shared`

**For multi-service monorepos:**
One task per service. Example: `⚡ Task A: packages/shared`, `⚡ Task B: packages/backend`, `⚡ Task C: packages/frontend`

### IF_DATABASE / IF_NO_DATABASE

Check Architecture.md for database presence:
- If PostgreSQL/MongoDB/MySQL/Redis mentioned → use `{{IF_DATABASE}}` block
- Set `{{MIGRATION_COMMAND}}` to correct ORM command:
  - Prisma: `npx prisma migrate dev --name init`
  - TypeORM: `npx typeorm migration:run`
  - Drizzle: `npx drizzle-kit push`
  - Knex: `npx knex migrate:latest`
  - Raw SQL: `psql -f init.sql`
- Set `{{SEED_COMMAND}}` similarly
- If NO database in Architecture → use `{{IF_NO_DATABASE}}` block, remove --skip-seed flag

### Key Principles

1. **Docs as source of truth** — every Task must reference specific docs, never generate from memory
2. **Maximize parallelism** — independent packages run as parallel Tasks
3. **Atomic commits** — one commit per logical change, not one giant commit
4. **Full integration** — Phase 3 MUST include Docker build + start + health check (+ DB if applicable)
5. **Error recovery** — git commits after each phase ensure progress is saved
6. **Project-specific** — adapt ALL placeholders to actual tech stack and architecture

### Adaptation Checklist

- [ ] All packages from Architecture have a Task in Phase 2
- [ ] All core algorithms from Pseudocode are assigned to correct packages
- [ ] Database section is conditional (included only if DB exists)
- [ ] Migration command matches actual ORM (Prisma/TypeORM/Drizzle/Knex/raw SQL)
- [ ] Docker services match docker-compose.yml from Architecture
- [ ] Health check endpoint matches actual API
- [ ] Test commands match actual test framework
- [ ] Env vars in .env.example match Completion/deployment docs
- [ ] Single-app monorepo handled correctly (fewer Phase 2 tasks)
- [ ] If DDD: bounded contexts map to packages/modules
- [ ] If Gherkin: test stubs generated from .feature files
- [ ] If external APIs: encrypted storage setup included

---

## Adaptation Rules

The `/start` content MUST be adapted to the specific project:

| Project Aspect | How /start Adapts |
|---------------|------------------|
| **Monorepo packages** | One Task per package in Phase 2 |
| **Single-app monorepo** | May have only 1-2 Tasks (e.g. Next.js + shared) |
| **Tech stack** | Correct build/start/test commands per framework |
| **Database present** | Include ORM migration commands (Prisma/TypeORM/Drizzle/etc.) |
| **No database** | Skip migration/seed in Phase 3, remove {{MIGRATION_COMMAND}} |
| **Docker services** | All services from docker-compose.yml |
| **External APIs** | Adapter/client generation + encrypted storage setup |
| **DDD Bounded Contexts** | One module/package per context if applicable |
| **Pseudocode algorithms** | Core logic files generated from pseudocode |
| **Gherkin scenarios** | Test file stubs generated from .feature files |
| **Security patterns** | Auth middleware, encryption utils if required |

---

## Example: What /start Generated for PredMarket

Real-world reference from a prediction market project (SPARC pipeline):

```
Phase 1 (Foundation):
  - docker-compose.yml (3 services: frontend, backend, postgres)
  - root package.json with workspaces
  - .env.example with all env vars
  - tsconfig.base.json

Phase 2 (3 parallel Tasks):
  ⚡ Task A: packages/shared
     - LMSR engine (core math from Pseudocode.md)
     - TypeScript types from data model
     - Unit tests with invariant checks
     
  ⚡ Task B: packages/backend  
     - Prisma schema from Specification.md data model
     - 13 API endpoints from Architecture.md
     - Service layer from Pseudocode.md algorithms
     - Oracle adapters from Pseudocode.md
     - Cron scheduler from Completion.md
     - Zod schemas for all endpoints
     
  ⚡ Task C: packages/frontend
     - React pages from user stories
     - Components from UI requirements
     - Hooks (auth, markets, trading, wallet)
     - API client, router setup

Phase 3 (Integration):
  - docker compose build
  - docker compose up -d
  - npx prisma migrate dev --name init
  - npx prisma db seed
  - curl localhost:3001/health → verify

Phase 4 (Finalize):
  - README.md with quick start
  - git tag v0.1.0-scaffold
  - Summary: 70+ files, 15 commits, all services running
```

---

## Critical: /start MUST Reference Docs, Not Hallucinate

The `/start` command instructions must tell Claude Code to **read the actual docs** in `docs/`
directory, not generate code from memory. Each Phase 2 Task should include explicit references:

```markdown
### Task B: packages/backend ⚡
Read and use as source:
- `docs/Specification.md` → data model → Prisma schema
- `docs/Architecture.md` → API endpoints → route files
- `docs/Pseudocode.md` → algorithms → service implementations
- `docs/Completion.md` → env config → config.ts
```

This ensures generated code matches the documentation, not Claude's assumptions.
