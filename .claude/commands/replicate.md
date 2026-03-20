---
description: >
  Replicate pipeline — полный цикл подготовки проекта к Vibe Coding.
  Генерирует SPARC документацию, валидирует, создаёт project-specific toolkit.
  $ARGUMENTS: описание продукта/идеи или название компании для reverse engineering.
---

# /replicate $ARGUMENTS

## Role

Координатор подготовки к Vibe Coding. Генерируешь всё для старта проекта
в Claude Code — прямо в текущем репозитории, без zip-архивов.

## Target Architecture (Constraints)

Все проекты создаются под эту целевую архитектуру:

| Аспект | Решение |
|--------|---------|
| **Архитектура** | Distributed Monolith в Monorepo |
| **Контейнеризация** | Docker + Docker Compose |
| **Инфраструктура** | VPS (AdminVPS/HOSTKEY) |
| **Деплой** | Docker Compose на VPS (direct deploy) |
| **AI Integration** | MCP серверы |

## Skills (loaded from .claude/skills/)

All skills are available locally. Read their SKILL.md when needed:

| Skill | Path | Phase |
|-------|------|-------|
| reverse-engineering-unicorn | `.claude/skills/reverse-engineering-unicorn/SKILL.md` | Phase 0 |
| sparc-prd-mini | `.claude/skills/sparc-prd-mini/SKILL.md` | Phase 1 |
| explore | `.claude/skills/explore/SKILL.md` | Phase 1 (dependency) |
| goap-research-ed25519 | `.claude/skills/goap-research-ed25519/SKILL.md` | Phase 1 (dependency) |
| problem-solver-enhanced | `.claude/skills/problem-solver-enhanced/SKILL.md` | Phase 1 (dependency) |
| requirements-validator | `.claude/skills/requirements-validator/SKILL.md` | Phase 2 |
| cc-toolkit-generator-enhanced | `.claude/skills/cc-toolkit-generator-enhanced/SKILL.md` | Phase 3 |
| brutal-honesty-review | `.claude/skills/brutal-honesty-review/SKILL.md` | Phase 4 (/feature) |

**IMPORTANT (Claude Code adaptation):**
- Skills reference `view("/mnt/skills/user/...")` paths from claude.ai
- In Claude Code, replace ALL such references with `.claude/skills/[name]/SKILL.md`
- When sparc-prd-mini calls `view("/mnt/skills/user/explore/SKILL.md")`, read `.claude/skills/explore/SKILL.md` instead
- When sparc-prd-mini calls `view("/mnt/skills/user/goap-research/SKILL.md")`, read `.claude/skills/goap-research-ed25519/SKILL.md` instead

## Pipeline

```
INPUT → [PRODUCT DISCOVERY] → PLANNING → VALIDATION → TOOLKIT → FINALIZE
         (optional)            sparc-prd   requirements  cc-toolkit  commit
                               -mini       -validator    -generator  & report
```

**Note:** sparc-prd-mini v2 already includes Explore, Research, and Solve phases
internally via skill references. The coordinator does NOT duplicate these phases.

## Execution

### Start

1. Briefly explain the phases (4 main + 1 optional)
2. Mention the target architecture (distributed monolith + Docker на VPS)
3. Determine project type → is Product Discovery needed?
4. Begin with the relevant phase

### Phase 0: PRODUCT DISCOVERY (optional)

**Gate — when to activate:**
- New product / startup / SaaS → **activate**
- Competitors to analyze → **activate**
- Internal tool / experiment → **skip**

Read the skill: `.claude/skills/reverse-engineering-unicorn/SKILL.md`

**Mode:** QUICK (sufficient for informing PRD)

**Selected modules:**

| Module | When needed | Output for PRD |
|--------|------------|----------------|
| M2: Product & Customers | Always | JTBD, Value Prop, segments |
| M3: Market & Competition | Always | TAM/SAM, competitors, Blue Ocean |
| M4: Business & Finance | If monetization | Unit economics |
| M5: Growth Engine | If B2C/PLG | Channels, integrations |

**Output:** Product Discovery Brief → passed as pre-filled context to Phase 1

**Checkpoint:**
```
═══════════════════════════════════════════════════════════════
✅ PHASE 0: PRODUCT DISCOVERY
[Summary from brief]
⏸️ "ок" — next | "превью discovery" — show brief
═══════════════════════════════════════════════════════════════
```

### Phase 1: PLANNING

Read the skill: `.claude/skills/sparc-prd-mini/SKILL.md`

**sparc-prd-mini v2 runs 8 internal phases:**
- Phase 0: Explore → explore skill (read from `.claude/skills/explore/SKILL.md`)
- Phase 1: Research → goap-research-ed25519 skill (read from `.claude/skills/goap-research-ed25519/SKILL.md`)
- Phase 2: Solve → problem-solver-enhanced skill (read from `.claude/skills/problem-solver-enhanced/SKILL.md`)
- Phases 3-7: Specification, Pseudocode, Architecture, Refinement, Completion

**Pass context to the skill:**

```yaml
Architecture Constraints:
  pattern: "Distributed Monolith (Monorepo)"
  containers: "Docker + Docker Compose"
  infrastructure: "VPS (AdminVPS/HOSTKEY)"
  deploy: "Docker Compose direct deploy (SSH / CI pipeline)"
  ai_integration: "MCP servers"

Product Context: # From Phase 0 (if applicable)
  target_segments: [from JTBD]
  key_competitors: [from competitive matrix]
  differentiation: [from Blue Ocean]
  monetization: [from Unit Economics]

Security Pattern: # If external integrations
  api_keys_input: "UI Settings > Integrations"
  storage: "Encrypted IndexedDB (AES-GCM 256-bit)"
  key_derivation: "PBKDF2 from user password"
  server_side: "No key storage on backend"
```

**Mode:** MANUAL (checkpoint at each phase inside sparc-prd-mini)

**Output location:** `docs/` directory (NOT `/output/` — write directly into the project)

Write all 11 documents to `docs/`:
- `docs/PRD.md`
- `docs/Solution_Strategy.md`
- `docs/Specification.md`
- `docs/Pseudocode.md`
- `docs/Architecture.md`
- `docs/Refinement.md`
- `docs/Completion.md`
- `docs/Research_Findings.md`
- `docs/Final_Summary.md`
- `docs/C4_Diagrams.md` (if applicable)
- `docs/ADR.md` (if applicable)

Git commit: `docs: SPARC documentation for [project-name]`

**Checkpoint:**
```
═══════════════════════════════════════════════════════════════
✅ PHASE 1: PLANNING (SPARC DOCUMENTATION)
Created [N] documents in docs/
⏸️ "ок" — next to validation | "превью [filename]" — show file
═══════════════════════════════════════════════════════════════
```

### Phase 2: VALIDATION

Read the skill: `.claude/skills/requirements-validator/SKILL.md`

**Goal:** Verify all documentation for completeness, testability, and implementation readiness.

**Strategy: Swarm of Validation Agents**

| Agent | Scope | Criteria |
|-------|-------|----------|
| `validator-stories` | PRD → User Stories | INVEST criteria, score ≥70 |
| `validator-acceptance` | Stories → AC | SMART criteria, testability |
| `validator-architecture` | Architecture.md | Target constraints, completeness |
| `validator-pseudocode` | Pseudocode.md | Story coverage, implementability |
| `validator-coherence` | Cross-document | Consistency, no contradictions |

**Process (iterative, max 3 iterations):**

```
1. ANALYZE — parallel validator agents (use Task tool)
2. AGGREGATE — Gap Register + Blocked/Warning items
3. FIX — resolve gaps in documentation
4. RE-VALIDATE — re-check fixes
↻ Until: no BLOCKED (≥50), average ≥70, no contradictions
```

**BDD Scenarios Generation:**
- Happy path (1-2), Error handling (2-3), Edge cases (1-2), Security
- Save as `docs/test-scenarios.md`

**Save validation report:** `docs/validation-report.md`

Git commit: `docs: validation report and BDD scenarios`

**Exit Criteria:**

| Verdict | Conditions | Action |
|---------|-----------|--------|
| 🟢 READY | All scores ≥50, average ≥70, no contradictions | → Phase 3 |
| 🟡 CAVEATS | Warnings exist, no blocked, limitations described | → Phase 3 with notes |
| 🔴 NEEDS WORK | Blocked items exist | → Return to Phase 1 |

**Checkpoint:**
```
═══════════════════════════════════════════════════════════════
✅ PHASE 2: VALIDATION COMPLETE
Verdict: [🟢/🟡/🔴]
Average Score: XX/100
Iterations: N/3
⏸️ "ок" — generate toolkit | "превью validation" — show report
═══════════════════════════════════════════════════════════════
```

### Phase 3: TOOLKIT GENERATION

Read the skill: `.claude/skills/cc-toolkit-generator-enhanced/SKILL.md`

**Goal:** Generate project-specific Claude Code instruments IN-PLACE.

**IMPORTANT (Claude Code adaptation):**
- Scan `docs/` directory for SPARC documents (NOT `/mnt/user-data/uploads/`)
- Generate files IN-PLACE into the project (NOT into output directory)
- Lifecycle skills already exist in `.claude/skills/` — do NOT copy
- Generic commands (`/feature`, `/myinsights`) already exist — do NOT overwrite
- Generic rules (`feature-lifecycle`, `insights-capture`, `git-workflow`) already exist — do NOT overwrite
- `settings.json` already exists with hooks — do NOT overwrite

**Generate these project-specific files:**

**1. Enhance CLAUDE.md** (root) with project-specific content:
- Project overview from PRD.md
- Architecture from Architecture.md
- Tech stack decisions
- Parallel execution strategy
- Swarm agents section
- Available agents/skills/commands list
- Development insights section
- Feature lifecycle section

**2. Commands (`.claude/commands/`):**
- `start.md` — project bootstrap (uses /start template from cc-toolkit skill)
- `plan.md` — implementation planning
- `test.md` — test generation/execution
- `deploy.md` — deployment workflow

**3. Agents (`.claude/agents/`):**
- `planner.md` — feature planning with algorithm templates from Pseudocode.md
- `code-reviewer.md` — quality review with edge cases from Refinement.md
- `architect.md` — system design from Architecture.md + Solution_Strategy.md
- Additional agents based on project characteristics

**4. Project-specific Rules (`.claude/rules/`):**
- `security.md` — from Specification.md NFRs
- `coding-style.md` — from Architecture.md tech stack
- `secrets-management.md` — IF external APIs detected
- `testing.md` — from Refinement.md test strategy

**5. Project-specific Skills (`.claude/skills/`):**
- `project-context/` — domain knowledge from Research_Findings.md
- `coding-standards/` — tech-specific patterns from Architecture.md
- `security-patterns/` — IF external APIs (encrypted storage pattern)

**6. Additional files:**
- `.mcp.json` — IF external integrations
- `DEVELOPMENT_GUIDE.md` — step-by-step development lifecycle
- `README.md` — enhanced with project info

Git commit: `feat: Claude Code toolkit for [project-name]`

**Checkpoint:**
```
═══════════════════════════════════════════════════════════════
✅ PHASE 3: TOOLKIT GENERATED
- CLAUDE.md enhanced with project context
- [N] agents + [N] commands + [N] rules generated
- DEVELOPMENT_GUIDE.md created
⏸️ "ок" — finalize | "превью toolkit" — show structure
═══════════════════════════════════════════════════════════════
```

### Phase 4: FINALIZE

**Goal:** Generate scaffold files, commit everything, show summary.

**Generate scaffold files:**

1. `docker-compose.yml` — from Architecture.md services
2. `Dockerfile` — from Architecture.md tech stack
3. `.gitignore` — if not exists
4. `docs/features/` — create empty directory for future features

**Git operations:**
```bash
git add .
git commit -m "chore: initial project setup from SPARC documentation"
```

**Show final summary:**
```
═══════════════════════════════════════════════════════════════
✅ REPLICATE COMPLETE: [project-name]

📁 Project structure:
├── CLAUDE.md                     # Project context
├── DEVELOPMENT_GUIDE.md          # Dev lifecycle guide
├── README.md                     # Quick start
├── docs/                         # [N] SPARC documents
│   ├── validation-report.md      # Validation results
│   ├── test-scenarios.md         # BDD scenarios
│   └── features/                 # For future features
├── .claude/
│   ├── commands/                 # /start, /feature, /plan, /test, /deploy, /myinsights
│   ├── agents/                   # planner, code-reviewer, architect
│   ├── skills/                   # 8 shared + project-specific skills
│   ├── rules/                    # git-workflow, security, coding-style, ...
│   └── settings.json             # Hooks (insights auto-commit)
├── docker-compose.yml            # Scaffold
└── Dockerfile                    # Scaffold

🚀 Next steps:
1. Run /start to bootstrap the project
2. First feature: [recommended from PRD MVP]

💡 Available commands:
- /start         — bootstrap project from docs
- /feature [name] — full feature lifecycle
- /plan [feature] — plan implementation
- /test [scope]   — run/generate tests
- /deploy [env]   — deploy to environment
- /myinsights     — capture development insights
═══════════════════════════════════════════════════════════════
```

## Development Practices (embedded in toolkit)

### 1. Swarm of Agents & Parallel Execution

Include in CLAUDE.md:
```markdown
## Parallel Execution Strategy
- Use `Task` tool for independent subtasks
- Run tests, linting, type-checking in parallel
- For complex features: spawn specialized agents
```

### 2. Client-Side Secrets Management (if external APIs)

**Mandatory pattern for apps with external integrations:**

```
PRINCIPLE: User enters keys via UI → stored encrypted in browser → NEVER sent to backend
```

**Security Implementation:**
- Encryption at Rest: AES-GCM 256-bit (Web Crypto API)
- Key derivation: PBKDF2 from user password (100k+ iterations)
- Storage: IndexedDB for encrypted data, master key only in memory
- Auto-lock after inactivity timeout
- Never: transmit to backend, log, store in plaintext

## Checkpoint Commands

| Command | Action |
|---------|--------|
| `ок` | Next phase |
| `превью [filename]` | View generated file |
| `превью discovery` | Show Product Discovery Brief |
| `превью validation` | Show Validation Report |
| `превью toolkit` | Show toolkit structure |

## Critical Rules

### ALWAYS
- Read skill SKILL.md before executing its logic
- Checkpoint after each phase
- Pass Architecture Constraints to sparc-prd-mini
- Write docs to `docs/` directory (not `/output/`)
- Generate toolkit IN-PLACE (not into separate directory)
- Use existing generic commands/rules (don't regenerate /feature, /myinsights, etc.)

### NEVER
- Don't duplicate explore/research phases — sparc-prd-mini does this internally
- Never skip validation — toolkit is built on validated docs
- Never use base cc-toolkit-generator — only enhanced version
- Don't overwrite template files (generic commands, rules, settings.json)

### CONDITIONAL
- If external APIs → include security-patterns/ skill + secrets-management.md rule
- If new product → start with Phase 0 (Product Discovery)
- If B2B/Enterprise → strengthen security patterns in validation
