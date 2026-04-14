# CLAUDE.md Generation Strategy

This file defines how to generate CLAUDE.md for each pipeline. Both strategies share
a common base of sections; only the top sections differ by pipeline.

## Pipeline Detection

- Has `docs/ddd/` or `.ai-context/` → **idea2prd-manual pipeline**
- Otherwise → **SPARC pipeline**

## SPARC Pipeline — Top Sections

```markdown
# Project: [Name]

## Overview
[From PRD.md Executive Summary]

## Problem & Solution
[From Solution_Strategy.md — 2-3 sentences]

## Architecture
[From Architecture.md — monorepo structure, tech stack]

## Tech Stack
[From Architecture.md decisions table]

## Key Algorithms
[From Pseudocode.md — top 3-5 function signatures]

## Security Rules
⚠️ [From Specification.md security requirements]
[IF has_external_apis: client-side encryption mandatory]
```

## idea2prd Pipeline — Top Sections

```markdown
# Project: [Name]

## Overview
[From .ai-context/README.md]

## Architecture
[From .ai-context/architecture-summary.md]

## Key Decisions
[From .ai-context/key-decisions.md — top 5 ADRs]

## Domain Model
[From .ai-context/bounded-contexts.md]

## Glossary
[From .ai-context/domain-glossary.md — key terms]

## Tech Stack
[From ADRs + architecture-summary]

## Coding Standards
[From .ai-context/coding-standards.md]

## Quality Gates
[From .ai-context/fitness-rules.md]
```

## Common Sections (both pipelines)

Include ALL of the following sections after the pipeline-specific top sections.
These are identical regardless of pipeline.

```markdown
## Parallel Execution Strategy
- Use `Task` tool for independent subtasks
- Run tests, linting, type-checking in parallel
- For complex features: spawn specialized agents

## Swarm Agents
| Scenario | Agents | Parallelism |
|----------|--------|-------------|
| Large feature | planner + 2-3 implementation agents | Yes |
| Refactoring | code-reviewer + refactor agents | Yes |
| Bug fix | 1 agent | No |

## Git Workflow
- Commit after each logical change
- Format: `type(scope): description`
- Types: feat, fix, refactor, test, docs, chore

## Available Agents
[Generated list with trigger descriptions]

## Available Skills
[Generated list]

## Quick Commands
[Generated list — /start first]

## 🔍 Development Insights (живая база знаний)
Index: [myinsights/1nsights.md](myinsights/1nsights.md) — check here FIRST before debugging.
⚠️ On error → grep the error string in the index → read only the matched detail file.
Capture new findings: `/myinsights [title]`

## 🔄 Feature Development Lifecycle
New features use the 4-phase lifecycle: `/feature [name]`
1. **PLAN** — sparc-prd-mini (with Gate + external skills) → `docs/features/<n>/sparc/`
2. **VALIDATE** — requirements-validator swarm → score ≥70
3. **IMPLEMENT** — parallel agents from validated docs
4. **REVIEW** — brutal-honesty-review swarm → fix all criticals

Available lifecycle skills in `.claude/skills/`:
- `sparc-prd-mini` (orchestrator, delegates to explore, goap-research, problem-solver-enhanced)
- `explore` (Socratic questioning → Product Brief)
- `goap-research` (GOAP A* + OODA → Research Findings)
- `problem-solver-enhanced` (9 modules + TRIZ → Solution Strategy)
- `requirements-validator`
- `brutal-honesty-review`
```

### Enterprise Lifecycle Section (IF DDD detected — add after Feature Lifecycle)

```markdown
## 🏢 Enterprise Feature Development Lifecycle
Complex domain features use the enterprise lifecycle: `/feature-ent [name]`
1. **PLAN** — idea2prd-manual (DDD + ADR + C4 + Gherkin) → `docs/features/<n>/`
2. **VALIDATE** — requirements-validator swarm (7 agents) → score ≥70
3. **IMPLEMENT** — parallel agents per Bounded Context from validated docs
4. **REVIEW** — brutal-honesty-review swarm (6 agents) → ADR + fitness verified

Use `/feature` for simple features, `/feature-ent` for complex domain features.

Available enterprise lifecycle skills in `.claude/skills/`:
- `idea2prd-manual` (orchestrator, delegates to explore, goap-research-ed25519, problem-solver-enhanced)
- `goap-research-ed25519` (crypto-verified research with Ed25519 signatures)
```

### Remaining Common Sections (always include)

```markdown
## 📋 Feature Roadmap
Roadmap: [.claude/feature-roadmap.json](.claude/feature-roadmap.json) — single source of truth for feature status.
Sprint progress and next steps are injected automatically at session start.
Quick check: `/next` | Full overview: ask "what should I work on?"
Mark done: `/next [feature-id]` | Update all: `/next update`

## 📝 Implementation Plans
Plans: [docs/plans/](docs/plans/) — lightweight implementation plans.
Create: `/plan <feature-name>` | List: `/plan list` | Mark done: `/plan done <slug>`
For full feature lifecycle (10 docs, 4 phases): `/feature <n>`

## 🚀 Automation Commands
- `/go [feature]` — auto-select pipeline (/plan, /feature, /feature-ent) and implement
- `/run` or `/run mvp` — bootstrap + implement all MVP features in a loop
- `/run all` — bootstrap + implement ALL features
- `/docs` — generate bilingual documentation (RU/EN) in /README/
- `/docs update` — update existing documentation

## Resources
[Links to docs/ directory files]
```

## Source Priority Rules

| CLAUDE.md Section | Priority 1 | Priority 2 | Priority 3 |
|-------------------|------------|------------|------------|
| Overview | .ai-context/README | PRD Executive Summary | Final_Summary |
| Architecture | .ai-context/architecture | Architecture.md | — |
| Tech Stack | Architecture.md | ADRs | — |
| Key Decisions | .ai-context/key-decisions | ADRs | Solution_Strategy |
| Security | Specification.md | Fitness Functions | Architecture.md |
| Agents list | Generated from .claude/agents/ | — | — |
| Skills list | Generated from .claude/skills/ | — | — |
| Commands list | Generated from .claude/commands/ | — | — |

## Context Budget for CLAUDE.md

- **Target:** 4,000 tokens
- **Maximum:** 6,000 tokens
- **Rule:** If content exceeds max, prioritize: Overview > Architecture > Security > Lifecycle sections > Generated lists
