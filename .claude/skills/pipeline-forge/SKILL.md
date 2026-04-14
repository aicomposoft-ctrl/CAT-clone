---
name: pipeline-forge
description: >
  Meta-skill for building multi-phase AI-assisted development pipelines from extracted
  methodology patterns. Creates composable skill architectures, pipeline orchestrators,
  swarm agents, quality gates, and toolkit generators for any domain. Extracted from
  the PU Unicorn Replicate methodology — 8 skills, 5 phases, 3 agents, swarm validation.
  Triggers: "build pipeline", "create methodology", "forge pipeline", "skill architecture",
  "создай пайплайн", "методология разработки", "архитектура скиллов".
---

# Pipeline Forge: Meta-Skill for Building AI Development Pipelines

Build production-grade, multi-phase AI-assisted development pipelines from proven
methodology patterns. This skill encodes 7 architectural patterns extracted from
the PU Unicorn Replicate system and makes them reusable for any domain.

## Architecture

```
pipeline-forge/
├── SKILL.md                           # Orchestrator (this file)
├── references/
│   ├── patterns-catalog.md            # 7 core patterns with examples
│   ├── skill-anatomy.md               # How to structure composable skills
│   └── quality-gates.md               # Validation, scoring, verdicts
├── templates/
│   ├── skill-template.md              # Skeleton for new skills
│   ├── command-template.md            # Skeleton for new commands
│   ├── agent-template.md              # Skeleton for new agents
│   └── pipeline-template.md           # Skeleton for pipeline orchestrators
└── examples/
    └── replicate-analysis.md          # PU Unicorn Replicate as reference implementation
```

## When to Use

**Trigger Patterns:**
- "build a pipeline for [domain]"
- "create methodology for [process]"
- "skill architecture for [project]"
- "forge pipeline from [description]"
- "создай пайплайн для [области]"
- "архитектура скиллов"
- "методология разработки"

**Use Cases:**
- Building a new multi-phase development workflow
- Creating a plugin/template system for Claude Code
- Designing composable skill libraries
- Setting up quality gates and validation pipelines
- Creating swarm-based parallel processing workflows

## The 7 Core Patterns

| # | Pattern | Purpose | Reference |
|---|---------|---------|-----------|
| 1 | Composable Skill Architecture | Self-contained, reusable skills | `references/skill-anatomy.md` |
| 2 | Multi-Phase Pipeline Orchestration | Strict ordering, context passing | `references/patterns-catalog.md` §2 |
| 3 | Swarm of Agents | Parallel independent tasks | `references/patterns-catalog.md` §3 |
| 4 | Skill Composition via view() | Loose coupling, single source of truth | `references/patterns-catalog.md` §4 |
| 5 | Quality Gates | Scoring, verdicts, blocking thresholds | `references/quality-gates.md` |
| 6 | Documentation-Driven Development | Docs as single source, validate before code | `references/patterns-catalog.md` §6 |
| 7 | Toolkit Generation | Docs → instruments, conditional, tiered | `references/patterns-catalog.md` §7 |

## Operating Modes

| Mode | Description | Checkpoints | Time |
|------|-------------|-------------|------|
| **ANALYZE** | Analyze existing methodology, extract patterns | 0 | ~10 min |
| **DESIGN** | Design new pipeline from requirements | 3 | ~30 min |
| **FORGE** | Generate complete pipeline (skills + commands + agents + rules) | 5 | ~60 min |
| **AUDIT** | Audit existing pipeline against best practices | 2 | ~15 min |

## Pipeline

```
INPUT: Domain description / existing methodology to analyze
                    ↓
  PHASE 1: DISCOVERY
    Understand the domain, identify phases, actors, artifacts
    → Domain Model
    ⏸️ CHECKPOINT 1
                    ↓
  PHASE 2: PATTERN MATCHING
    Map domain phases to core patterns (1-7)
    Identify which patterns apply and how
    → Pattern Application Map
    ⏸️ CHECKPOINT 2
                    ↓
  PHASE 3: SKILL DECOMPOSITION
    Break domain into composable skills
    Define skill boundaries, interfaces, dependencies
    → Skill Dependency Graph
    ⏸️ CHECKPOINT 3
                    ↓
  PHASE 4: PIPELINE DESIGN
    Design orchestrator, context flow, quality gates
    Define checkpoints, verdicts, exit criteria
    → Pipeline Specification
    ⏸️ CHECKPOINT 4
                    ↓
  PHASE 5: FORGE
    Generate all files: skills, commands, agents, rules
    Apply templates, validate structure
    → Complete Pipeline Toolkit
    ⏸️ CHECKPOINT 5
                    ↓
  OUTPUT: Ready-to-use pipeline in .claude/
```

## Execution Protocol

### Phase 1: DISCOVERY

**Goal:** Understand the target domain and identify its natural phases.

**Process:**
1. Use `explore` skill (if available) to clarify vague requests
2. Identify the **actors** (who participates)
3. Identify the **artifacts** (what gets produced)
4. Identify the **phases** (natural sequential stages)
5. Identify the **quality criteria** (what makes output good)

**Discovery Questions:**
- What is the end-to-end process from input to output?
- What are the natural stages where work product changes form?
- Who are the actors at each stage?
- What artifacts are produced at each stage?
- What can go wrong at each stage?
- What are the quality criteria for each artifact?
- Which stages are independent (parallelizable)?
- Which stages have strict dependencies?

**Output — Domain Model:**
```markdown
## Domain Model: [Domain Name]

### Input
[What enters the pipeline]

### Output
[What the pipeline produces]

### Actors
| Actor | Role | Stages |
|-------|------|--------|

### Phases
| # | Phase | Input | Output | Quality Gate |
|---|-------|-------|--------|--------------|

### Artifacts
| Artifact | Producer Phase | Consumer Phase | Format |
|----------|---------------|----------------|--------|

### Parallelism Opportunities
[Which phases/tasks can run concurrently]
```

**Checkpoint:**
```
═══════════════════════════════════════════════════════════════
⏸️ CHECKPOINT 1: DOMAIN MODEL
[Summary of phases, actors, artifacts]
"ок" — proceed to Pattern Matching
"уточни [aspect]" — clarify
═══════════════════════════════════════════════════════════════
```

---

### Phase 2: PATTERN MATCHING

**Goal:** Map domain phases to the 7 core patterns.

**Process:**
1. Read `references/patterns-catalog.md` for pattern definitions
2. For each domain phase, identify which pattern(s) apply
3. Score applicability (HIGH / MEDIUM / LOW / N/A)
4. Identify custom patterns needed (not covered by the 7)

**Pattern Application Matrix:**

```markdown
## Pattern Application Map

| Domain Phase | Pattern 1: Composable | Pattern 2: Pipeline | Pattern 3: Swarm | Pattern 4: Composition | Pattern 5: Quality | Pattern 6: Doc-Driven | Pattern 7: Toolkit |
|--------------|----------------------|---------------------|-------------------|------------------------|--------------------|-----------------------|---------------------|
| Phase A | HIGH | HIGH | LOW | MEDIUM | HIGH | N/A | N/A |
| Phase B | MEDIUM | HIGH | HIGH | HIGH | MEDIUM | HIGH | N/A |
```

**Key Decisions:**
- Which phases need quality gates (Pattern 5)?
- Which phases can use swarm parallelism (Pattern 3)?
- Which skills need composition (Pattern 4)?
- Is documentation-driven approach needed (Pattern 6)?
- Does the pipeline produce a toolkit (Pattern 7)?

**Checkpoint:**
```
═══════════════════════════════════════════════════════════════
⏸️ CHECKPOINT 2: PATTERN APPLICATION MAP
[Summary of which patterns apply where]
"ок" — proceed to Skill Decomposition
"измени [pattern] для [phase]" — adjust
═══════════════════════════════════════════════════════════════
```

---

### Phase 3: SKILL DECOMPOSITION

**Goal:** Break domain into composable skills with clear boundaries.

**Process:**
1. Read `references/skill-anatomy.md` for skill structure
2. For each domain capability, create a skill definition
3. Define interfaces: inputs, outputs, dependencies
4. Create dependency graph
5. Identify reusable vs domain-specific skills

**Skill Design Principles:**
- **Single Responsibility**: One skill = one capability
- **Self-Contained**: SKILL.md + references/ + templates/ = complete
- **Loose Coupling**: Skills reference each other via view(), not inline
- **Explicit Interfaces**: Input format, output format, triggers documented
- **Fallback Strategy**: What happens if a dependency is unavailable

**Output — Skill Dependency Graph:**
```markdown
## Skills

| Skill | Responsibility | Type | Dependencies |
|-------|---------------|------|--------------|
| explore | Task clarification | Generic (reusable) | None |
| [domain-skill-1] | [what it does] | Domain-specific | explore |
| [domain-skill-2] | [what it does] | Domain-specific | [skill-1] |

## Dependency Graph

```
[orchestrator]
├── [skill-1] (Phase 1)
│   └── explore (if unclear)
├── [skill-2] (Phase 2)
│   ├── [skill-1] (context)
│   └── goap-research-ed25519 (if research needed)
├── [validator] (Phase 3)
│   └── requirements-validator
└── [generator] (Phase 4)
    └── cc-toolkit-generator-enhanced
```
```

**Checkpoint:**
```
═══════════════════════════════════════════════════════════════
⏸️ CHECKPOINT 3: SKILL DECOMPOSITION
Skills: [N] total ([M] reusable + [K] domain-specific)
Dependencies: [graph summary]
"ок" — proceed to Pipeline Design
"добавь скилл для [capability]" — add skill
"объедини [A] и [B]" — merge skills
═══════════════════════════════════════════════════════════════
```

---

### Phase 4: PIPELINE DESIGN

**Goal:** Design the orchestrator with context flow, quality gates, and checkpoints.

**Process:**
1. Read `references/quality-gates.md` for gate patterns
2. Define context flow: what data passes between phases
3. Define quality gates: scoring, verdicts, exit criteria
4. Define checkpoints: user interaction points
5. Define error handling: what happens on failure
6. Define git discipline: when to commit

**Pipeline Specification Format:**
```markdown
## Pipeline: [Name]

### Context Flow
Phase 1 → Phase 2: [what context passes]
Phase 2 → Phase 3: [what context passes]
...

### Quality Gates
| Gate | After Phase | Scoring | Blocking Threshold | Verdict Options |
|------|------------|---------|-------------------|-----------------|

### Checkpoints
| CP | After Phase | User Commands | Purpose |
|----|------------|---------------|---------|

### Error Handling
| Error | Phase | Recovery Strategy |
|-------|-------|-------------------|

### Git Commits
| After Phase | Commit Template |
|------------|-----------------|
```

**Checkpoint:**
```
═══════════════════════════════════════════════════════════════
⏸️ CHECKPOINT 4: PIPELINE SPECIFICATION
Phases: [N], Quality Gates: [M], Checkpoints: [K]
Context flow: [summary]
"ок" — proceed to Forge
"добавь gate для [phase]" — add quality gate
"измени flow" — modify context flow
═══════════════════════════════════════════════════════════════
```

---

### Phase 5: FORGE

**Goal:** Generate all pipeline files using templates.

**Process:**
1. Read templates from `templates/`
2. For each skill → generate `SKILL.md` + directory structure
3. For orchestrator → generate command `.md`
4. For agents → generate agent `.md` files
5. For rules → generate rule `.md` files
6. For hooks → generate `settings.json` entries
7. Validate all files against master checklist

**Generation Order:**
```
1. Skills (bottom-up: leaf skills first, then composites)
2. Agents (specialized workers)
3. Rules (constraints and conventions)
4. Commands (user-facing entry points)
5. Orchestrator command (pipeline entry point)
6. CLAUDE.md section (pipeline documentation)
7. settings.json (hooks)
```

**File Generation Strategy:**
- Use `templates/skill-template.md` for each skill
- Use `templates/command-template.md` for each command
- Use `templates/agent-template.md` for each agent
- Use `templates/pipeline-template.md` for the orchestrator
- Substitute `{{PLACEHOLDERS}}` with domain-specific content

**Master Validation Checklist:**
- [ ] Every skill has `SKILL.md` with name, description, triggers
- [ ] Every skill has explicit input/output format
- [ ] Every skill has anti-pattern warnings
- [ ] Orchestrator references all skills by correct path
- [ ] Quality gates have scoring systems and verdicts
- [ ] Checkpoints have user commands documented
- [ ] Context flow matches phase ordering
- [ ] Git commits defined for each major phase
- [ ] No circular dependencies in skill graph
- [ ] All templates substituted (no `{{PLACEHOLDER}}` remaining)

**Checkpoint:**
```
═══════════════════════════════════════════════════════════════
✅ PIPELINE FORGED: [Pipeline Name]

📁 Generated structure:
├── .claude/
│   ├── skills/
│   │   ├── [skill-1]/SKILL.md
│   │   ├── [skill-2]/SKILL.md
│   │   └── ...
│   ├── commands/
│   │   ├── [pipeline-command].md
│   │   └── ...
│   ├── agents/
│   │   ├── [agent-1].md
│   │   └── ...
│   └── rules/
│       ├── [rule-1].md
│       └── ...

Skills: [N] | Commands: [M] | Agents: [K] | Rules: [J]

🚀 Run /[pipeline-command] to start the pipeline
═══════════════════════════════════════════════════════════════
```

## Swarm Strategy

When designing pipelines, identify parallelism opportunities and use swarm agents:

**When to use swarms:**
- Multiple independent validations (like doc-validator's 5 parallel validators)
- Independent research tasks across topics
- Multi-artifact generation from single source
- Cross-document consistency checks

**Swarm Design Pattern:**
```
1. DECOMPOSE: Break task into independent subtasks
2. SPAWN: Launch parallel agents via Task tool
3. AGGREGATE: Collect results, merge, resolve conflicts
4. VALIDATE: Cross-check aggregate for consistency
```

**Swarm Agent Template:**
```markdown
| Agent | Scope | Criteria | Independence |
|-------|-------|----------|-------------|
| validator-X | [scope] | [criteria] | Full (no cross-deps) |
| validator-Y | [scope] | [criteria] | Full (no cross-deps) |
| validator-Z | [scope] | [criteria] | Reads X,Y output |
```

## Plugin Architecture

When building pipelines as distributable plugins:

**Install Pattern:**
```bash
# Remote install via curl
curl -sL https://raw.githubusercontent.com/[org]/[repo]/main/install.sh | bash

# What install.sh does:
# 1. Clone repo to temp directory
# 2. Detect conflicts with existing .claude/ files
# 3. Copy skills/, commands/, agents/, rules/
# 4. Write manifest for clean uninstall
# 5. Show summary and next steps
```

**Manifest Pattern:**
```
.claude/.plugin-manifest
├── skills/[name]        # Installed skill directories
├── commands/[name].md   # Installed commands
├── agents/[name].md     # Installed agents
└── rules/[name].md      # Installed rules
```

**Non-Destructive Rules:**
- Never overwrite existing files without user confirmation
- Write manifest for clean uninstall
- Don't touch source code, configs, or existing .claude files
- Support both "template" (new project) and "plugin" (existing project) modes

## Path Mapping (Portability)

Skills written for claude.ai use `/mnt/skills/user/` paths. For Claude Code portability:

| claude.ai path | Claude Code path |
|----------------|------------------|
| `/mnt/skills/user/[name]/` | `.claude/skills/[name]/` |
| `/mnt/user-data/uploads/` | `docs/` or project-specific |
| `/output/` | `docs/` or project root |

**Rule:** Always include path mapping table in orchestrator commands for cross-platform compatibility.

## Anti-Patterns

❌ **Monolithic Skills** — skills with 1000+ lines doing everything
❌ **Implicit Dependencies** — skills that assume others exist without declaring
❌ **Skipping Quality Gates** — generating toolkit from unvalidated documentation
❌ **Hardcoded Paths** — using absolute paths instead of relative/mapped
❌ **Duplicating Logic** — copying skill content instead of view() references
❌ **No Checkpoints** — running entire pipeline without user feedback points
❌ **No Error Recovery** — pipeline that can't resume from a failed phase
❌ **Over-Engineering** — creating 20 skills when 5 would suffice
❌ **No Fallbacks** — skills that crash when an optional dependency is missing

## Quality Standards

**Skill Quality:**
- [ ] SKILL.md has frontmatter (name, description, triggers)
- [ ] Clear "When to Use" with trigger patterns
- [ ] Explicit input/output formats
- [ ] Anti-patterns section
- [ ] References to related skills

**Pipeline Quality:**
- [ ] All phases have documented inputs/outputs
- [ ] Context flow is complete (no data gaps)
- [ ] Quality gates have blocking thresholds
- [ ] Checkpoints have user command reference
- [ ] Git discipline defined
- [ ] Error handling documented
- [ ] Swarm opportunities identified and used

**Plugin Quality:**
- [ ] install.sh handles conflicts gracefully
- [ ] Manifest written for uninstall
- [ ] No destructive operations without confirmation
- [ ] Works as both template and plugin

## Integration with Existing Skills

Pipeline Forge works best when combined with:

| Skill | Integration | Phase |
|-------|-------------|-------|
| `explore` | Clarify vague pipeline requirements | Phase 1 |
| `problem-solver-enhanced` | Resolve design contradictions (TRIZ) | Phase 3-4 |
| `brutal-honesty-review` | Audit pipeline for quality issues | AUDIT mode |
| `goap-research-ed25519` | Research best practices for domain | Phase 1-2 |
| `requirements-validator` | Validate pipeline specification | Phase 4 |

## Checkpoint Commands (all phases)

| Command | Action |
|---------|--------|
| `ок` / `далее` | Next phase |
| `уточни [topic]` | Clarify aspect |
| `добавь [element]` | Add skill/phase/gate |
| `убери [element]` | Remove element |
| `измени [element]` | Modify element |
| `покажи [artifact]` | Preview artifact |
| `граф` | Show dependency graph |
| `стоп` | Save state, pause |
