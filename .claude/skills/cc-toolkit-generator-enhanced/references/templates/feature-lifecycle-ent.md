# Feature Lifecycle Enterprise Templates

Templates for generating the enterprise 4-phase feature development lifecycle system.
Uses `idea2prd-manual` for deep DDD/ADR/C4 documentation — recommended for complex domain features.

---

## 1. Skill Copying Protocol

When generating the toolkit, **copy these additional skills** into `.claude/skills/`:

```bash
# Enterprise-specific skills (in addition to base /feature skills)
/mnt/skills/user/idea2prd-manual/          → .claude/skills/idea2prd-manual/
/mnt/skills/user/goap-research-ed25519/    → .claude/skills/goap-research-ed25519/
```

**Shared skills (already copied for /feature):**
```bash
# These are already present from base feature-lifecycle — do NOT duplicate
# .claude/skills/explore/
# .claude/skills/problem-solver-enhanced/
# .claude/skills/requirements-validator/
# .claude/skills/brutal-honesty-review/
```

Copy the **entire directory** for each skill (SKILL.md + references/ + scripts/).

**⚠️ Path Rewrite Required for idea2prd-manual:**
After copying, rewrite ALL `view()` paths in `idea2prd-manual/SKILL.md`:

External skill paths (3):
```
/mnt/skills/user/explore/SKILL.md              → .claude/skills/explore/SKILL.md
/mnt/skills/user/goap-research-ed25519/SKILL.md → .claude/skills/goap-research-ed25519/SKILL.md
/mnt/skills/user/problem-solver-enhanced/SKILL.md → .claude/skills/problem-solver-enhanced/SKILL.md
```

Also update informational references in `idea2prd-manual/SKILL.md`:
```
Lines 50-52: External Skills Dependencies table — update paths to .claude/skills/
```

---

## 2. Command Template: `/feature-ent`

Generate as `.claude/commands/feature-ent.md`:

```markdown
---
description: Enterprise feature lifecycle — deep DDD/ADR/C4 documentation with idea2prd-manual.
  For complex domain features requiring bounded contexts, architectural decisions, and fitness functions.
  Use /feature for simpler features, /feature-ent for enterprise-grade planning.
  $ARGUMENTS: feature name or brief description
---

# /feature-ent $ARGUMENTS

## Overview

Enterprise four-phase feature development lifecycle with quality gates.
Uses idea2prd-manual for deep domain-driven documentation.
All documentation goes to `docs/features/<feature-name>/`.

## Phase 0: PRE-FLIGHT CHECK

Before starting, verify all required skills exist:

```
Required skills in .claude/skills/:
✅ idea2prd-manual/SKILL.md          — ABORT if missing (core orchestrator)
✅ goap-research-ed25519/SKILL.md    — ABORT if missing (crypto-verified research)
⚠️ explore/SKILL.md                  — fallback: built-in Socratic questions (degraded)
⚠️ problem-solver-enhanced/SKILL.md  — fallback: First Principles + SCQA only (degraded)
✅ requirements-validator/SKILL.md   — ABORT if missing (Phase 2 blocker)
✅ brutal-honesty-review/SKILL.md    — ABORT if missing (Phase 4 blocker)
```

If any ✅ skill is missing → stop and inform user to re-run toolkit generator.
If any ⚠️ skill is missing → warn user about degraded quality, continue.

## Phase 1: PLAN (idea2prd-manual)

**Goal:** Deep domain analysis and full DDD/ADR/C4 documentation for the feature.

```
Read the idea2prd-manual skill from .claude/skills/idea2prd-manual/SKILL.md
```

1. Create feature directory: `docs/features/<feature-name>/`
2. idea2prd-manual auto-detects input type via Gate 0:
   - Problem → Analyst Pipeline (explore → research → solve) → PRD Pipeline
   - Idea → Skip to PRD Pipeline
3. idea2prd-manual delegates to external skills via view():
   - explore → Socratic questioning → Task Brief
   - goap-research-ed25519 → GOAP A* + OODA + Ed25519 verification → Research Findings
   - problem-solver-enhanced → ALL 9 modules + TRIZ → Product Idea
4. PRD Pipeline generates full enterprise documentation:
   - Phase 1: Requirements → PRD.md (10+ FR, 5+ NFR, 5+ User Stories)
   - Phase 2: DDD Strategic → Bounded Contexts, Context Map
   - Phase 3: ADR + C4 → 10+ Architecture Decision Records, C4 diagrams
   - Phase 4: DDD Tactical → Aggregates, Entities, Domain Events, schema
   - Phase 4.5: Pseudocode → .pseudo files per aggregate/service
   - Phase 5: Validation → Fitness Functions, Gherkin .feature tests, .ai-context/
   - Phase 6: Completion → CI/CD, deployment, monitoring checklist
5. Output all documents into feature directory:

```
docs/features/<feature-name>/
├── prd/PRD.md
├── ddd/
│   ├── strategic/            # Bounded contexts, context map
│   └── tactical/             # Aggregates, entities, events, schema
├── adr/                      # 10+ Architecture Decision Records
├── c4/                       # C4 diagrams (Mermaid)
├── pseudocode/               # .pseudo files per aggregate/service
├── tests/                    # Gherkin .feature test scenarios
├── fitness/                  # Fitness functions
├── completion/               # COMPLETION_CHECKLIST.md
├── .ai-context/              # 8 AI context files
└── INDEX.md                  # Document index
```

Note: CLAUDE.md is NOT generated per-feature (project-level CLAUDE.md already exists).

6. Git commit: `docs(feature-ent): enterprise planning for <feature-name>`

**⏸️ Checkpoint:** Show documentation summary with artifact counts, ask to proceed to validation.

## Phase 2: VALIDATE (requirements-validator, swarm)

**Goal:** Validate enterprise documentation quality — deeper scope than /feature.

```
Read the requirements-validator skill from .claude/skills/requirements-validator/SKILL.md
```

Use swarm of agents to validate:

| Agent | Scope | Target |
|-------|-------|--------|
| validator-stories | User Stories from PRD.md | INVEST criteria, score ≥70 |
| validator-acceptance | Acceptance Criteria | SMART criteria, testability |
| validator-ddd | DDD strategic + tactical | BC independence, aggregate size ≤7 entities |
| validator-adr | ADR consistency | All key decisions documented, no contradictions |
| validator-pseudocode | Pseudocode files | Completeness, domain event coverage |
| validator-fitness | Fitness Functions | All BCs covered, thresholds defined |
| validator-coherence | All docs cross-ref | PRD↔DDD↔ADR↔C4 consistency |

**Iterative loop (max 3 iterations):**
1. Run all validators in parallel (Task tool)
2. Aggregate gaps and blocked items
3. Fix gaps in documents
4. Re-validate
5. Repeat until: no BLOCKED items, average score ≥70

Save validation report: `docs/features/<feature-name>/validation-report.md`
Git commit: `docs(feature-ent): validation complete for <feature-name>`

**⏸️ Checkpoint:** Show validation results, ask to proceed to implementation.

## Phase 3: IMPLEMENT (swarm + parallel tasks)

**Goal:** Implement the feature using validated enterprise docs as source of truth.

When documentation is ready for implementation:
1. Read ALL documents from `docs/features/<feature-name>/`
2. Use swarm of agents and specialized skills to deliver:
   - `@planner` — break down into tasks from Pseudocode .pseudo files
   - `@architect` — ensure consistency with ADRs and C4 diagrams
   - `@domain-expert` — enforce DDD tactical patterns (aggregates, events)
   - Implementation agents — parallel Task tool per Bounded Context
3. **Make implementation modular** — one module per Bounded Context
4. Generate tests from Gherkin .feature files
5. Validate Fitness Functions during implementation
6. Save frequent commits to GitHub

**Implementation rules:**
- Each Bounded Context gets its own Task for parallel execution
- Reference docs (pseudocode, DDD tactical, ADR), don't hallucinate code
- Commit after each logical unit: `feat(<feature-name>): <what>`
- Run tests from .feature files in parallel with implementation
- Validate aggregate invariants against DDD tactical docs

**⏸️ Checkpoint:** Show implementation summary, ask to proceed to review.

## Phase 4: REVIEW (brutal-honesty-review, swarm)

**Goal:** Rigorous post-implementation review — enterprise depth.

```
Read the brutal-honesty-review skill from .claude/skills/brutal-honesty-review/SKILL.md
```

Use swarm of agents for review:

| Agent | Scope | Focus |
|-------|-------|-------|
| code-quality | Source code | Clean code, patterns, naming |
| architecture | Integration | ADR compliance, C4 consistency |
| domain-integrity | DDD patterns | Aggregate boundaries, event flow |
| security | Security surface | Vulnerabilities, input validation |
| performance | Hot paths | Bottlenecks, complexity |
| testing | Test coverage | Gherkin coverage, fitness functions passing |

Process:
1. Run brutal-honesty-review on implementation
2. Verify ADR compliance — each decision reflected in code
3. Verify Fitness Functions pass
4. Fix identified issues (use Task tool for parallel fixes)
5. Save frequent commits: `fix(<feature-name>): <what>`
6. Benchmark performance after implementation
7. Re-review critical findings until clean

Save review report: `docs/features/<feature-name>/review-report.md`
Git commit: `docs(feature-ent): review complete for <feature-name>`

## Completion

After all 4 phases:
```
✅ Feature (Enterprise): <feature-name>

📁 docs/features/<feature-name>/
├── prd/PRD.md
├── ddd/
│   ├── strategic/            # Bounded contexts
│   └── tactical/             # Aggregates, events, schema
├── adr/                      # 10+ ADRs
├── c4/                       # C4 diagrams
├── pseudocode/               # .pseudo files
├── tests/                    # Gherkin .feature files
├── fitness/                  # Fitness functions
├── completion/               # Deployment checklist
├── .ai-context/              # 8 AI context files
├── INDEX.md
├── validation-report.md
└── review-report.md

📊 Validation: score XX/100
🔍 Review: X issues found → X fixed
💾 Commits: N commits
🏗️ Bounded Contexts: N implemented
📋 ADRs verified: N/N

💡 Consider running /myinsights if you encountered any tricky issues.
```
```

---

## 3. Rule Template: `feature-lifecycle-ent.md`

Generate as `.claude/rules/feature-lifecycle-ent.md`:

```markdown
# Enterprise Feature Development Lifecycle

## Protocol

Enterprise features with complex domains follow the 4-phase lifecycle:

```
/feature-ent [name]
  Phase 1: PLAN      → idea2prd-manual → docs/features/<n>/ (DDD + ADR + C4 + tests)
  Phase 2: VALIDATE  → requirements-validator swarm (7 agents, max 3 iterations, score ≥70)
  Phase 3: IMPLEMENT → swarm per Bounded Context + parallel tasks
  Phase 4: REVIEW    → brutal-honesty-review swarm (6 agents, ADR + fitness verification)
```

## When to use /feature-ent vs /feature

| Use /feature when | Use /feature-ent when |
|-------------------|-----------------------|
| Simple CRUD features | Complex domain logic |
| No domain model needed | Multiple bounded contexts |
| Quick iteration / MVP | Production system |
| Single team scope | Cross-team boundaries |
| <3 entities involved | Rich aggregate model |

## Rules

### Planning (Phase 1)
- Enterprise features get FULL idea2prd-manual documentation
- idea2prd-manual auto-detects problem vs idea via Gate 0
- Analyst Pipeline uses goap-research-ed25519 for crypto-verified research
- All 9 problem-solver-enhanced modules executed
- Documentation lives in `docs/features/<feature-name>/` with subdirectories
- DDD Strategic and Tactical design are MANDATORY for /feature-ent
- 10+ ADRs documenting all key architectural decisions
- C4 diagrams for system context, container, and component views
- Commit docs before implementation

### Validation (Phase 2)
- Run requirements-validator with EXTENDED agent set (7 agents, not 5)
- Additional validators: DDD coherence, ADR consistency, fitness functions
- Minimum score: 70/100 average, no BLOCKED items
- Fix gaps in docs, not in code
- Max 3 iterations — if not passing, escalate to user
- Commit validation-report.md

### Implementation (Phase 3)
- One parallel Task per Bounded Context
- Read pseudocode .pseudo files — don't hallucinate code
- Enforce aggregate invariants from DDD tactical docs
- Generate test stubs from Gherkin .feature files
- Validate fitness functions during implementation
- Commit after each logical change
- Format: `feat(<feature-name>): <description>`

### Review (Phase 4)
- Use brutal-honesty-review with EXTENDED agent set (6 agents)
- Verify ADR compliance in code
- Verify all Fitness Functions pass
- Check DDD boundary integrity (no cross-BC dependencies)
- Fix all critical and major issues before marking complete
- Commit review-report.md

## Enterprise Feature Directory Structure

```
docs/features/
├── order-management/                # /feature-ent example
│   ├── prd/PRD.md
│   ├── ddd/
│   │   ├── strategic/
│   │   │   ├── bounded-contexts.md
│   │   │   └── context-map.md
│   │   └── tactical/
│   │       ├── aggregates/
│   │       ├── entities/
│   │       └── events/
│   ├── adr/
│   │   ├── ADR-001-event-sourcing.md
│   │   ├── ADR-002-cqrs-pattern.md
│   │   └── ...10+ files
│   ├── c4/
│   │   ├── system-context.mermaid
│   │   ├── container.mermaid
│   │   └── component.mermaid
│   ├── pseudocode/
│   │   ├── OrderAggregate.pseudo
│   │   └── PaymentService.pseudo
│   ├── tests/
│   │   ├── order-placement.feature
│   │   └── payment-processing.feature
│   ├── fitness/
│   │   └── fitness-functions.md
│   ├── completion/
│   │   └── COMPLETION_CHECKLIST.md
│   ├── .ai-context/
│   │   └── [8 files]
│   ├── INDEX.md
│   ├── validation-report.md
│   └── review-report.md
├── user-authentication/              # /feature example (simpler)
│   ├── sparc/
│   │   └── ...9 SPARC docs
│   └── review-report.md
└── ...
```

## When to Skip Phases

| Scenario | Skip | Justification |
|----------|------|---------------|
| Hotfix (1-5 lines) | Use /feature or skip 1-2 | Too small for enterprise |
| Config change | Use /feature | No domain model needed |
| New bounded context | NEVER skip | Full enterprise lifecycle |
| Cross-BC refactoring | Phase 1 only | Validate + implement + review |
| New aggregate | NEVER skip | Full enterprise lifecycle |

For skipped phases, still run Phase 4 (brutal-honesty-review) on the changes.
```

---

## 4. CLAUDE.md Integration

Add to CLAUDE.md generation (alongside existing /feature section):

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
- `explore` (Socratic questioning → Task Brief)
- `problem-solver-enhanced` (9 modules + TRIZ → Product Idea)
- `requirements-validator`
- `brutal-honesty-review`
```
