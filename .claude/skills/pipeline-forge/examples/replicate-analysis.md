# Reference Implementation: PU Unicorn Replicate

Analysis of the PU Unicorn Replicate methodology as a reference implementation
of all 7 Pipeline Forge patterns. Use this as a model for designing your own pipelines.

---

## System Overview

**Purpose:** Transform a product idea into a fully equipped Claude Code project, ready for
AI-assisted development (Vibe Coding).

**Pipeline:** Idea → Documentation → Validation → Toolkit → Scaffold

**Stats:**
- 8 composable skills
- 5 pipeline phases (1 optional)
- 3 specialized agents
- 5 parallel validation sub-agents (swarm)
- 11 SPARC documentation files generated
- ~30 Claude Code instruments generated (commands, agents, rules, skills, hooks)

---

## Pattern Application Map

| Pattern | How PU Unicorn Replicate Uses It |
|---------|----------------------------------|
| 1. Composable Skills | 8 skills with SKILL.md entry, references/, templates/, modules/ |
| 2. Pipeline Orchestration | 5-phase `/replicate` pipeline with checkpoints and git commits |
| 3. Swarm of Agents | 5 parallel validators in Phase 2 (doc-validator) |
| 4. Skill Composition | sparc-prd-mini loads explore, goap-research, problem-solver via view() |
| 5. Quality Gates | INVEST/SMART scoring, 0-100 scale, BLOCKED <50, 3 iteration max |
| 6. Doc-Driven Dev | 11 SPARC docs as single source, validated before toolkit generation |
| 7. Toolkit Generation | Docs → commands, agents, rules, skills, hooks; P0/P1/P2 tiers |

---

## Skill Inventory

### Leaf Skills (no dependencies)

| Skill | Lines | Purpose | Used By |
|-------|-------|---------|---------|
| `explore` | ~220 | Socratic task clarification | sparc-prd-mini, reverse-engineering-unicorn |
| `problem-solver-enhanced` | ~560 | 9-module problem solving + TRIZ | sparc-prd-mini |
| `requirements-validator` | ~125 | INVEST/SMART validation + BDD | doc-validator agent |
| `brutal-honesty-review` | ~225 | Unvarnished technical criticism | /feature command |

### Composite Skills (depend on others via view())

| Skill | Lines | Dependencies | Used By |
|-------|-------|-------------|---------|
| `goap-research-ed25519` | ~415 | None (standalone) | sparc-prd-mini, reverse-engineering-unicorn |
| `sparc-prd-mini` | ~955 | explore, goap-research, problem-solver | /replicate Phase 1 |
| `reverse-engineering-unicorn` | ~195 + 7 modules | explore, goap-research, problem-solver, brutal-honesty | /replicate Phase 0 |
| `cc-toolkit-generator-enhanced` | ~375 + 11 templates | Reads docs, no skill deps | /replicate Phase 3 |

### Dependency Graph

```
/replicate (command)
├── reverse-engineering-unicorn (Phase 0)
│   ├── explore
│   ├── goap-research-ed25519
│   ├── problem-solver-enhanced
│   └── brutal-honesty-review
├── sparc-prd-mini (Phase 1)
│   ├── explore
│   ├── goap-research-ed25519
│   └── problem-solver-enhanced
├── requirements-validator (Phase 2, via doc-validator agent)
├── cc-toolkit-generator-enhanced (Phase 3)
└── (Phase 4: no skills, just scaffold)
```

---

## Pipeline: /replicate

### Phase Flow

```
INPUT: Product idea or company name
                    ↓
  PHASE 0: PRODUCT DISCOVERY (optional)
    Skill: reverse-engineering-unicorn (QUICK mode)
    Modules: M2 (Product), M3 (Market), M4 (Business), M5 (Growth)
    Output: Product Discovery Brief
    Gate: activate if SaaS/startup, skip if internal tool
    ⏸️ CHECKPOINT 0
    git commit: (none — brief is in-memory context)
                    ↓
  PHASE 1: PLANNING
    Skill: sparc-prd-mini (MANUAL mode)
    Internal phases: Explore → Research → Solve → Spec → Pseudo → Arch → Refine → Complete
    Output: 11 SPARC documents in docs/
    Constraints: Distributed Monolith, Docker, VPS, MCP
    ⏸️ CHECKPOINT 1
    git commit: "docs: SPARC documentation for [project-name]"
                    ↓
  PHASE 2: VALIDATION
    Agent: doc-validator (swarm of 5 parallel validators)
    Criteria: INVEST ≥50, SMART ≥50, avg ≥70
    Max iterations: 3
    Output: docs/validation-report.md, docs/test-scenarios.md
    ⏸️ CHECKPOINT 2
    git commit: "docs: validation report and BDD scenarios"
                    ↓
  PHASE 3: TOOLKIT GENERATION
    Skill: cc-toolkit-generator-enhanced
    Input: validated docs from docs/
    Output: CLAUDE.md, commands, agents, rules, skills, hooks
    Tiers: P0 (mandatory), P1 (recommended), P2 (optional)
    ⏸️ CHECKPOINT 3
    git commit: "feat: Claude Code toolkit for [project-name]"
                    ↓
  PHASE 4: FINALIZE
    Output: docker-compose.yml, Dockerfile, .gitignore
    git commit: "chore: initial project setup from SPARC documentation"
    Final summary with project structure and next steps
```

### Context Flow

| From | To | What Passes |
|------|----|-------------|
| Phase 0 | Phase 1 | Product Discovery Brief (JTBD, competitors, Blue Ocean) |
| Phase 1 | Phase 2 | 11 SPARC documents in docs/ |
| Phase 2 | Phase 3 | Validated docs + validation-report.md + test-scenarios.md |
| Phase 3 | Phase 4 | Complete toolkit (commands, agents, rules, skills) |

### Quality Gate (Phase 2)

```
Swarm: 5 parallel validators via Task tool
├── validator-stories     → INVEST on user stories
├── validator-acceptance  → SMART on acceptance criteria
├── validator-architecture → Target constraints compliance
├── validator-pseudocode  → Story coverage, implementability
└── validator-coherence   → Cross-document consistency

Scoring: 0-100 per validator
Aggregate: weighted average
Blocking: score <50 = BLOCKED
Iterations: max 3

Verdicts:
  🟢 READY:      all ≥50, avg ≥70, no contradictions → Phase 3
  🟡 CAVEATS:    warnings, no blocked, limitations noted → Phase 3 with notes
  🔴 NEEDS WORK: blocked items exist → return to Phase 1
```

---

## Skill Composition Example

### How sparc-prd-mini composes 3 external skills

```
sparc-prd-mini/SKILL.md declares:

| Phase | Skill | Action |
|-------|-------|--------|
| Phase 0: Explore | explore | view(".claude/skills/explore/SKILL.md") |
| Phase 1: Research | goap-research-ed25519 | view(".claude/skills/goap-research-ed25519/SKILL.md") |
| Phase 2: Solve | problem-solver-enhanced | view(".claude/skills/problem-solver-enhanced/SKILL.md") |

Fallbacks:
- explore unavailable → built-in 3-5 Socratic questions
- goap-research unavailable → direct web_search
- problem-solver unavailable → First Principles + SCQA only

Pre-filled context acceptance:
- Product Brief provided? → skip Phase 0
- Research Findings provided? → skip Phase 1
- Solution Strategy provided? → skip Phase 2
```

---

## Toolkit Generation Example (Phase 3)

### What cc-toolkit-generator-enhanced produces from SPARC docs

**P0 (Mandatory) — always generated:**
```
CLAUDE.md                          ← PRD + Architecture + Final_Summary
.claude/commands/start.md          ← Architecture + Pseudocode
.claude/commands/feature.md        ← feature-lifecycle template
.claude/commands/myinsights.md     ← insights-system template
.claude/rules/git-workflow.md      ← semantic commits
.claude/rules/security.md         ← Specification NFRs
.claude/rules/coding-style.md     ← Architecture tech stack
.claude/rules/insights-capture.md ← insights-system template
.claude/rules/feature-lifecycle.md ← feature-lifecycle template
.claude/settings.json              ← hooks (insights, roadmap, plans)
6 lifecycle skills (copied)        ← explore, goap, solver, validator, brutal, sparc-prd
```

**P1 (Recommended) — if docs provide context:**
```
.claude/agents/planner.md          ← Pseudocode + PRD
.claude/agents/code-reviewer.md    ← Refinement + Specification
.claude/agents/architect.md        ← Architecture + Solution_Strategy
.claude/skills/project-context/    ← Research_Findings
.claude/skills/coding-standards/   ← Architecture tech stack
.claude/commands/plan.md           ← PRD + Pseudocode
.claude/commands/test.md           ← Refinement
.claude/commands/deploy.md         ← Completion
.claude/commands/next.md           ← feature suggestions
.claude/commands/go.md             ← smart pipeline
.claude/commands/run.md            ← autonomous loop
.claude/commands/docs.md           ← bilingual docs
.claude/rules/testing.md           ← Refinement test strategy
feature-roadmap.json               ← PRD features
```

**P1 Conditional — if detected:**
```
IF has_external_apis:
  .claude/rules/secrets-management.md
  .claude/skills/security-patterns/

IF has_ddd_docs:
  .claude/commands/feature-ent.md
  .claude/rules/feature-lifecycle-ent.md
  .claude/skills/idea2prd-manual/
  .claude/skills/goap-research-ed25519/ (copy)
```

---

## Plugin Architecture

### install.sh flow

```
1. Pre-flight: check git, warn if not git repo
2. Clone: git clone --depth 1 to temp dir
3. Detect conflicts: check .claude/{skills,commands,agents,rules}/*
4. If conflicts: prompt user (y/N)
5. Install:
   - mkdir -p .claude/{skills,commands,agents,rules}
   - cp -r skills/ (8 skills)
   - cp -r commands/ (1 command)
   - cp -r agents/ (3 agents)
   - cp -r rules/ (1 rule)
6. Write manifest: .claude/.replicate-plugin-manifest
7. Summary: counts + next steps
```

### uninstall.sh flow

```
1. Read manifest
2. Show what will be removed
3. Prompt user
4. Remove files listed in manifest
5. Remove manifest
6. Clean empty dirs
7. Summary (preserves project-specific files)
```

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Skills use view() not inline | Single source of truth, auto-propagation of updates |
| Phase 2 never skipped | Quality gate ensures toolkit is built on validated docs |
| MANUAL mode for sparc-prd-mini | User controls each sub-phase of documentation |
| Swarm of 5 validators | Independent checks parallelized for speed |
| P0/P1/P2 tiers | Not everything is mandatory; reduces noise for simple projects |
| Path mapping tables | Portability between claude.ai and Claude Code environments |
| Manifest for uninstall | Clean removal without affecting project files |
| Architecture constraints injected | All projects follow same infrastructure pattern |

---

## Lessons for New Pipelines

1. **Start with the dependency graph** — identify leaf skills first, then composites
2. **Quality gates are non-negotiable** — never skip validation between major phases
3. **Swarm where independent** — 5 validators run faster in parallel than sequentially
4. **Context budget matters** — keep CLAUDE.md under 6k tokens, total under 30k
5. **Fallbacks for everything** — skills should work even if dependencies are missing
6. **Git at phase boundaries** — semantic commits enable rollback to any phase
7. **Checkpoints for user control** — automated does not mean uncontrolled
8. **Plugin architecture** — install.sh + manifest = clean install/uninstall
