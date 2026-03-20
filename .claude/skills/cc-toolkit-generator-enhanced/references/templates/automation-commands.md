# Automation Commands Templates

Templates for generating orchestration and automation commands:
- `/go` — intelligent pipeline selector (delegates to /plan, /feature, or /feature-ent)
- `/run` — autonomous MVP/full build loop
- `/docs` — bilingual documentation generator (RU/EN)

---

## 1. Command Template: `/go`

Generate as `.claude/commands/go.md`:

````markdown
---
description: Intelligent feature implementation pipeline. Analyzes complexity and selects
  optimal approach (/plan, /feature, or /feature-ent if available), then executes autonomously
  with parallel agents and frequent commits. Falls back to /feature for complex tasks
  when /feature-ent is not available in this project.
  $ARGUMENTS: feature name, ID, or brief description (optional — defaults to next from roadmap)
---

# /go $ARGUMENTS

## Purpose

One-command feature implementation that automatically selects the right pipeline
based on feature complexity, then executes it without manual confirmations.

> **PROCESS COMPLIANCE — BLOCKING RULES:**
> - MUST use /plan, /feature, or /feature-ent commands — NEVER launch raw Agent tools directly
> - MUST follow the skill chain: /next -> /go -> /plan|/feature|/feature-ent
> - FORBIDDEN: Bypassing the skill chain by spawning parallel agents without commands
> - FORBIDDEN: Batching multiple features into a single commit wave
> - CRITICAL: Each feature MUST get its own plan, validation, and commit sequence

## Step 1: Determine Target Feature

IF $ARGUMENTS is provided:
  - Parse as feature name, roadmap ID, or description
  - Look up in `.claude/feature-roadmap.json` if it matches an ID
ELSE:
  - Run `/next` logic to find the highest-priority `next` feature
  - If no `next` feature found, pick first `planned` feature
  - Confirm selection before proceeding

## Step 2: Analyze Complexity

First, check which pipelines are available:

```
Available pipelines:
✅ /plan              — always available
✅ /feature           — always available
⚠️ /feature-ent       — ONLY if .claude/commands/feature-ent.md exists
                        (generated only when project has DDD docs from idea2prd-manual pipeline)

CHECK: ls .claude/commands/feature-ent.md 2>/dev/null
  → exists: feature_ent_available = true
  → missing: feature_ent_available = false
```

Then evaluate the feature to determine the right pipeline:

| Signal | Score |
|--------|-------|
| Touches ≤3 files | -2 (simple) |
| Touches 4-10 files | 0 (medium) |
| Touches >10 files | +3 (complex) |
| Has external API integration | +2 |
| Requires new database entities | +2 |
| Has cross-bounded-context dependencies | +3 |
| Is a hotfix or minor improvement | -3 |
| Has DDD docs in project (`docs/ddd/`) | +1 (toward /feature-ent) |
| Has Gherkin scenarios for this feature | +1 |
| Estimated implementation < 30 min | -2 |
| Estimated implementation > 2 hours | +3 |

**Decision matrix:**

| Total Score | Pipeline | Rationale |
|-------------|----------|-----------|
| ≤ -2 | `/plan` | Simple task, lightweight plan is enough |
| -1 to +4 | `/feature` | Standard feature, needs SPARC lifecycle |
| ≥ +5 AND feature_ent_available | `/feature-ent` | Complex enterprise feature, full DDD/ADR/C4 lifecycle |
| ≥ +5 AND NOT feature_ent_available | `/feature` | Complex feature but /feature-ent not in this project (no DDD docs); use /feature with extra attention to architecture |

> **Note:** `/feature-ent` is only available in projects where the toolkit was generated
> from idea2prd-manual pipeline with DDD documentation. If `/feature-ent` is not available
> and the feature is complex (score ≥ +5), `/feature` is used with a recommendation to
> pay extra attention to architectural consistency and consider creating ADRs manually.

## Step 3: Execute Selected Pipeline

### If `/plan` selected:
1. Run `/plan <feature-name>`
2. After plan is saved, immediately implement it
3. Use `Task` tool to parallelize independent changes
4. Run tests after implementation
5. Commit and push: `git push origin HEAD`

### If `/feature` selected:
1. Run `/feature <feature-name>` in AUTO mode (no confirmations between phases)
   - Phase 1: PLAN (sparc-prd-mini → docs)
   - Phase 2: VALIDATE (requirements-validator → score ≥70)
   - Phase 3: IMPLEMENT (parallel agents from docs)
   - Phase 4: REVIEW (brutal-honesty-review → fix criticals)
2. Where possible, spawn concurrent tasks:
   - Parallel test writing + implementation
   - Parallel frontend + backend if independent
   - Use swarm of agents for large implementations
3. Commit frequently (after each logical change)
4. Push after each phase: `git push origin HEAD`

### If `/feature-ent` selected (only when feature_ent_available = true):
1. Run `/feature-ent <feature-name>` in AUTO mode
   - Includes DDD analysis, ADR creation, C4 updates
   - Phase 1: PLAN (idea2prd-manual → DDD/ADR/C4/Gherkin)
   - Phase 2: VALIDATE (7 agents, including DDD coherence + ADR consistency)
   - Phase 3: IMPLEMENT (parallel agents per Bounded Context)
   - Phase 4: REVIEW (6 agents, ADR + fitness verification)
2. Same parallelization and commit strategy as `/feature`
3. Push after each phase: `git push origin HEAD`

### If complex feature but `/feature-ent` NOT available:
1. Run `/feature <feature-name>` in AUTO mode (same as standard /feature above)
2. Additionally after Phase 1 (PLAN):
   - Recommend creating manual ADRs in `docs/features/<feature-name>/adr/`
   - Flag architectural concerns for extra review
3. Log warning:
```
⚠️ Complex feature (score: <N>) but /feature-ent not available in this project.
   Using /feature with enhanced attention to architecture.
   Consider: re-generate toolkit with idea2prd-manual for enterprise features.
```

## Step 4: Post-Implementation

1. Update `.claude/feature-roadmap.json`:
   - Set feature status to `done`
   - Update `files` array with actual files touched
2. Commit roadmap update: `git add .claude/feature-roadmap.json && git commit -m "docs(roadmap): mark <feature> as done"`
3. Push: `git push origin HEAD`
4. Report summary:
```
✅ Feature completed: <feature-name>
   Pipeline used: /plan | /feature | /feature-ent | /feature (complex fallback)
   Complexity score: <N>
   Files changed: <count>
   Commits: <count>
   Tests: <passed>/<total>
   Duration: <time>
   
   IF complex fallback was used:
   ⚠️ Note: /feature-ent was not available. Consider re-generating toolkit
      with idea2prd-manual pipeline for enterprise-grade planning.
   
   Next suggested: /next or /go for the next feature
```

## Parallelization Strategy

- Use `Task` tool for independent subtasks within implementation
- Spawn concurrent agents when feature touches multiple packages/services
- Run tests in parallel with implementation of unrelated components
- Never parallelize tasks that have data dependencies

## Git Strategy

- Commit after each logical unit of work (not giant commits)
- Format: `type(scope): description`
- Push to remote after each completed phase to prevent data loss
- If working on a branch: `git push origin HEAD`
````

---

## 2. Command Template: `/run`

Generate as `.claude/commands/run.md`:

````markdown
---
description: Autonomous project build loop. Bootstraps project and implements features
  one by one until MVP (default) or all features are done.
  $ARGUMENTS: "mvp" (default) | "all" — scope of features to implement
---

# /run $ARGUMENTS

## Purpose

End-to-end autonomous project build: bootstrap → implement features in loop → done.
Combines `/start`, `/next`, and `/go` into a single continuous pipeline.

> **AUTONOMOUS EXECUTION — BLOCKING RULES:**
> - MUST execute features ONE AT A TIME through the full /go pipeline
> - MUST create 1 plan per feature, 1 validation per feature, 1 commit per feature
> - NEVER batch features into parallel waves without individual plans
> - NEVER skip the /next -> /go pipeline by launching raw implementation agents
> - CRITICAL: If a feature fails 3 times, skip it and log — NEVER retry indefinitely
> - MUST push state after each feature completion (independent commits)

## Step 0: Parse Scope

```
IF $ARGUMENTS is empty OR $ARGUMENTS == "mvp":
    scope = "mvp"
    → Implement only features with status `next` or `in_progress`
    → Stop when no more `next` features remain (skip `planned`)
    
IF $ARGUMENTS == "all":
    scope = "all"
    → Implement ALL features regardless of status
    → Stop only when every feature is `done`
```

## Step 1: Bootstrap Project

1. Check if project is already bootstrapped:
   - IF `docker-compose.yml` exists AND key source dirs exist → skip to Step 2
   - ELSE → run `/start`
2. Verify bootstrap succeeded:
   - Project structure exists
   - Docker services running (if applicable)
   - Basic health checks pass
3. Commit and push: `git push origin HEAD`

## Step 2: Feature Implementation Loop

```
LOOP:
    1. Run `/next` to get current sprint status and next feature
    
    2. IF scope == "mvp":
         - Get next feature with status `next` or `in_progress`
         - IF no such feature exists → EXIT LOOP (MVP complete)
       IF scope == "all":
         - Get next feature that is NOT `done`
         - IF all features are `done` → EXIT LOOP (all complete)
    
    3. Run `/go <feature-name>` to implement the feature
       - /go automatically selects /plan, /feature, or /feature-ent
       - /go handles commits and pushes
    
    4. Verify implementation:
       - Run project tests: ensure no regressions
       - IF tests fail → fix before continuing
    
    5. Update progress:
       - Feature marked as `done` in roadmap (handled by /go)
       - Log progress to stdout
    
    6. CONTINUE LOOP
```

## Step 3: Finalize

After loop completes:

1. Run full test suite: `npm test` or equivalent
2. Update README.md with current state
3. Final commit: `git add -A && git commit -m "milestone: <scope> complete"`
4. Push and tag:
   ```bash
   git push origin HEAD
   IF scope == "mvp":
       git tag v0.1.0-mvp && git push origin v0.1.0-mvp
   IF scope == "all":
       git tag v1.0.0 && git push origin v1.0.0
   ```
5. Generate summary report:

```
🏁 /run <scope> — COMPLETE

📊 Summary:
   Features implemented: <count>/<total>
   Total commits: <count>
   Total files: <count>
   Test results: <passed>/<total>
   Duration: <time>

📋 Features completed:
   ✅ <feature-1>  (via /plan)
   ✅ <feature-2>  (via /feature)
   ✅ <feature-3>  (via /feature-ent)
   ...

🏷️ Tagged: v0.1.0-mvp | v1.0.0

IF scope == "mvp" AND planned features remain:
   ⏭️ Remaining planned features: <count>
   To continue: /run all
```

## Error Recovery

- Each feature is committed independently → partial progress is saved
- If a feature fails repeatedly (3 attempts), skip it and mark as `blocked`
- If `/start` fails, stop and report — project bootstrap is critical
- On any failure: always push current state to remote first

## Parallelization

- `/go` handles per-feature parallelization internally
- Features are implemented sequentially (one at a time) to avoid conflicts
- Within each feature, /go maximizes internal parallelism
````

---

## 3. Command Template: `/docs`

Generate as `.claude/commands/docs.md`:

````markdown
---
description: Generate or update project documentation in Russian and English.
  Creates a comprehensive set of markdown files covering deployment, usage,
  architecture, and user flows.
  $ARGUMENTS: optional flags — "rus" (Russian only), "eng" (English only), "update" (refresh existing)
---

# /docs $ARGUMENTS

## Purpose

Generate professional, bilingual project documentation from source code,
existing docs, and development insights. Output: `/README/rus/` and `/README/eng/`.

## Step 1: Gather Context

Read all available sources to build comprehensive understanding:

### Primary sources (project documentation):
```
docs/PRD.md (or docs/*.md)          — product requirements, features
docs/Architecture.md                 — system architecture, tech stack
docs/Specification.md                — API, data model, user stories
docs/Completion.md                   — deployment, environment setup
docs/features/                       — feature-specific documentation
docs/plans/                          — implementation plans
CLAUDE.md                            — project overview, commands, agents
DEVELOPMENT_GUIDE.md                 — development workflow
INSTALL.md                           — installation instructions
docker-compose.yml                   — infrastructure services
.env.example                         — environment variables
```

### Secondary sources (knowledge base):
```
myinsights/1nsights.md               — development insights index
myinsights/details/                   — detailed insight files
.claude/feature-roadmap.json          — feature list and statuses
```

### Tertiary sources (code analysis):
```
Source code structure                 — actual implementation
package.json / Cargo.toml / etc.     — dependencies, scripts
README.md (existing, if any)         — current documentation
```

## Step 2: Determine Scope

```
IF $ARGUMENTS contains "rus":  languages = ["rus"]
ELIF $ARGUMENTS contains "eng": languages = ["eng"]
ELSE: languages = ["rus", "eng"]

IF $ARGUMENTS contains "update":
    mode = "update"  — read existing /README/ files, update only changed sections
ELSE:
    mode = "create"  — generate from scratch
```

## Step 3: Generate Documentation Set

For EACH language in languages, generate these files:

### File 1: `deployment.md` — Как развернуть систему / Deployment Guide

```markdown
# Развертывание системы / Deployment Guide

## Требования к окружению
- OS, runtime versions, Docker version
- Minimum hardware requirements

## Быстрый старт (Quick Start)
- Clone → configure → run (step by step)
- Docker-based deployment
- Environment variables explanation

## Полное развертывание (Production Deployment)
- Infrastructure provisioning
- SSL/TLS configuration
- Database initialization
- Service startup order
- Health checks verification

## Обновление (Updating)
- How to update to a new version
- Database migration steps
- Rollback procedure
```

### File 2: `admin-guide.md` — Руководство администратора / Admin Guide

```markdown
# Руководство администратора / Administrator Guide

## Управление пользователями
- User creation, roles, permissions

## Конфигурация системы
- Configuration files and their purposes
- Feature flags / toggles
- Performance tuning

## Мониторинг и логирование
- How to check system health
- Log locations and format
- Alerting setup

## Резервное копирование
- Backup procedures
- Restore procedures

## Устранение неполадок
- Common issues and solutions
- Diagnostic commands
```

### File 3: `user-guide.md` — Руководство пользователя / User Guide

```markdown
# Руководство пользователя / User Guide

## Начало работы
- First login / registration
- Initial setup

## Основные функции
- Feature-by-feature walkthrough
- Screenshots / descriptions of key screens

## Типичные сценарии использования
- Common workflows step by step

## FAQ
- Frequently asked questions
```

### File 4: `infrastructure.md` — Требования к инфраструктуре / Infrastructure Requirements

```markdown
# Требования к инфраструктуре / Infrastructure Requirements

## Минимальные требования
- CPU, RAM, Disk for each component
- Network requirements

## Рекомендуемые требования
- Production-grade specifications
- High-availability setup

## Сетевые требования
- Ports to open
- Internal service communication
- External API access requirements

## Зависимости
- Required external services
- Third-party integrations
- License requirements
```

### File 5: `architecture.md` — Архитектура системы / System Architecture

```markdown
# Архитектура и принципы работы / Architecture & Design Principles

## Обзор архитектуры
- High-level system diagram (Mermaid)
- Component responsibilities

## Технологический стек
- Languages, frameworks, databases
- Why each was chosen (from ADRs if available)

## Компоненты системы
- Service-by-service description
- Communication patterns (REST, events, queues)

## Модель данных
- Key entities and relationships
- Database schema overview

## Безопасность
- Authentication / authorization approach
- Data encryption
- API security

## Масштабируемость
- Horizontal scaling strategy
- Bottlenecks and mitigations
```

### File 6: `ui-guide.md` — Интерфейс системы / UI Guide

```markdown
# Интерфейс системы / UI Guide

## Структура интерфейса
- Main navigation layout
- Key screens and their purposes

## Основные экраны
- Dashboard / Home
- Feature-specific screens
- Settings / Admin panel

## Элементы управления
- Common UI patterns used
- Keyboard shortcuts (if any)
- Mobile / responsive behavior
```

### File 7: `user-flows.md` — Пользовательские сценарии / User & Admin Flows

```markdown
# Типовые сценарии / User & Admin Flows

## User Flow: Регистрация и первый вход
[Step-by-step with Mermaid sequence diagram]

## User Flow: Основной рабочий процесс
[Primary user journey — the main thing users do]

## User Flow: [Feature-specific flow]
[For each key feature]

## Admin Flow: Настройка системы
[Admin setup walkthrough]

## Admin Flow: Управление пользователями
[User management walkthrough]

## Admin Flow: Мониторинг
[Monitoring and maintenance walkthrough]
```

## Step 4: Generate Output

1. Create directory structure:
```bash
mkdir -p README/rus README/eng
```

2. Generate files for each language:
   - Russian files go to `README/rus/`
   - English files go to `README/eng/`
   - Use proper language throughout (not machine-translated fragments)

3. Generate `README/index.md` — table of contents linking both languages:
```markdown
# Project Documentation

## 🇷🇺 Документация на русском
- [Развертывание](rus/deployment.md)
- [Руководство администратора](rus/admin-guide.md)
- [Руководство пользователя](rus/user-guide.md)
- [Требования к инфраструктуре](rus/infrastructure.md)
- [Архитектура](rus/architecture.md)
- [Интерфейс](rus/ui-guide.md)
- [Пользовательские сценарии](rus/user-flows.md)

## 🇬🇧 English Documentation
- [Deployment Guide](eng/deployment.md)
- [Administrator Guide](eng/admin-guide.md)
- [User Guide](eng/user-guide.md)
- [Infrastructure Requirements](eng/infrastructure.md)
- [Architecture](eng/architecture.md)
- [UI Guide](eng/ui-guide.md)
- [User & Admin Flows](eng/user-flows.md)
```

## Step 5: Commit and Report

```bash
git add README/
git commit -m "docs: generate project documentation (RU/EN)"
git push origin HEAD
```

Report:
```
📚 Documentation generated: README/

🇷🇺 Russian (README/rus/):
   ✅ deployment.md — развертывание
   ✅ admin-guide.md — руководство администратора
   ✅ user-guide.md — руководство пользователя
   ✅ infrastructure.md — требования к инфраструктуре
   ✅ architecture.md — архитектура
   ✅ ui-guide.md — интерфейс
   ✅ user-flows.md — пользовательские сценарии

🇬🇧 English (README/eng/):
   ✅ deployment.md — deployment guide
   ✅ admin-guide.md — admin guide
   ✅ user-guide.md — user guide
   ✅ infrastructure.md — infrastructure requirements
   ✅ architecture.md — architecture
   ✅ ui-guide.md — UI guide
   ✅ user-flows.md — user & admin flows

📄 README/index.md — documentation index
```

## Update Mode

When `$ARGUMENTS` contains "update":
1. Read existing files in `README/rus/` and `README/eng/`
2. Compare with current project state
3. Update only sections that have changed
4. Preserve any manual additions (sections not in template)
5. Commit: `git commit -m "docs: update project documentation"`

## Notes

- Documentation is generated from ACTUAL project state, not assumptions
- Mermaid diagrams are used for architecture and flow visualizations
- If UI doesn't exist yet, ui-guide.md notes this and describes planned UI
- If some information is unavailable, the section notes what's missing
- myinsights/ is checked for gotchas and important notes to include
````

---

## 4. Integration Points

### CLAUDE.md Addition

Add this section to CLAUDE.md generation:

```markdown
## 🚀 Automation Commands
- `/go [feature]` — auto-select pipeline (/plan, /feature, /feature-ent) and implement
- `/run` or `/run mvp` — bootstrap + implement all MVP features in a loop
- `/run all` — bootstrap + implement ALL features
- `/docs` — generate bilingual documentation (RU/EN) in /README/
- `/docs update` — update existing documentation
```

### DEVELOPMENT_GUIDE.md Addition

Add to the development workflow section:

```markdown
## Autonomous Development

### Single Feature
```bash
/go <feature-name>     # Auto-selects pipeline, implements, commits, pushes
```

### Full MVP Build
```bash
/run                   # Bootstrap → implement MVP features → tag v0.1.0-mvp
/run mvp               # Same as above
```

### Complete Project Build
```bash
/run all               # Bootstrap → implement ALL features → tag v1.0.0
```

### Documentation
```bash
/docs                  # Generate docs in /README/rus/ and /README/eng/
/docs rus              # Russian only
/docs eng              # English only
/docs update           # Update existing docs with current project state
```

### Command Hierarchy
```
/run mvp
  └── /start (bootstrap)
  └── LOOP:
      ├── /next (find next feature)
      └── /go <feature>
          ├── /plan (simple tasks)
          ├── /feature (standard features)
          ├── /feature-ent (enterprise features) — only if DDD toolkit was generated
          └── /feature (complex fallback when /feature-ent not available)
```
```

### Output Directory Structure Addition

```
[project-name]-cc-toolkit/
├── ...
├── .claude/
│   ├── commands/
│   │   ├── go.md                      # ⭐ Intelligent pipeline selector — P1
│   │   ├── run.md                     # ⭐ Autonomous build loop — P1
│   │   ├── docs.md                    # ⭐ Bilingual docs generator — P1
│   │   ├── start.md                   # Full project bootstrap — MANDATORY P0
│   │   ├── feature.md                 # Feature lifecycle — MANDATORY P0
│   │   ├── myinsights.md             # Insight capture — MANDATORY P0
│   │   ├── next.md                   # Feature navigation — P1
│   │   ├── plan.md                   # Implementation planning — P1
│   │   └── ...
├── README/                            # Generated by /docs
│   ├── index.md                       # TOC with links to both languages
│   ├── rus/                           # Russian documentation
│   │   ├── deployment.md
│   │   ├── admin-guide.md
│   │   ├── user-guide.md
│   │   ├── infrastructure.md
│   │   ├── architecture.md
│   │   ├── ui-guide.md
│   │   └── user-flows.md
│   └── eng/                           # English documentation
│       ├── deployment.md
│       ├── admin-guide.md
│       ├── user-guide.md
│       ├── infrastructure.md
│       ├── architecture.md
│       ├── ui-guide.md
│       └── user-flows.md
```

### Validation Checklist (Automation Commands)

- [ ] `.claude/commands/go.md` created with complexity scoring matrix
- [ ] `.claude/commands/run.md` created with MVP/all scope handling
- [ ] `.claude/commands/docs.md` created with bilingual generation
- [ ] CLAUDE.md includes "Automation Commands" section
- [ ] DEVELOPMENT_GUIDE.md includes command hierarchy diagram
- [ ] `/go` references `/plan`, `/feature`, `/feature-ent` correctly
- [ ] `/run` references `/start`, `/next`, `/go` correctly
- [ ] `/docs` references `docs/`, `myinsights/`, source code as inputs
