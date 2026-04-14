# Self-Extracted Patterns

Reusable patterns extracted from the PU Unicorn Replicate methodology itself.
Domain-agnostic, composable with the 7 core patterns in `patterns-catalog.md`.

---

## 1. Module Orchestrator

**A thin orchestrator delegates to numbered, self-contained modules with typed interfaces.**

**Use when:** skill exceeds 400 lines; phases need independent evolution; execution order varies.
**Skip when:** skill is under 200 lines; single execution path; no conditional branches.

**Input -> Process -> Output:**
```
IN:  Orchestrator SKILL.md + modules/01-*.md ... modules/NN-*.md
DO:  1. SKILL.md declares module table (phase, file, purpose)
     2. view() loads each module at runtime
     3. Each module: Input (typed) -> Process -> Output (typed) -> Quality Gate
     4. Output of module N becomes input to module N+1
     5. Optional modules loaded conditionally
OUT: Final artifact assembled from chained module outputs
```

**PU Unicorn Example:** `cc-toolkit-generator-enhanced/SKILL.md` (~80 lines) delegates to
9 modules (~165K chars total). Core: `01-detect-parse` through `06-package-deliver`.
Extensions: `07-harvest-feedback`, `08-skill-composition`, `09-cross-project-learning`.

**Adapt:** Create orchestrator with module table + flow diagram. Number modules by execution
order. Enforce typed interface contract (Input/Process/Output/Quality Gate per module).
Use view() -- never inline content. Mark optional modules explicitly.

**Integrates with:** Pipeline Orchestration (catalog P2) for sequencing; Swarm Agent (P7) inside modules; Quality Gate (P6) between modules.

---

## 2. Feedback Loop (Harvest-Improve-Generate)

**Outputs from completed projects feed back to improve templates for future generation.**

**Use when:** templates evolve over time; multiple projects share the pipeline; you want empirical improvement.
**Skip when:** one-off generation; templates are externally mandated; feedback overhead exceeds benefit.

**Input -> Process -> Output:**
```
IN:  Harvest reports (extracted artifacts) + current generation templates
DO:  1. SCAN harvest reports for artifacts
     2. MATCH artifacts against templates by category
     3. CLASSIFY: NEW_DEFAULT | TEMPLATE_UPGRADE | NEW_RULE | RECOMMENDATION_UPDATE
     4. SCORE by impact (1-10) and risk (LOW/MEDIUM/HIGH)
     5. AUTO-APPLY if: risk=LOW AND impact>=7 AND maturity>=Beta
     6. REPORT non-eligible improvements for human review
     7. PROMOTE maturity on successful application
OUT: Updated templates + feedback report + maturity promotions
```

**PU Unicorn Example:** Module `07-harvest-feedback.md` -- `/harvest` extracts artifacts,
module 07 matches them against cc-toolkit-generator templates, auto-applies low-risk
high-impact improvements, promotes artifacts through Alpha -> Beta -> Stable.

**Adapt:** Replace artifact-to-template mapping. Keep the impact/risk matrix, auto-apply
formula, and maturity promotion thresholds (2 projects -> Beta, 3 -> Stable, 5 -> Proven).
All auto-applied changes must be additive, never destructive.

**Integrates with:** Cross-Project Learning (P4) for registry; Tiered Generation (P5) via improved templates; Quality Gate (P6) to validate updated templates.

---

## 3. Skill Composition (Dependency Graph + Path Rewriting)

**Copy skills into targets by resolving dependencies, rewriting paths, producing a manifest.**

**Use when:** skills reference each other; multiple environments with different paths; need install/uninstall manifest.
**Skip when:** skills are self-contained; single environment; small enough to copy manually.

**Input -> Process -> Output:**
```
IN:  Required skill names + source registry + target project path
DO:  1. BUILD dependency graph from view() references in SKILL.md files
     2. RESOLVE transitive dependencies (depth-first)
     3. FAIL FAST on circular dependencies before copying
     4. COPY directories (preserve structure, skip build artifacts)
     5. REWRITE paths via regex (/mnt/skills/user/X/ -> .claude/skills/X/)
     6. GENERATE skills.json manifest (graph, integrity, rewrite counts)
     7. HEALTH CHECK (unresolved paths, missing files, broken refs)
OUT: Copied skills + rewritten paths + manifest + health report
```

**PU Unicorn Example:** Module `08-skill-composition.md` copies 6+ skills during generation.
`sparc-prd-mini`'s transitive dependency on `explore` is auto-resolved. Paths rewritten
from claude.ai format to Claude Code local paths. Manifest records provenance and integrity.

**Adapt:** Define path rewriting rules table and dependency detection patterns for your
environment. Keep cycle detection, JSON manifest format, and post-copy health check.

**Integrates with:** Tiered Generation (P5) during P0 skill copying; Quality Gate (P6) for manifest integrity; Cross-Project Learning (P4) for registry data.

---

## 4. Cross-Project Learning (Registry + Relevance Scoring + Maturity Gating)

**Artifact registry with multi-dimensional scoring and maturity gates injects proven patterns into new projects.**

**Use when:** multiple projects over time; overlapping tech stacks/domains; want quality to improve per project.
**Skip when:** every project is unique; fewer than 3 completed projects; policy forbids sharing.

**Input -> Process -> Output:**
```
IN:  Project characteristics (IPM) + artifact registry + maturity model
DO:  1. SCAN registry for available artifacts
     2. SCORE relevance: stack(30) + arch(20) + domain(15) + infra(10) + maturity(15) + usage(10)
     3. RANK by composite score (0-100)
     4. FILTER by maturity gate:
        Proven >=50 -> P0 | Stable >=60 -> P1 | Beta >=70 -> P2 (confirm) | Alpha -> report only
     5. INJECT matched artifacts into generation phases
     6. TRACK usage in append-only log for maturity promotion
OUT: Augmented generation plan + learning report + usage records
```

**PU Unicorn Example:** Module `09-cross-project-learning.md` -- artifact metadata includes
tech stacks, architecture types, domains. New project IPM scored against each artifact on
6 dimensions. Proven patterns auto-inject; Alpha experiments are report-only.

**Adapt:** Define your project characteristics model and artifact metadata schema. Adjust
dimension weights for your domain. Keep maturity gating (Alpha never auto-injects) and
file-based registry (JSON) for portability.

**Integrates with:** Feedback Loop (P2) populates registry via /harvest; Skill Composition (P3) for artifact copying; Tiered Generation (P5) for injection targets.

---

## 5. Tiered Generation (P0/P1/P2/P3)

**Organize outputs into mandatory-to-optional tiers: essentials always, advanced conditionally.**

**Use when:** generator produces many artifacts; some universal, some conditional; need budget control.
**Skip when:** every project needs identical outputs; fewer than 5 artifacts; no priority ordering.

**Input -> Process -> Output:**
```
IN:  Instrument map (scored artifacts) + project characteristics
DO:  1. CLASSIFY into tiers:
        P0 Mandatory    -- always, zero conditions
        P0 Conditional  -- if characteristic flag true
        P1 Recommended  -- when docs provide enough context
        P2 Optional     -- nice-to-have, user opts in
        P3 Integration  -- external system configs
     2. GENERATE P0 first (foundation)
     3. GENERATE P1 (may reference P0)
     4. GENERATE P2-P3 (may reference P0+P1)
     5. ENFORCE context budget per tier and total
OUT: Tiered artifact set within budget constraints
```

**PU Unicorn Example:** Modules `03-generate-p0.md` through `05-generate-p2p3.md`:
P0 = CLAUDE.md, /start, /feature, git-workflow, security (always).
P0 conditional = secrets-management (if has_external_apis).
P1 = planner agent, /plan, /deploy. P1 conditional = /feature-ent (if DDD).
P2 = TDD guide. P3 = .mcp.json. Budget: ~18K target, 30K max.

**Adapt:** Define your P0 (what must every project have?). Set conditional triggers.
Set budget per tier. Ensure P0 alone produces a working system.

**Integrates with:** Cross-Project Learning (P4) informs tier assignment; Quality Gate (P6) at tier boundaries; Skill Composition (P3) during P0; Module Orchestrator (P1) for module boundaries.

---

## 6. Quality Gate (Checklist-Driven Validation)

**Score output against weighted criteria, render three-tier verdict, block if insufficient.**

**Use when:** phases produce dependent artifacts; late defects are costly; need auditable validation.
**Skip when:** single phase; speed over quality; criteria are purely subjective.

**Input -> Process -> Output:**
```
IN:  Phase output + scoring criteria (weighted) + blocking thresholds
DO:  1. APPLY criteria (binary or graduated 0-100)
     2. COMPUTE weighted aggregate score
     3. RENDER verdict:
        READY      -- all >=50, avg >=70
        CAVEATS    -- warnings, no blocks
        NEEDS_WORK -- any <50 or avg <70
     4. IF NEEDS_WORK: build Gap Register, fix, re-validate (max 3 iterations)
     5. IF max iterations exhausted: exit with gap register for human review
OUT: Verdict + score + gap register + iteration count
```

**PU Unicorn Example:** `requirements-validator` uses INVEST (50%) + SMART (30%) + coverage (20%). `doc-validator` runs 5-agent validation swarm. Module `06-package-deliver.md` runs master checklist: P0 checks, placeholder scan, budget audit, structural integrity, JSON validation.

**Adapt:** Define criteria with weights (sum to 100%). Set thresholds (<50 blocked, <70 warning). Design Gap Register for your domain. Set max iterations (3 recommended). Keep three-tier verdict system unchanged.

**Integrates with:** Module Orchestrator (P1) between phases; Tiered Generation (P5) at tier boundaries; Feedback Loop (P2) consumes pass/fail; Swarm Agent (P7) for parallel validation.

---

## 7. Swarm Agent (Parallel Independent Agents with Merge)

**Decompose into independent subtasks, run as parallel agents, aggregate with conflict resolution.**

**Use when:** 3-7 independent subtasks; clear scopes; straightforward aggregation; latency matters.
**Skip when:** subtasks depend on each other; more than 7 agents; aggregation is complex; task is trivial.

**Input -> Process -> Output:**
```
IN:  Task definition + agent table (scope, criteria, independence, output format)
DO:  1. DECOMPOSE into independent subtasks
     2. SPAWN parallel agents via Task tool
     3. Each agent: scoped input -> execute -> structured output
     4. AGGREGATE: collect, deduplicate, resolve conflicts
     5. VALIDATE aggregate for consistency
     6. IF inconsistent: run cross-validation agent (reads all outputs)
OUT: Unified result + conflict resolution notes
```

**PU Unicorn Example:** `knowledge-extractor` Phase 1 runs 5 agents (extractor-patterns,
-commands, -rules, -templates, -snippets) each scanning independently, merged by orchestrator.
`doc-validator` runs 5 validators; `validator-coherence` depends on the other 4 -- the
"tier within swarm" sub-pattern where one agent cross-validates peers.

**Adapt:** Define agent table (name, scope, criteria, independence). Ensure 3+ fully
independent agents. Design shared output format for merging. Optionally add a
cross-validation agent. Cap at 7 per swarm.

**Integrates with:** Module Orchestrator (P1) as parallelism within a phase; Quality Gate (P6) scores agent outputs; Feedback Loop (P2) consumes swarm findings.

---

## Composition Map

```
Module Orchestrator (1)
├── Phases use Swarm Agent (7) for parallel work
├── Between phases: Quality Gate (6) validates output
├── Generation phases: Tiered Generation (5) ordering
├── Skills bundled via Skill Composition (3)
├── Registry feeds Cross-Project Learning (4)
└── Post-project: Feedback Loop (2) improves templates
```

| Composition | Patterns | Use Case |
|-------------|----------|----------|
| Validated Pipeline | 1 + 6 | Sequential phases with quality gates |
| Parallel Validation | 6 + 7 | Swarm of validators for different dimensions |
| Learning Pipeline | 1 + 2 + 4 | Pipeline improving from past project data |
| Tiered Generator | 1 + 3 + 5 + 6 | P0/P1/P2 generation with validation |
| Full Lifecycle | All 7 | Complete PU Unicorn Replicate methodology |

## Quick Reference

| # | Pattern | Core Mechanism | Key Constraint |
|---|---------|----------------|----------------|
| 1 | Module Orchestrator | SKILL.md + numbered modules + view() | Typed Input/Output/Quality Gate per module |
| 2 | Feedback Loop | harvest -> match -> score -> auto-apply | Never auto-apply HIGH risk changes |
| 3 | Skill Composition | dependency graph + path rewrite + manifest | Fail fast on circular dependencies |
| 4 | Cross-Project Learning | registry + relevance scoring + maturity gate | Alpha never auto-injects |
| 5 | Tiered Generation | P0/P1/P2/P3 mandatory-to-optional | P0 alone must be a working system |
| 6 | Quality Gate | weighted criteria + verdict + iteration | Max 3 fix-and-revalidate cycles |
| 7 | Swarm Agent | parallel agents + merge + cross-validate | Cap at 7 agents per swarm |
