---
name: cc-toolkit-generator-enhanced
version: "2.0"
maturity: production
description: >
  Generate complete Claude Code toolkit from idea2prd-manual or SPARC documentation.
  Supports: PRD, SPARC, DDD, ADR, C4, Pseudocode, Gherkin, Fitness Functions.
  Creates CLAUDE.md, agents, skills, commands, hooks, rules, MCP configs.
  Feature lifecycle: /feature + sparc-prd-mini + requirements-validator + brutal-honesty-review.
  Enterprise lifecycle: /feature-ent + idea2prd-manual (conditional P1).
  Feature suggestions: /next + feature-navigator skill + SessionStart hook.
  Insights: /myinsights + index/detail architecture. Plans: /plan with auto-commit.
  Automation: /go (smart pipeline), /run (autonomous build loop), /docs (bilingual RU/EN docs).
  Harvest feedback: post-project learning loop from knowledge-extractor.
  Cross-project learning: pattern reuse from previous projects via maturity model.
  Skill composition: automated dependency resolution, copying, and path rewriting.
  Triggers: "cc-toolkit-enhanced", "generate toolkit from docs", "создай инструменты из документации".
  Three modes: AUTO, HYBRID (default), MANUAL.
---

> **CRITICAL MODULE LOADING REQUIREMENT:**
> This skill has 9 modules in `modules/`. SKILL.md is the orchestrator ONLY.
> You MUST read EVERY module file referenced in the Module Execution Protocol below
> before executing its phase. Skipping module files causes entire artifact categories
> to be silently omitted. In one real project, skipping `modules/04-generate-p1.md`
> caused 10+ P1 artifacts (agents, skills, commands) to be completely missing.
> NEVER generate artifacts from SKILL.md summaries alone — always read the full module.

# CC-Toolkit-Generator Enhanced

Generate production-ready Claude Code instruments from **SPARC or idea2prd-manual documentation**.

## Modular Architecture

This skill uses a composable module system. Each phase is a self-contained module with
clear INPUT → PROCESS → OUTPUT → QUALITY GATE interface.

### Core Pipeline Modules

| Phase | Module | File |
|-------|--------|------|
| 1 | Detect & Parse | `modules/01-detect-parse.md` |
| 2 | Analyze & Map | `modules/02-analyze-map.md` |
| 3 | Generate P0 (Mandatory) | `modules/03-generate-p0.md` |
| 4 | Generate P1 (Recommended) | `modules/04-generate-p1.md` |
| 5 | Generate P2-P3 (Optional) | `modules/05-generate-p2p3.md` |
| 6 | Package & Deliver | `modules/06-package-deliver.md` |

### Extension Modules

| Module | File | Purpose |
|--------|------|---------|
| Harvest Feedback | `modules/07-harvest-feedback.md` | Post-project learning loop |
| Skill Composition | `modules/08-skill-composition.md` | Dependency resolution + path rewriting |
| Cross-Project Learning | `modules/09-cross-project-learning.md` | Pattern reuse via maturity model |

### Module Execution Protocol

```
view(modules/01-detect-parse.md)     → IPM (Internal Project Model)
view(modules/02-analyze-map.md)      → Instrument Map (scored items)
  ↓ [OPTIONAL] view(modules/09-cross-project-learning.md) → Augmented Instrument Map
view(modules/03-generate-p0.md)      → P0 files
  ↓ view(modules/08-skill-composition.md) → Skills copied + paths rewritten
view(modules/04-generate-p1.md)      → P1 files (conditional)
view(modules/05-generate-p2p3.md)    → P2-P3 files (optional)
view(modules/06-package-deliver.md)  → Validated package
  ↓ [POST-PROJECT] view(modules/07-harvest-feedback.md) → Template improvements
```

## Input Documents

### SPARC Pipeline

| Document | Maps To |
|----------|---------|
| **PRD.md** | CLAUDE.md overview, /plan command, feature context |
| **Solution_Strategy.md** | CLAUDE.md problem context, architect agent |
| **Specification.md** | coding-standards/ skill, security.md rule, /test command |
| **Pseudocode.md** | planner agent templates, /start Phase 2 references |
| **Architecture.md** | CLAUDE.md tech stack, /start structure, architect agent, MCP |
| **Refinement.md** | testing.md rule, code-reviewer agent, /test command |
| **Completion.md** | /deploy command, /start Phase 3, CI/CD hooks |
| **Research_Findings.md** | project-context/ skill, domain knowledge |
| **Final_Summary.md** | CLAUDE.md quick reference, DEVELOPMENT_GUIDE.md |
| **CLAUDE.md** (from docs) | Base for enhanced CLAUDE.md |

### idea2prd-manual Pipeline

| Category | Documents | Maps To |
|----------|-----------|---------|
| **Analyst** | Task_Brief, Research_Findings, Product_Idea | CLAUDE.md context, project-context skill |
| **PRD** | PRD.md | CLAUDE.md overview, commands |
| **DDD Strategic** | bounded-contexts/, context-map | domain-model skill, architect agent |
| **DDD Tactical** | aggregates/, entities/, events/ | coding-standards skill, validation hooks |
| **ADR** | adr/*.md | CLAUDE.md decisions, rules |
| **C4** | c4/*.mermaid | architect agent, CLAUDE.md diagrams |
| **Pseudocode** | pseudocode/*.pseudo | planner agent, tdd-guide agent |
| **Tests** | tests/*.feature (Gherkin) | /test command, testing rules |
| **Fitness** | fitness/*.md | hooks (quality gates), rules |
| **Completion** | COMPLETION_CHECKLIST.md | /deploy command, CI/CD hooks |
| **.ai-context/** | 8 context files | Direct CLAUDE.md integration |

## Mode Selection

| Mode | Triggers | Checkpoints | Time |
|------|----------|-------------|------|
| **AUTO** | "auto", "быстро" | 0 | ~5 min |
| **HYBRID** | default, "smart" | 2 | ~10 min |
| **MANUAL** | "manual", "пошагово" | 6 | ~20 min |

## Workflow

> Each phase delegates to a self-contained module. Read the module file for full details.
> Modules can be used independently outside this skill for other pipelines.

### Phase 1: Detect & Parse

**Read module:** `modules/01-detect-parse.md`

Summary: Scan docs directory, detect pipeline type (SPARC/idea2prd), detect project
characteristics, build Internal Project Model (IPM).

**MANUAL Checkpoint 1:** Document Detection Review

### Phase 2: Analyze & Map

**Read module:** `modules/02-analyze-map.md`

Summary: Map documents to toolkit instruments using scoring rules.
SPARC mapping: see [SPARC Document Mapping](#sparc-document-mapping) below.
idea2prd mapping: see `references/extended-mapping.md`.

**MANUAL Checkpoint 2:** Mapping Approval

### Phase 2.5: Cross-Project Learning (Optional)

**Read module:** `modules/09-cross-project-learning.md`

Summary: If a cross-project artifact registry exists, match proven patterns against the
new project's characteristics and augment the Instrument Map with battle-tested defaults.

### Phase 3: Generate P0 (Mandatory)

**Read module:** `modules/03-generate-p0.md`

Summary: Generate all mandatory toolkit items (CLAUDE.md, rules, commands, settings, lifecycle skills).
Uses `modules/08-skill-composition.md` for skill copying and path rewriting.

**MANUAL Checkpoint 3:** P0 Review

### Phase 4: Generate P1 (Recommended)

**Read module:** `modules/04-generate-p1.md`

Summary: Generate recommended items — agents, skills, commands, enterprise lifecycle,
feature suggestions, automation commands. All conditional on project characteristics.

**MANUAL Checkpoint 4:** P1 Selection

### Phase 5: Generate P2-P3 (Optional)

**Read module:** `modules/05-generate-p2p3.md`

Summary: Generate optional advanced items — TDD guide, DDD validators, MCP configs.

**MANUAL Checkpoint 5:** P2-P3 Selection

### Phase 6: Package & Deliver

**Read module:** `modules/06-package-deliver.md`

Summary: Run Master Validation Checklist, verify all placeholders, create output package.

**MANUAL Checkpoint 6:** Final Review

### Post-Project: Harvest Feedback (After project completion)

**Read module:** `modules/07-harvest-feedback.md`

Summary: After /harvest extracts knowledge from a completed project, this module feeds
improvements back into toolkit templates for future generations.

## Output Structure

```
[project-name]-cc-toolkit/
├── CLAUDE.md
├── DEVELOPMENT_GUIDE.md
├── .claude/
│   ├── settings.json                   # Hooks: insights + roadmap + plans, SessionStart
│   ├── feature-roadmap.json            # Feature status (from PRD)
│   ├── hooks/feature-context.py        # SessionStart: inject feature context
│   ├── agents/
│   │   ├── planner.md, code-reviewer.md, architect.md
│   │   ├── tdd-guide.md               # P2
│   │   ├── domain-expert.md           # {{IF_DDD}}
│   │   └── ddd-validator.md           # {{IF_DDD}} P2
│   ├── skills/
│   │   ├── sparc-prd-mini/            # ⭐ P0 — feature planning orchestrator
│   │   ├── explore/                   # ⭐ P0 — Socratic questioning
│   │   ├── goap-research/             # ⭐ P0 — GOAP research
│   │   ├── problem-solver-enhanced/   # ⭐ P0 — 9 modules + TRIZ
│   │   ├── requirements-validator/    # ⭐ P0 — doc validation
│   │   ├── brutal-honesty-review/     # ⭐ P0 — post-impl review
│   │   ├── idea2prd-manual/          # {{IF_DDD}} P1
│   │   ├── goap-research-ed25519/    # {{IF_DDD}} P1
│   │   ├── feature-navigator/        # P1 — roadmap navigation
│   │   ├── project-context/, coding-standards/, testing-patterns/
│   │   ├── security-patterns/        # {{IF_EXTERNAL_APIS}}
│   │   ├── aggregate-patterns/       # {{IF_DDD}} P2
│   │   └── event-handlers/           # {{IF_DDD}} P2
│   ├── commands/
│   │   ├── start.md                   # ⭐ P0 — full project bootstrap
│   │   ├── myinsights.md             # ⭐ P0 — insight capture
│   │   ├── feature.md                # ⭐ P0 — feature lifecycle
│   │   ├── feature-ent.md           # {{IF_DDD}} P1
│   │   ├── next.md, plan.md         # P1
│   │   ├── go.md, run.md, docs.md   # P1 — automation
│   │   ├── test.md, deploy.md, review.md
│   │   └── validate-ddd.md          # {{IF_DDD}} P2
│   └── rules/
│       ├── security.md, coding-style.md, testing.md
│       ├── git-workflow.md           # ⭐ P0
│       ├── insights-capture.md      # ⭐ P0
│       ├── feature-lifecycle.md     # ⭐ P0
│       ├── feature-lifecycle-ent.md # {{IF_DDD}} P1
│       ├── secrets-management.md    # {{IF_EXTERNAL_APIS}}
│       ├── domain-model.md          # {{IF_DDD}}
│       └── fitness-functions.md     # {{IF_DDD}}
├── docs/features/, docs/plans/
├── README/                          # Bilingual (RU/EN), created by /docs
├── .mcp.json                        # {{IF_EXTERNAL_INTEGRATIONS}}
└── INSTALL.md
```

**Markers:** `{{IF_DDD}}` = DDD docs detected; `{{IF_EXTERNAL_APIS}}` = external APIs; `{{IF_EXTERNAL_INTEGRATIONS}}` = external MCP.

## SPARC Document Mapping

> Primary pipeline. Apply when `docs/ddd/` is NOT present.

| SPARC Document | Section | Primary Output | Secondary Output |
|----------------|---------|----------------|------------------|
| **PRD.md** | Executive Summary | CLAUDE.md Overview | — |
| PRD.md | Problem Statement | CLAUDE.md Problem Context | architect.md |
| PRD.md | Functional Requirements | /plan features | /start Phase 2 scope |
| PRD.md | NFRs | security.md, testing.md | rules |
| PRD.md | User Stories | /test templates | testing-patterns/ |
| **Solution_Strategy.md** | Root Cause / Framework | project-context/, architect.md | CLAUDE.md |
| **Specification.md** | Data Model / API / Security | /start Phase 2, security.md | coding-standards/ |
| **Pseudocode.md** | Algorithms / Error Handling | planner.md, code-reviewer.md | /start refs |
| **Architecture.md** | Structure / Stack / Docker / APIs | CLAUDE.md, /start, .mcp.json | coding-style.md |
| **Refinement.md** | Edge Cases / Testing / Security | code-reviewer.md, testing.md, /test | tdd-guide.md |
| **Completion.md** | CI/CD / Docker / Monitoring | /deploy, /start Phase 3 | hooks |
| **Research_Findings.md** | Tech Decisions / Best Practices | architect.md, coding-standards/ | CLAUDE.md |
| **Final_Summary.md** | Quick Reference | CLAUDE.md | DEVELOPMENT_GUIDE.md |

### Extraction Patterns

```
EXTRACT PRD.md:       name → title, problem → context, requirements → features, NFRs → rules
EXTRACT Architecture: structure → /start P1, packages → /start P2, docker → /start P3,
                      stack → CLAUDE.md, APIs → security-patterns, DB → migration
EXTRACT Pseudocode:   functions → planner templates, algorithms → /start P2 refs,
                      errors → code-reviewer
```

## Smart Recommendations

```
# SPARC Core
Architecture.md → architect.md (+10), /start (+10)
Pseudocode.md   → planner.md (+10), BOOST /start P2
Refinement.md   → testing.md (+8), code-reviewer.md (+8), /test (+8)
Solution_Strategy → project-context/ (+8), BOOST architect (+3)
Completion.md   → /deploy (+8), BOOST /start P3

# Detection-based
"API"|"integration"|"external" → security-patterns/ (+10), secrets-management.md (+10)
"PostgreSQL"|"MongoDB"|"database" → BOOST /start P3 with migration
"Coolify" → coolify MCP (+8);  "Docker" → docker MCP (+5)

# DDD-Specific
docs/ddd/strategic/         → domain-expert.md (+10)
docs/ddd/tactical/aggregates → ddd-validator.md (+10), /validate-ddd (+8)
docs/ddd/tactical/events/    → event-handlers/ (+8)
docs/adr/ (>10 files)       → architect.md (+10)
docs/tests/*.feature         → testing-patterns/ (+10), tdd-guide.md (+8)
docs/fitness/                → fitness-functions.md (+10)
.ai-context/                 → INTEGRATE into CLAUDE.md, project-context/ (+10)
```

See `references/enhanced-recommendations.md` for detailed scoring.

## CLAUDE.md Generation

**Read `references/claude-md-strategy.md`** for complete generation strategy.

Two pipeline-specific strategies with shared base sections:
- **SPARC** → emphasis on Problem & Solution, Key Algorithms
- **idea2prd** → emphasis on Domain Model, Key Decisions, Quality Gates

Both include: Parallel Execution Strategy, Swarm Agents, Git Workflow, Available Agents/Skills/Commands, Development Insights, Feature Lifecycle, Feature Roadmap, Plans, Automation Commands.

## Key Systems (read templates before generating)

| System | Template File | Key Components |
|--------|--------------|----------------|
| **/start** | `templates/start-command.md` | 4-phase bootstrap, parallel Tasks, anti-hallucination |
| **Insights** | `templates/insights-system.md` | /myinsights, insights-capture rule, Stop hook, index+detail |
| **Feature Lifecycle** | `templates/feature-lifecycle.md` | /feature (4 phases), 6 skills copy, path rewrite |
| **Enterprise Lifecycle** | `templates/feature-lifecycle-ent.md` | /feature-ent, idea2prd-manual, goap-research-ed25519 |
| **Feature Suggestions** | `templates/feature-suggestions.md` | /next, feature-navigator, roadmap.json, SessionStart |
| **Automation** | `templates/automation-commands.md` | /go, /run, /docs, command hierarchy |
| **DDD Agents** | `templates/ddd-agents.md` | domain-expert, ddd-validator |
| **DDD Skills** | `templates/ddd-skills.md` | aggregate-patterns, event-handlers |
| **DDD Hooks/Commands** | `templates/ddd-hooks-commands.md` | hooks, /validate-ddd |
| **MCP** | `templates/mcp.md` | .mcp.json generation |
| **Enhanced CLAUDE.md** | `templates/enhanced-claude-md.md` | Additional CLAUDE.md sections |

## Context Budget

| Component | Target | Max |
|-----------|--------|-----|
| CLAUDE.md | 4k | 6k |
| /start command | 2k | 4k |
| /myinsights, /feature, /plan | 3k combined | 5.5k |
| Domain rules | 1.5k | 2.5k |
| Generated skills + agents | 3.5k | 5k |
| Copied lifecycle skills | 0 | 0 (on-demand) |
| Commands + hooks | 1k | 2k |
| DEVELOPMENT_GUIDE | 1k | 2k |
| **Total** | ~18k | 30k (<15% of 200k) |

## Checkpoint Commands (MANUAL Mode)

| Checkpoint | Commands |
|------------|----------|
| CP1: Detection | `ок`, `добавь [doc]`, `убери [doc]` |
| CP2: Mapping | `повысь [tool]`, `понизь [tool]`, `покажи mapping` |
| CP3: P0 | `измени [file]`, `покажи [file]` |
| CP4: P1 | `+N`, `-N`, `всё`, `минимум` |
| CP5: P2-P3 | `+agents`, `+skills`, `+hooks`, `+mcp` |
| CP6: Final | `превью [file]`, `скачать`, `добавить [tool]` |

## Master Validation Checklist

Run in Phase 6 before delivery.

### P0 Mandatory

- [ ] CLAUDE.md generated per `references/claude-md-strategy.md`
- [ ] CLAUDE.md includes: Parallel Execution, Swarm Agents, Insights, Feature Lifecycle, Roadmap, Plans, Automation
- [ ] DEVELOPMENT_GUIDE.md with full lifecycle instructions
- [ ] `/start` — complete project gen, all packages, Task parallelism, Docker health check, references actual docs
- [ ] `/myinsights` — duplicate detection, subcommands, index+detail architecture
- [ ] `insights-capture.md` rule with auto-grep pattern
- [ ] `/feature` — 4-phase lifecycle (plan → validate → implement → review)
- [ ] `feature-lifecycle.md` rule
- [ ] 6 lifecycle skills copied with path rewrite (`/mnt/skills/user/` → `.claude/skills/`)
- [ ] `git-workflow.md` rule (semantic commits)
- [ ] `settings.json` — Stop hooks (insights + roadmap + plans) + SessionStart hook
- [ ] `docs/features/` directory created

### P0 Conditional

- [ ] `secrets-management.md` + `security-patterns/` — IF has_external_apis
- [ ] `domain-model.md` rule — IF DDD Strategic docs
- [ ] `/start` includes DB migration + seed — IF has_database

### P1 Enterprise (IF DDD)

- [ ] `/feature-ent` + `feature-lifecycle-ent.md` rule
- [ ] `idea2prd-manual/` + `goap-research-ed25519/` skills copied with path rewrites
- [ ] CLAUDE.md Enterprise Feature Lifecycle section

### P1 Feature Suggestions

- [ ] `feature-roadmap.json` populated (min 5 features from PRD)
- [ ] `feature-context.py` SessionStart hook
- [ ] `/next` command + `feature-navigator/` skill

### P1 Automation

- [ ] `/go` — complexity scoring → pipeline selection
- [ ] `/run` — /start → /next → /go loop (MVP/all scope)
- [ ] `/docs` — bilingual RU/EN generation

### Pipeline-Specific (IF applicable)

- [ ] Bounded Contexts → agent scopes (DDD)
- [ ] Aggregates → validation patterns (DDD)
- [ ] ADR decisions → rules (ADR)
- [ ] Fitness Functions → hooks (Fitness)
- [ ] Gherkin features → test commands (Gherkin)
- [ ] .ai-context/ → CLAUDE.md integration

## Dependencies

### Required
- SPARC documentation set (11 files) — primary pipeline
- Alternatively: idea2prd-manual/auto output

### Optional
- `.ai-context/` directory — enhanced CLAUDE.md integration
- `knowledge-extractor` skill — for harvest feedback loop (module 07)
- Cross-project artifact registry — for pattern reuse (module 09)

### Skill Dependencies (managed by module 08)

| Skill | Copied To | Priority | Condition |
|-------|-----------|----------|-----------|
| sparc-prd-mini | .claude/skills/ | P0 | Always |
| explore | .claude/skills/ | P0 | Always |
| goap-research | .claude/skills/ | P0 | Always |
| problem-solver-enhanced | .claude/skills/ | P0 | Always |
| requirements-validator | .claude/skills/ | P0 | Always |
| brutal-honesty-review | .claude/skills/ | P0 | Always |
| idea2prd-manual | .claude/skills/ | P1 | IF DDD detected |
| goap-research-ed25519 | .claude/skills/ | P1 | IF DDD detected |
| feature-navigator | .claude/skills/ | P1 | Always (recommended) |

## Reusability

This skill's modules are designed for reuse across different IT contexts:

| Module | Reuse Context |
|--------|--------------|
| 01-detect-parse | Any pipeline needing document type detection |
| 02-analyze-map | Any document-to-artifact mapping with scoring |
| 03-06 (generation) | Template-based code/config generation |
| 07-harvest-feedback | Any system with post-production learning loops |
| 08-skill-composition | Any project that composes AI skills/plugins |
| 09-cross-project-learning | Any AI pipeline that learns from past projects |
