# Module: Generate P1 (Recommended)

Phase 4 of the CC-Toolkit-Generator-Enhanced pipeline. Generates recommended instruments
that significantly enhance the developer experience. Items are scored by the recommendation
engine and conditionally included based on project characteristics and document richness.

## Input

- **Internal Project Model (IPM)** — from Phase 1 (Detect & Parse)
  - `project_name`, `tech_stack`, `docker_services`, `monorepo_packages`
  - `has_external_apis`, `has_database`, `has_ddd`, `has_gherkin`, `has_fitness`
  - `has_ai_context`, `has_pseudocode`, `has_adr`, `has_c4`
- **Instrument Map** — from Phase 2 (Analyze & Map)
  - Scored instrument list with tier assignments (P0/P1/P2/P3)
  - Document-to-instrument mapping with source references
- **P0 Outputs** — from Phase 3 (Generate P0)
  - Generated CLAUDE.md, settings.json, feature-lifecycle rule, 6 lifecycle skills
  - Confirmed project paths and naming conventions

## Process

> **ANTI-COMPRESSION DIRECTIVE:** When generating files from templates in this module,
> COPY the FULL text of each template. Do NOT summarize, compress, or "interpret" templates.
> Every section, every placeholder, every comment must be preserved verbatim.
> AI systems routinely compress 211-line templates to 60 lines — this is a CRITICAL defect.
> Validate: generated file line count must be >= 80% of template line count.

### Step 1: Filter P1 Candidates

Select all instruments assigned tier P1 from the Instrument Map (score >= 12 after tier boosts).
Apply the scoring engine from `view("references/enhanced-recommendations.md")` to finalize the set.

```
P1 Candidate Instruments:
  Agents:    planner.md, code-reviewer.md, architect.md
  Skills:    project-context/, coding-standards/, testing-patterns/
  Commands:  /plan, /test, /deploy
  Rules:     testing.md

Conditional P1 (require detection flags):
  Enterprise Lifecycle:   /feature-ent, feature-lifecycle-ent.md rule, idea2prd-manual/ skill, goap-research-ed25519/ skill
  Feature Suggestions:    /next, feature-navigator/ skill, feature-roadmap.json, SessionStart hook, feature-context.py
  Automation Commands:    /go, /run, /docs
```

### Step 2: Generate Core P1 Agents

#### 2a. planner.md Agent

Source documents: Pseudocode.md (SPARC) or `docs/pseudocode/*.pseudo` (idea2prd)

```
Generate .claude/agents/planner.md:
  - Extract algorithm structures from Pseudocode documents
  - Include function signatures, error handling patterns
  - Reference actual pseudocode file paths in agent instructions
  - Set model: sonnet, tools: Read, Glob, Grep, Write
  - Include planning templates derived from PRD functional requirements
```

Fill `{{PSEUDOCODE_REFERENCES}}` from IPM pseudocode index.
Fill `{{PLANNING_TEMPLATES}}` from PRD functional requirements.

#### 2b. code-reviewer.md Agent

Source documents: Refinement.md + Specification.md (SPARC) or Fitness Functions + ADRs (idea2prd)

```
Generate .claude/agents/code-reviewer.md:
  - Extract review criteria from Refinement.md edge cases and security checks
  - IF has_ddd: include DDD compliance checklist from view("references/templates/ddd-agents.md")
  - IF has_fitness: include fitness function verification checklist
  - IF has_adr: include ADR compliance verification list
  - Set model: sonnet, tools: Read, Glob, Grep, Bash
  - Include code quality standards from Specification.md NFRs
```

Fill `{{REVIEW_CHECKLIST}}` from Refinement edge cases.
Fill `{{FITNESS_FUNCTIONS_CHECKLIST}}` from fitness functions (if present).
Fill `{{ADR_COMPLIANCE_LIST}}` from top ADRs (if present).

#### 2c. architect.md Agent

Source documents: Architecture.md + Solution_Strategy.md (SPARC) or C4 + ADRs + DDD Strategic (idea2prd)

```
Generate .claude/agents/architect.md:
  - Extract system structure from Architecture.md
  - Include tech stack rationale from Solution_Strategy.md
  - IF has_c4: include C4 context and container summaries from view("references/templates/ddd-agents.md")
  - IF has_adr: include top 5-10 ADR summaries with status
  - IF has_fitness: include architecture fitness functions
  - Set model: opus, tools: Read, Glob, Grep, Write
  - Include ADR template for new architectural decisions
```

Fill `{{C4_CONTEXT_SUMMARY}}` from C4 diagrams (if present).
Fill `{{TOP_ADRS_SUMMARY}}` from ADR files (if present).
Fill `{{ARCHITECTURE_FITNESS_FUNCTIONS}}` from fitness docs (if present).

### Step 3: Generate Core P1 Skills

#### 3a. project-context/ Skill

Source: Research_Findings.md + Final_Summary.md (SPARC) or .ai-context/* + Research (idea2prd)

```
Generate .claude/skills/project-context/SKILL.md:
  - Use template from view("references/templates/ddd-skills.md") section "project-context/ Skill (Enhanced)"
  - IF has_ai_context: integrate all 8 .ai-context files directly
    - README.md → Overview
    - architecture-summary.md → Architecture Summary
    - key-decisions.md → Key Decisions
    - domain-glossary.md → Domain Glossary
    - bounded-contexts.md → Bounded Contexts
  - ELSE: extract from Research_Findings.md and Final_Summary.md
  - Fill {{FROM_PRD_PERSONAS}} from PRD user personas
  - Fill {{FROM_PRD_METRICS}} from PRD success metrics
```

#### 3b. coding-standards/ Skill

Source: Architecture.md tech stack (SPARC) or DDD Tactical + ADRs + .ai-context/coding-standards.md (idea2prd)

```
Generate .claude/skills/coding-standards/SKILL.md:
  - Use template from view("references/templates/ddd-skills.md") section "coding-standards/ Skill (Enhanced)"
  - Extract tech stack conventions from Architecture.md
  - IF has_ddd: include DDD naming conventions and file organization
  - IF has_adr: extract coding-related decisions as standards
  - IF has_ai_context: integrate .ai-context/coding-standards.md directly
  - Fill {{TECH_KEYWORDS}} from IPM tech stack
  - Fill {{CODING_STANDARDS_FROM_ADRS}} from ADR extraction
  - Fill {{ANTI_PATTERNS_FROM_REJECTED_ADRS}} from rejected ADR alternatives
```

#### 3c. testing-patterns/ Skill

Source: Refinement.md test strategy (SPARC) or Gherkin + Fitness Functions (idea2prd)

```
Generate .claude/skills/testing-patterns/SKILL.md:
  - Use template from view("references/templates/ddd-skills.md") section "testing-patterns/ Skill (Enhanced)"
  - IF has_gherkin: extract Given/When/Then patterns, create step-to-code mappings
  - IF has_fitness: include coverage requirements from fitness functions
  - ELSE: derive testing patterns from Refinement.md test strategy
  - Fill {{GHERKIN_FEATURES_TABLE}} from docs/tests/*.feature index
  - Fill {{GIVEN_MAPPINGS}}, {{WHEN_MAPPINGS}}, {{THEN_MAPPINGS}} from Gherkin steps
  - Fill {{LINE_TARGET}}, {{BRANCH_TARGET}} from fitness functions
```

### Step 4: Generate Core P1 Commands

#### 4a. /plan Command

Source: PRD.md + Pseudocode.md

```
Generate .claude/commands/plan.md:
  - Lightweight implementation planning with persistence to docs/plans/
  - Include auto-commit via Stop hook (already in settings.json from P0)
  - Reference planner agent for complex plans
  - Include plan template with sections: Goal, Tasks, Files, Dependencies, Risks
  - Generate docs/plans/ directory
```

#### 4b. /test Command

Source: Refinement.md + Specification.md (SPARC) or Gherkin + Pseudocode (idea2prd)

```
Generate .claude/commands/test.md:
  - IF has_gherkin: use enhanced template from view("references/templates/ddd-hooks-commands.md") section "/test Command"
    - Include available Gherkin features list
    - Support: /test [feature], /test all, /test generate [feature]
    - Include Gherkin-to-test mapping examples
  - ELSE: standard test runner command
    - Support: /test, /test [scope], /test coverage
  - Fill {{GHERKIN_FEATURES_LIST}} from docs/tests/*.feature
  - Fill {{GENERATED_TEST_TEMPLATE}} from tech stack test conventions
```

#### 4c. /deploy Command

Source: Completion.md (SPARC) or COMPLETION_CHECKLIST.md (idea2prd)

```
Generate .claude/commands/deploy.md:
  - Use enhanced template from view("references/templates/ddd-hooks-commands.md") section "/deploy Command"
  - Extract pre-deployment checklist from Completion.md
  - Include environment tiers: dev (auto), staging (checks), prod (manual)
  - IF has_fitness: include fitness function verification in pre-deploy
  - IF has_ddd: include DDD validation in pre-deploy
  - Fill {{FROM_COMPLETION_CHECKLIST}} from Completion docs
```

### Step 5: Generate Core P1 Rules

#### 5a. testing.md Rule

Source: Refinement.md (SPARC) or Fitness Functions (idea2prd)

```
Generate .claude/rules/testing.md:
  - Extract testing requirements and standards
  - IF has_fitness: include fitness function thresholds (coverage targets, complexity limits)
  - IF has_gherkin: include Gherkin scenario coverage requirements
  - Include test naming conventions from tech stack
  - Include test organization rules (unit/integration/e2e)
```

### Step 6: Conditional P1 — Enterprise Lifecycle (IF DDD detected)

**Trigger:** `IPM.has_ddd == true`

Read complete template: `view("references/templates/feature-lifecycle-ent.md")`
> CRITICAL: COPY the full template. Do NOT compress or summarize.

```
IF has_ddd:
  6a. Generate .claude/commands/feature-ent.md
      - Full enterprise 4-phase lifecycle command
      - Phase 0: Pre-flight check (verify skills exist)
      - Phase 1: PLAN (idea2prd-manual → DDD/ADR/C4/Gherkin)
      - Phase 2: VALIDATE (requirements-validator swarm, 7 agents, score >= 70)
      - Phase 3: IMPLEMENT (parallel agents per Bounded Context)
      - Phase 4: REVIEW (brutal-honesty-review swarm, 6 agents)
      - Output to docs/features/<feature-name>/ with full subdirectory structure

  6b. Generate .claude/rules/feature-lifecycle-ent.md
      - When to use /feature-ent vs /feature decision matrix
      - Enterprise planning rules (full idea2prd-manual, mandatory DDD)
      - Enterprise validation rules (7 agents, extended scope)
      - Enterprise implementation rules (Task per Bounded Context)
      - Enterprise review rules (6 agents, ADR + fitness verification)

  6c. Copy skill directories with path rewrite:
      - Copy .claude/skills/idea2prd-manual/ (entire directory)
        Path rewrite in SKILL.md:
          /mnt/skills/user/explore/SKILL.md → .claude/skills/explore/SKILL.md
          /mnt/skills/user/goap-research-ed25519/SKILL.md → .claude/skills/goap-research-ed25519/SKILL.md
          /mnt/skills/user/problem-solver-enhanced/SKILL.md → .claude/skills/problem-solver-enhanced/SKILL.md
        Also update informational references (Lines 50-52): paths to .claude/skills/

      - Copy .claude/skills/goap-research-ed25519/ (entire directory)

      NOTE: Do NOT duplicate skills already copied in P0:
        - explore/ (already present)
        - problem-solver-enhanced/ (already present)
        - requirements-validator/ (already present)
        - brutal-honesty-review/ (already present)

  6d. Add Enterprise Feature Lifecycle section to CLAUDE.md:
      - /feature-ent usage summary
      - Available enterprise lifecycle skills list
      - When to use /feature vs /feature-ent guidance
```

### Step 7: Conditional P1 — Feature Suggestions System

**Trigger:** Always generated for P1 (enhances developer workflow regardless of pipeline).

Read complete template: `view("references/templates/feature-suggestions.md")`
> CRITICAL: COPY the full template. Do NOT compress or summarize.

```
7a. Generate .claude/feature-roadmap.json
    - Pre-populate from PRD.md Functional Requirements
    - Extract feature names, descriptions, MoSCoW priorities
    - Extract dependencies from Architecture.md
    - Status assignment:
      - Already implemented (git/codebase scan) → "done"
      - Current sprint, highest priority → "in_progress" (max 1-2)
      - Next Must-have features → "next"
      - Should-have features → "planned"
      - Features with unmet depends_on → "blocked"
    - Minimum viable roadmap: at least 5 features with correct statuses

7b. Generate .claude/hooks/feature-context.py
    - SessionStart hook script
    - Reads feature-roadmap.json + git log + TODO scan
    - Outputs context snapshot: sprint progress, current/next features, blockers, recent commits
    - Keep timeout <= 10 seconds

7c. Update .claude/settings.json (merge with existing from P0):
    - Add SessionStart hook: python3 .claude/hooks/feature-context.py (timeout: 10)
    - Add Stop hook: auto-commit feature-roadmap.json if changed
    - Merge with existing Stop hooks (insights + plans auto-commit)

7d. Generate .claude/skills/feature-navigator/SKILL.md
    - Read roadmap, git log, TODO scan
    - Present sprint progress, in-progress, next-up, blocked items
    - Suggest top 3 actions (actionable, 3-8 words each)
    - Update roadmap when features are completed (cascade dependency unblocking)
    - Priority rules: in_progress > next > planned; respect depends_on

7e. Generate .claude/commands/next.md
    - Default: show sprint progress + top 3 next tasks
    - /next update: scan codebase, suggest status updates
    - /next [feature-id]: mark done, cascade unblocking, show next

7f. Add Feature Roadmap section to CLAUDE.md:
    - Link to feature-roadmap.json
    - /next command usage summary
    - SessionStart hook explanation

7g. Add Feature Workflow section to DEVELOPMENT_GUIDE.md:
    - /next → pick feature → /feature or /feature-ent → /next [id] cycle
```

### Step 8: Conditional P1 — Automation Commands

**Trigger:** Always generated for P1 (provides autonomous execution capabilities).

Read complete template: `view("references/templates/automation-commands.md")`
> CRITICAL: COPY the full template. Do NOT compress or summarize.

```
8a. Generate .claude/commands/go.md
    - Step 1: Determine target feature (from $ARGUMENTS or /next logic)
    - Step 2: Analyze complexity with scoring matrix:
      | Signal                              | Score  |
      | Touches <= 3 files                  | -2     |
      | Touches 4-10 files                  | 0      |
      | Touches > 10 files                  | +3     |
      | External API integration            | +2     |
      | New database entities               | +2     |
      | Cross-bounded-context dependencies  | +3     |
      | Hotfix or minor improvement         | -3     |
      | DDD docs in project                 | +1     |
      | Gherkin scenarios for feature       | +1     |
      | Implementation < 30 min             | -2     |
      | Implementation > 2 hours            | +3     |
    - Step 3: Decision matrix:
      | Score   | Pipeline     | Condition                   |
      | <= -2   | /plan        | Simple task                 |
      | -1 to 4 | /feature     | Standard feature            |
      | >= +5   | /feature-ent | IF feature-ent available    |
      | >= +5   | /feature     | IF feature-ent NOT available (with warning) |
    - Step 4: Execute selected pipeline autonomously
    - Step 5: Post-implementation — update roadmap, commit, push, report

8b. Generate .claude/commands/run.md
    - Step 0: Parse scope — "mvp" (default) or "all"
    - Step 1: Bootstrap project via /start (skip if already bootstrapped)
    - Step 2: Feature loop — /next → /go → verify → repeat
      - mvp scope: implement only "next" and "in_progress" features
      - all scope: implement ALL features until every one is "done"
    - Step 3: Finalize — full test suite, tag (v0.1.0-mvp or v1.0.0), summary report
    - Error recovery: independent commits, skip after 3 failures, always push state

8c. Generate .claude/commands/docs.md
    - Step 1: Gather context from docs/, CLAUDE.md, myinsights/, source code
    - Step 2: Determine scope — languages (rus/eng/both), mode (create/update)
    - Step 3: Generate 7 documentation files per language:
      1. deployment.md
      2. admin-guide.md
      3. user-guide.md
      4. infrastructure.md
      5. architecture.md
      6. ui-guide.md
      7. user-flows.md
    - Step 4: Generate README/index.md (bilingual table of contents)
    - Step 5: Commit and report

8d. Add Automation Commands section to CLAUDE.md:
    - /go, /run, /run mvp, /run all, /docs summary
    - Command hierarchy diagram

8e. Add Autonomous Development section to DEVELOPMENT_GUIDE.md:
    - Single feature: /go
    - Full MVP: /run or /run mvp
    - Complete project: /run all
    - Documentation: /docs, /docs rus, /docs eng, /docs update
    - Command hierarchy: /run → /start → /next → /go → /plan|/feature|/feature-ent
```

## Output

### Generated Files (Core P1)

| File | Type | Path |
|------|------|------|
| planner.md | Agent | `.claude/agents/planner.md` |
| code-reviewer.md | Agent | `.claude/agents/code-reviewer.md` |
| architect.md | Agent | `.claude/agents/architect.md` |
| project-context/ | Skill | `.claude/skills/project-context/SKILL.md` |
| coding-standards/ | Skill | `.claude/skills/coding-standards/SKILL.md` |
| testing-patterns/ | Skill | `.claude/skills/testing-patterns/SKILL.md` |
| plan.md | Command | `.claude/commands/plan.md` |
| test.md | Command | `.claude/commands/test.md` |
| deploy.md | Command | `.claude/commands/deploy.md` |
| testing.md | Rule | `.claude/rules/testing.md` |

### Generated Files (Conditional: Enterprise Lifecycle — IF DDD)

| File | Type | Path |
|------|------|------|
| feature-ent.md | Command | `.claude/commands/feature-ent.md` |
| feature-lifecycle-ent.md | Rule | `.claude/rules/feature-lifecycle-ent.md` |
| idea2prd-manual/ | Skill (copy) | `.claude/skills/idea2prd-manual/` |
| goap-research-ed25519/ | Skill (copy) | `.claude/skills/goap-research-ed25519/` |

### Generated Files (Conditional: Feature Suggestions — Always P1)

| File | Type | Path |
|------|------|------|
| feature-roadmap.json | Data | `.claude/feature-roadmap.json` |
| feature-context.py | Hook | `.claude/hooks/feature-context.py` |
| settings.json | Config (merge) | `.claude/settings.json` |
| feature-navigator/ | Skill | `.claude/skills/feature-navigator/SKILL.md` |
| next.md | Command | `.claude/commands/next.md` |

### Generated Files (Conditional: Automation Commands — Always P1)

| File | Type | Path |
|------|------|------|
| go.md | Command | `.claude/commands/go.md` |
| run.md | Command | `.claude/commands/run.md` |
| docs.md | Command | `.claude/commands/docs.md` |

### Modified Files (CLAUDE.md and DEVELOPMENT_GUIDE.md sections added)

- CLAUDE.md: Enterprise Feature Lifecycle, Feature Roadmap, Automation Commands sections
- DEVELOPMENT_GUIDE.md: Feature Workflow, Autonomous Development sections

### Directories Created

- `docs/plans/` (for /plan command output)
- `.claude/hooks/` (for feature-context.py)

## Quality Gate

All of the following must pass before proceeding to Phase 5:

### Core P1 Validation

- [ ] All 3 agents generated with correct `model`, `tools`, and `skills` fields
- [ ] All 3 skills generated with `name`, `description`, and `---` frontmatter
- [ ] All 3 commands generated with `description` and `$ARGUMENTS` frontmatter
- [ ] `testing.md` rule generated with testing standards from source docs
- [ ] All `{{PLACEHOLDER}}` values substituted with actual project data
- [ ] No `{{IF_DDD}}` markers in output when `has_ddd == false`
- [ ] Agent/skill descriptions include trigger keywords for auto-activation
- [ ] All scored items above P1 threshold (score >= 12) are generated

### Conditional: Enterprise Lifecycle Validation (IF DDD)

- [ ] `/feature-ent` command includes all 4 phases with checkpoints
- [ ] `feature-lifecycle-ent.md` rule includes decision matrix (/feature vs /feature-ent)
- [ ] `idea2prd-manual/` skill copied with ALL path rewrites applied (3 external skill paths)
- [ ] `goap-research-ed25519/` skill copied completely
- [ ] No duplicate skill copies (explore, problem-solver-enhanced already in P0)
- [ ] CLAUDE.md includes Enterprise Feature Lifecycle section

### Conditional: Feature Suggestions Validation

- [ ] `feature-roadmap.json` is valid JSON with >= 5 features
- [ ] Feature statuses correctly assigned from MoSCoW priorities
- [ ] `feature-context.py` is valid Python, timeout <= 10 seconds
- [ ] `settings.json` merges SessionStart + Stop hooks correctly (no overwrite of P0 hooks)
- [ ] `feature-navigator/SKILL.md` includes priority rules and roadmap update logic
- [ ] `/next` command supports: default, update, and [feature-id] subcommands

### Conditional: Automation Commands Validation

- [ ] `/go` includes complexity scoring matrix with correct thresholds
- [ ] `/go` checks for `/feature-ent` availability before selecting it
- [ ] `/go` includes fallback behavior when `/feature-ent` is not available
- [ ] `/run` supports both "mvp" and "all" scope modes
- [ ] `/run` includes error recovery (skip after 3 failures, always push)
- [ ] `/docs` generates 7 files per language with correct structure
- [ ] CLAUDE.md includes Automation Commands section
- [ ] DEVELOPMENT_GUIDE.md includes command hierarchy diagram

### Context Budget Check

- [ ] Generated skills + agents total <= 5k tokens (target 3.5k)
- [ ] Commands + hooks total <= 2k tokens (target 1k)
- [ ] CLAUDE.md additions stay within 6k total limit

## Dependencies

### Template Files (read via view())

| Template | Used For |
|----------|----------|
| `references/templates/feature-lifecycle-ent.md` | Enterprise lifecycle: /feature-ent, rule, skill copy protocol |
| `references/templates/feature-suggestions.md` | Feature suggestions: /next, feature-navigator, roadmap.json, hooks |
| `references/templates/automation-commands.md` | Automation: /go, /run, /docs commands |
| `references/templates/ddd-agents.md` | DDD-enhanced agent templates: domain-expert, ddd-validator, architect, tdd-guide, code-reviewer |
| `references/templates/ddd-skills.md` | DDD-enhanced skill templates: aggregate-patterns, event-handlers, testing-patterns, project-context, coding-standards |
| `references/enhanced-recommendations.md` | Scoring engine for instrument selection and tier assignment |

### Upstream Modules

| Module | Provides |
|--------|----------|
| `01-detect-parse.md` | IPM with project characteristics and detection flags |
| `02-analyze-map.md` | Instrument Map with scored items and tier assignments |
| `03-generate-p0.md` | P0 outputs (CLAUDE.md, settings.json, lifecycle skills) to extend |

### Skill Dependencies (copy sources)

| Skill | Source Location | Condition |
|-------|----------------|-----------|
| idea2prd-manual/ | `.claude/skills/idea2prd-manual/` | IF has_ddd |
| goap-research-ed25519/ | `.claude/skills/goap-research-ed25519/` | IF has_ddd |

## Reusability

### Conditional Generation Pattern with Scoring Engine

The scoring-based conditional generation pattern used in this module is universal and can be
applied to any multi-file generation system where output should adapt to input characteristics:

1. **Define detection flags** from input analysis (boolean characteristics)
2. **Score each candidate output** using weighted rules tied to input signals
3. **Assign tiers** based on score thresholds (mandatory/recommended/optional)
4. **Conditionally generate** only items that meet their tier threshold
5. **Apply path rewrites** when copying assets between contexts

This pattern avoids monolithic "generate everything" approaches while maintaining deterministic
output based on input quality. The scoring engine can be extracted and reused for:

- Plugin/extension generation systems
- Configuration scaffold generators
- Template-based project initializers
- Any system where output complexity should scale with input richness

### Feature Suggestions as Reusable System

The feature-roadmap.json + SessionStart hook + /next command pattern is a self-contained
feature navigation system that can be extracted and used in any project with a backlog:

- JSON data file as single source of truth
- Hook injects context at session start (zero runtime cost)
- Command provides interactive navigation
- Skill enables on-demand deep inspection
- Auto-commit on session end preserves state

### Automation Command Hierarchy

The /go -> /run orchestration pattern (simple command delegates to appropriate pipeline
based on analysis) is reusable for any multi-pipeline execution system where the correct
pipeline depends on runtime characteristics of the input.
