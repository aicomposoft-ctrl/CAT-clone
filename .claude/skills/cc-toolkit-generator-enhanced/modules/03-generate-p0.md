# Module: Generate P0

Phase 3 of the CC-Toolkit-Generator Enhanced pipeline.
Generates all mandatory P0 toolkit items -- the core instruments that every
project receives regardless of pipeline type, score, or user selection.
Also generates conditional P0 items driven by project characteristics.

---

## Input

| Parameter | Type | Source |
|-----------|------|--------|
| `ipm` | IPM object | Output of Module 01 (Detect & Parse) |
| `instrument_map` | InstrumentMap object | Output of Module 02 (Analyze & Map) |

From the IPM this module uses:
- `pipeline_type` -- determines CLAUDE.md strategy and template selection
- `detected_docs` -- content sources for generated files
- `project_characteristics` -- conditional P0 triggers

From the Instrument Map this module uses:
- `p0_mandatory` -- confirmation of required items (hardcoded below)
- `p0_conditional` -- items gated by characteristic flags

---

## Process

> **ANTI-COMPRESSION DIRECTIVE:** When generating files from templates in this module,
> COPY the FULL text of each template. Do NOT summarize, compress, or "interpret" templates.
> Every section, every placeholder, every comment must be preserved verbatim.
> AI systems routinely compress 211-line templates to 60 lines — this is a CRITICAL defect.
> Validate: generated file line count must be >= 80% of template line count.

### P0 Mandatory Items (always generated)

The following 16 items are generated for every project, regardless of pipeline
type or user mode.

---

#### Item 1: CLAUDE.md

**Template:** `view() references/claude-md-strategy.md`
> CRITICAL: COPY the full template. Do NOT compress or summarize.

The project's root context file. Generation strategy differs by pipeline:

**SPARC pipeline top sections:**
```markdown
# Project: [Name from PRD.md]

## Overview
[From PRD.md Executive Summary]

## Problem & Solution
[From Solution_Strategy.md -- 2-3 sentences]

## Architecture
[From Architecture.md -- monorepo structure, tech stack]

## Tech Stack
[From Architecture.md decisions table]

## Key Algorithms
[From Pseudocode.md -- top 3-5 function signatures]

## Security Rules
[From Specification.md security requirements]
[IF has_external_apis: client-side encryption mandatory]
```

**idea2prd pipeline top sections:**
```markdown
# Project: [Name from .ai-context/README.md]

## Overview
[From .ai-context/README.md]

## Architecture
[From .ai-context/architecture-summary.md]

## Key Decisions
[From .ai-context/key-decisions.md -- top 5 ADRs]

## Domain Model
[From .ai-context/bounded-contexts.md]

## Glossary
[From .ai-context/domain-glossary.md -- key terms]

## Tech Stack
[From ADRs + architecture-summary]

## Coding Standards
[From .ai-context/coding-standards.md]

## Quality Gates
[From .ai-context/fitness-rules.md]
```

**Common sections (both pipelines) -- always appended after pipeline-specific top:**
```markdown
## Parallel Execution Strategy
## Swarm Agents
## Git Workflow
## Available Agents
## Available Skills
## Quick Commands
## Development Insights (knowledge base)
## Feature Development Lifecycle
## Enterprise Feature Lifecycle (IF DDD detected)
## Feature Roadmap
## Implementation Plans
## Automation Commands
## Resources
```

**Source priority rules:**

| CLAUDE.md Section | Priority 1 | Priority 2 | Priority 3 |
|-------------------|------------|------------|------------|
| Overview | .ai-context/README | PRD Executive Summary | Final_Summary |
| Architecture | .ai-context/architecture | Architecture.md | -- |
| Tech Stack | Architecture.md | ADRs | -- |
| Key Decisions | .ai-context/key-decisions | ADRs | Solution_Strategy |
| Security | Specification.md | Fitness Functions | Architecture.md |

**Context budget:** Target 4,000 tokens, maximum 6,000 tokens.
If content exceeds max, prioritize: Overview > Architecture > Security >
Lifecycle sections > Generated lists.

**Output path:** `CLAUDE.md` (project root)

---

#### Item 2: security.md rule

**Source:** Specification.md NFRs (SPARC) or ADRs + Fitness Functions (idea2prd)

Generate `.claude/rules/security.md` containing:
- Security requirements extracted from source docs
- Input validation rules
- Authentication/authorization requirements
- Encryption requirements (especially if `has_external_apis`)
- Dependency security scanning rules

**Output path:** `.claude/rules/security.md`

---

#### Item 3: coding-style.md rule

**Source:** Architecture.md tech stack (SPARC) or DDD Tactical + ADRs (idea2prd)

Generate `.claude/rules/coding-style.md` containing:
- Language and framework conventions from the tech stack
- Naming conventions (files, variables, functions, classes)
- Import ordering rules
- Code organization patterns
- IF idea2prd: DDD tactical patterns (aggregate rules, entity identity, VO immutability)

**Known Gotchas section (always include):**

Add a `## Known Gotchas` section to coding-style.md with language/framework-specific
pitfalls extracted from harvest insights. Include at minimum:

```markdown
## Known Gotchas

### TypeScript / JavaScript
- `\w` in regex does NOT match Cyrillic or other non-Latin characters.
  Use `\p{L}` with `/u` flag or explicit character classes for Unicode text.
- Direct type casting `req as CustomType` fails with TS2352. Use double-cast
  via `unknown`: `(req as unknown as CustomType)`. Better: use generic route handlers.
- Jest `coverageThreshold` (singular) silently fails if spelled `coverageThresholds` (plural).
  Per-directory thresholds require a `global` key. ts-jest needs `ts-node` as peer dependency.
- `jest.fn(async () => value)` doesn't satisfy `jest.Mocked<T>` in strict mode.
  Use `jest.fn().mockResolvedValue(value)` or `jest.fn().mockImplementation(...)`.
- Opossum `CircuitBreaker.fire()` returns `Promise<unknown>`, requires explicit cast.
  Both `@types/opossum` and `opossum` packages are needed.
- Socket.io `Server` has no `.toRoom()` method. Wrap it:
  `{ toRoom: (room) => io.to(room) }` for hexagonal architecture ports.

### Infrastructure
- Services with circuit breakers/rate limiters MUST be singletons.
  Per-request instances bypass protection (breaker never accumulates failures).
- `SET LOCAL` in PostgreSQL only affects the current transaction on the current connection.
  Use parameterized `set_config()` instead of string interpolation.
```

Adapt gotchas to the specific tech stack detected in IPM. Remove irrelevant entries
(e.g., no TypeScript gotchas for Python projects). Add stack-specific gotchas from
`view() references/security-patterns-library.md` if applicable.

**Output path:** `.claude/rules/coding-style.md`

---

#### Item 4: /start command

**Template:** `view() references/templates/start-command.md`
> CRITICAL: COPY the full template. Do NOT compress or summarize.

Generate `.claude/commands/start.md` -- the full project bootstrap command.

Key generation steps:
1. Read the start-command template for structure
2. Fill `{{DOCS_TO_READ}}` with actual doc paths from `ipm.detected_docs`
3. Fill `{{FOR_EACH_PACKAGE}}` with one Task block per `ipm.project_characteristics.monorepo_packages`
4. Set `{{IF_DATABASE}}` / `{{IF_NO_DATABASE}}` based on `ipm.project_characteristics.has_database`
5. Set `{{MIGRATION_COMMAND}}` based on `ipm.project_characteristics.orm_name`:
   - prisma: `npx prisma migrate dev --name init`
   - typeorm: `npx typeorm migration:run`
   - drizzle: `npx drizzle-kit push`
   - knex: `npx knex migrate:latest`
   - raw: `psql -f init.sql`
6. Set `{{SEED_COMMAND}}` similarly
7. Fill `{{DOCKER_SERVICES}}` from `ipm.project_characteristics.docker_services`
8. Fill `{{HEALTH_CHECK_COMMAND}}` from Architecture.md API endpoints

**Critical rule:** /start MUST reference actual docs in `docs/`, never hallucinate
code from memory. Every Phase 2 Task includes explicit doc references.

**Output path:** `.claude/commands/start.md`

---

#### Item 5: /myinsights command

**Template:** `view() references/templates/insights-system.md` (Section 1)
> CRITICAL: COPY the full template. Do NOT compress or summarize.

Generate `.claude/commands/myinsights.md` -- the insight capture and management
command with:
- Duplicate detection (Step 0) via index grep
- Information collection (Step 1) with structured fields
- Individual detail file creation (Step 2) as `myinsights/INS-NNN-slug.md`
- Index update (Step 3) in `myinsights/1nsights.md`
- Auto-numbering (Step 4) from highest existing INS-NNN
- Subcommands: archive, status
- Hit counter for tracking insight reuse value

**Output path:** `.claude/commands/myinsights.md`

---

#### Item 6: /feature command

**Template:** `view() references/templates/feature-lifecycle.md` (Section 2)
> CRITICAL: COPY the full template. Do NOT compress or summarize.

Generate `.claude/commands/feature.md` -- the 4-phase feature lifecycle command:

```
Phase 0: PRE-FLIGHT CHECK
  Verify all required skills exist in .claude/skills/
  ABORT if sparc-prd-mini, requirements-validator, or brutal-honesty-review missing
  WARN if explore, goap-research, or problem-solver-enhanced missing

Phase 1: PLAN (sparc-prd-mini)
  Create docs/features/<feature-name>/sparc/
  Run sparc-prd-mini Gate -> assess clarity
  Generate 9 SPARC documents
  Commit: docs(feature): SPARC planning for <feature-name>

Phase 2: VALIDATE (requirements-validator, swarm)
  5 parallel validation agents
  Iterative loop (max 3 iterations)
  Minimum score: 70/100, no BLOCKED items
  Save validation-report.md
  Commit: docs(feature): validation complete for <feature-name>

Phase 3: IMPLEMENT (swarm + parallel tasks)
  Read validated SPARC docs as source of truth
  Use @planner, @architect, implementation agents
  Modular design for reuse
  Commit per logical unit: feat(<feature-name>): <what>

Phase 4: REVIEW (brutal-honesty-review, swarm)
  5 parallel review agents (code-quality, architecture, security, performance, testing)
  Fix all critical/major issues
  Save review-report.md
  Commit: docs(feature): review complete for <feature-name>
```

**Output path:** `.claude/commands/feature.md`

---

#### Item 7: git-workflow.md rule

Generate `.claude/rules/git-workflow.md` with semantic commit conventions:

```markdown
# Git Workflow

## Commit Format
type(scope): description

## Types
- feat: New feature
- fix: Bug fix
- refactor: Code restructuring (no behavior change)
- test: Adding/updating tests
- docs: Documentation changes
- chore: Build, CI, config changes

## Rules
- Commit after each logical change
- Never combine unrelated changes in one commit
- Use scope from monorepo package names where applicable
- Write imperative mood descriptions ("add", not "added")
```

**Output path:** `.claude/rules/git-workflow.md`

---

#### Item 8: insights-capture.md rule

**Template:** `view() references/templates/insights-system.md` (Section 2)
> CRITICAL: COPY the full template. Do NOT compress or summarize.

Generate `.claude/rules/insights-capture.md` with:
- Error-First Lookup protocol (grep index BEFORE debugging)
- When to suggest capturing an insight (5 trigger conditions)
- How to suggest (prompt format)
- When NOT to suggest (4 exclusion conditions)
- Lifecycle awareness (Active / Workaround / Obsolete status handling)

**Output path:** `.claude/rules/insights-capture.md`

---

#### Item 9: feature-lifecycle.md rule

**Template:** `view() references/templates/feature-lifecycle.md` (Section 3)
> CRITICAL: COPY the full template. Do NOT compress or summarize.

Generate `.claude/rules/feature-lifecycle.md` with:
- Protocol definition (4-phase lifecycle)
- Planning rules (SPARC docs mandatory, Gate assessment, MANUAL/AUTO mode)
- Validation rules (swarm, min score 70, max 3 iterations)
- Implementation rules (read docs not hallucinate, modular, parallel Tasks)
- Review rules (brutal-honesty, fix criticals, benchmark)
- Feature directory structure template
- Skip rules table (when to skip phases)

**Output path:** `.claude/rules/feature-lifecycle.md`

---

#### Item 10: settings.json hooks

**Template:** `view() references/templates/insights-system.md` (Section 3 -- Stop hook)
> CRITICAL: COPY the full template. Do NOT compress or summarize.

Generate `.claude/settings.json` with hook configuration:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "command": "<insights auto-commit hook -- see template>"
      },
      {
        "matcher": "",
        "command": "<feature-roadmap auto-commit hook>"
      },
      {
        "matcher": "",
        "command": "<plans auto-commit hook>"
      }
    ],
    "SessionStart": [
      {
        "matcher": "",
        "command": "python3 .claude/hooks/feature-context.py"
      }
    ]
  }
}
```

The Stop hooks auto-commit changes to:
1. `myinsights/` -- knowledge base entries (insights-system.md template)
2. `.claude/feature-roadmap.json` -- feature status updates
3. `docs/plans/` -- implementation plans

The SessionStart hook injects current feature context and sprint progress.

**Output path:** `.claude/settings.json`

---

#### Items 11-16: Six Lifecycle Skills (copy + path rewrite)

**Template:** `view() references/templates/feature-lifecycle.md` (Section 1 -- Skill Copying Protocol)

Copy these 6 skills from the user's skill set into `.claude/skills/`:

| # | Skill | Source Path | Target Path |
|---|-------|-------------|-------------|
| 11 | sparc-prd-mini | `/mnt/skills/user/sparc-prd-mini/` | `.claude/skills/sparc-prd-mini/` |
| 12 | explore | `/mnt/skills/user/explore/` | `.claude/skills/explore/` |
| 13 | goap-research | `/mnt/skills/user/goap-research/` | `.claude/skills/goap-research/` |
| 14 | problem-solver-enhanced | `/mnt/skills/user/problem-solver-enhanced/` | `.claude/skills/problem-solver-enhanced/` |
| 15 | requirements-validator | `/mnt/skills/user/requirements-validator/` | `.claude/skills/requirements-validator/` |
| 16 | brutal-honesty-review | `/mnt/skills/user/brutal-honesty-review/` | `.claude/skills/brutal-honesty-review/` |

**Copy protocol:**
1. Copy the **entire directory** for each skill (SKILL.md + references/ + scripts/ + templates/)
2. In the replicate pipeline context, source paths map from `/mnt/skills/user/[name]/` to `.claude/skills/[name]/` (skills are already local)

**Path rewrite required for sparc-prd-mini/SKILL.md:**

After copying, rewrite ALL `view()` paths in `sparc-prd-mini/SKILL.md`:

External skill paths (3 rewrites):
```
/mnt/skills/user/explore/SKILL.md                    -> .claude/skills/explore/SKILL.md
/mnt/skills/user/goap-research/SKILL.md               -> .claude/skills/goap-research/SKILL.md
/mnt/skills/user/problem-solver-enhanced/SKILL.md     -> .claude/skills/problem-solver-enhanced/SKILL.md
```

Internal template/reference paths (3 rewrites):
```
templates/prd.md                  -> .claude/skills/sparc-prd-mini/templates/prd.md
references/sparc-methodology.md   -> .claude/skills/sparc-prd-mini/references/sparc-methodology.md
templates/CLAUDE.md               -> .claude/skills/sparc-prd-mini/templates/CLAUDE.md
```

Also update informational references in sparc-prd-mini/SKILL.md (non-executable
but avoids confusion):
```
Lines 31-33: External Dependencies table -- update paths to .claude/skills/
Lines 951-953: Dependency Version Note -- update paths to .claude/skills/
```

**Note on `goap-research` name mapping:** The skill name `goap-research` in the
lifecycle context maps to `goap-research-ed25519` in this repository. Ensure the
correct directory name is used when copying.

**Output paths:** `.claude/skills/sparc-prd-mini/`, `.claude/skills/explore/`,
`.claude/skills/goap-research/`, `.claude/skills/problem-solver-enhanced/`,
`.claude/skills/requirements-validator/`, `.claude/skills/brutal-honesty-review/`

---

### P0 Conditional Items (generated if flags match)

#### Conditional A: secrets-management.md + security-patterns/

**Condition:** `ipm.project_characteristics.has_external_apis == true`

Generate `.claude/rules/secrets-management.md`:
- API key storage rules (never in code, use env vars)
- Client-side encryption requirements
- Secret rotation policies
- .env file management rules

Generate `.claude/skills/security-patterns/`:
- SKILL.md with encryption patterns
- API key validation patterns
- Secure storage templates

**Output paths:** `.claude/rules/secrets-management.md`, `.claude/skills/security-patterns/`

---

#### Conditional B: domain-model.md rule

**Condition:** DDD Strategic docs detected (`ipm.detected_docs.idea2prd.ddd_strategic` non-empty)

Generate `.claude/rules/domain-model.md`:
- Bounded Context boundaries and responsibilities
- Ubiquitous Language enforcement
- Aggregate invariants
- Context mapping relationships (upstream/downstream)

**Source:** `docs/ddd/strategic/bounded-contexts.md`, `docs/ddd/strategic/context-map.md`,
`.ai-context/bounded-contexts.md`

**Output path:** `.claude/rules/domain-model.md`

---

#### Conditional C: /start database extensions

**Condition:** `ipm.project_characteristics.has_database == true`

Extend the /start command (Item 4) with:
- Database migration step in Phase 3
- Database seed step in Phase 3
- `--skip-seed` flag
- ORM-specific commands based on `ipm.project_characteristics.orm_name`

This is not a separate file but a conditional section within `/start`.

---

### Additional P0 Outputs

#### docs/features/ directory

Create the empty directory `docs/features/` to establish the feature
documentation structure. This directory is where `/feature` command outputs
will be stored.

**Output path:** `docs/features/` (directory)

---

#### DEVELOPMENT_GUIDE.md

Generate the development guide with:
- Full lifecycle instructions (setup -> develop -> test -> deploy)
- Command reference table
- Agent reference table
- Skill reference table
- Troubleshooting section
- Project-specific setup instructions

**Context budget:** Target 1,000 tokens, maximum 2,000 tokens.

**Output path:** `DEVELOPMENT_GUIDE.md` (project root)

---

### Step-by-step Generation Order

Generate items in this order to resolve dependencies:

```
1. Items 11-16: Copy lifecycle skills FIRST (other items reference them)
2. Item 1: CLAUDE.md (references agents/skills/commands lists)
3. Items 2-3: security.md, coding-style.md (rules, no deps)
4. Item 7: git-workflow.md (rule, no deps)
5. Item 8: insights-capture.md (rule, no deps)
6. Item 9: feature-lifecycle.md (rule, references skills from step 1)
7. Item 4: /start command (references docs, rules, skills)
8. Item 5: /myinsights command (references insights-capture rule)
9. Item 6: /feature command (references lifecycle skills, rules)
10. Item 10: settings.json (references all hooks)
11. Conditional A-C: based on project characteristics
12. docs/features/ directory
13. DEVELOPMENT_GUIDE.md (references everything above)
```

### MANUAL Mode Checkpoint

In MANUAL mode, present P0 generation results:

```
================================================================
CHECKPOINT 3: P0 Review
================================================================

P0 Mandatory Generated:
  [x] CLAUDE.md                        4.1 KB
  [x] .claude/rules/security.md       1.8 KB
  [x] .claude/rules/coding-style.md   2.1 KB
  [x] .claude/commands/start.md       3.2 KB
  [x] .claude/commands/myinsights.md  2.8 KB
  [x] .claude/commands/feature.md     3.5 KB
  [x] .claude/rules/git-workflow.md   0.8 KB
  [x] .claude/rules/insights-capture.md  1.9 KB
  [x] .claude/rules/feature-lifecycle.md 2.4 KB
  [x] .claude/settings.json           1.2 KB
  [x] 6 lifecycle skills copied       (sparc-prd-mini, explore,
       goap-research, problem-solver-enhanced,
       requirements-validator, brutal-honesty-review)

P0 Conditional Generated:
  [x] .claude/rules/secrets-management.md    (has_external_apis)
  [x] .claude/skills/security-patterns/      (has_external_apis)
  [x] .claude/rules/domain-model.md          (DDD Strategic detected)

Additional:
  [x] docs/features/ directory created
  [x] DEVELOPMENT_GUIDE.md                  1.1 KB

Total P0: 16 mandatory + 3 conditional = 19 items
Combined size: ~26 KB

Commands: "ok" to proceed to P1 | "modify [file]" | "show [file]"
================================================================
```

---

## Output

| Field | Type | Description |
|-------|------|-------------|
| `generated_files` | list of objects | Every file created, with absolute path, size, and category |

Each entry in `generated_files`:
```
{
  path: string,         # e.g. ".claude/rules/security.md"
  category: string,     # "rule" | "command" | "skill" | "config" | "doc" | "directory"
  size_bytes: int,
  is_conditional: bool,
  condition: string | null   # e.g. "has_external_apis"
}
```

The generated files list is consumed by:
- **Module 04 (Generate P1)** -- to avoid overwriting P0 files
- **Module 06 (Package & Deliver)** -- for the master validation checklist
- **CLAUDE.md** -- to populate Available Agents/Skills/Commands sections

---

## Quality Gate

| Check | Condition | Action on Failure |
|-------|-----------|-------------------|
| All 16 P0 mandatory items exist | Every item from the mandatory list has a file on disk | Re-generate missing items. Do not proceed to P1 with incomplete P0. |
| 6 lifecycle skills copied | All 6 skill directories exist under `.claude/skills/` with SKILL.md present | Re-copy missing skills. If source unavailable, log critical warning. |
| Path rewrite verified | `sparc-prd-mini/SKILL.md` contains `.claude/skills/` paths, not `/mnt/skills/user/` | Re-run path rewrite on sparc-prd-mini. |
| CLAUDE.md within budget | CLAUDE.md is under 6,000 tokens | Trim lower-priority sections (Generated lists, Resources). |
| Conditional items match flags | Conditional P0 items generated only when matching flag is true | Remove incorrectly generated conditional items. |
| settings.json valid JSON | `.claude/settings.json` parses as valid JSON | Fix JSON syntax. |
| docs/features/ exists | Directory created | Create the directory. |
| No P0 item references missing doc | Every P0 item that reads from `ipm.detected_docs` has valid source | Generate with degraded content, add warning comment. |

---

## Dependencies

This module reads the following reference/template files during execution:

| Reference | Purpose | Used By Item |
|-----------|---------|--------------|
| `view() references/claude-md-strategy.md` | CLAUDE.md generation strategy (pipeline-specific sections, common sections, source priority, budget) | Item 1: CLAUDE.md |
| `view() references/templates/start-command.md` | /start command template with placeholder fill instructions | Item 4: /start |
| `view() references/templates/feature-lifecycle.md` | Skill copying protocol (Sec 1), /feature command template (Sec 2), feature-lifecycle rule template (Sec 3), CLAUDE.md integration (Sec 4) | Items 6, 9, 11-16 |
| `view() references/templates/insights-system.md` | /myinsights command template (Sec 1), insights-capture rule template (Sec 2), Stop hook template (Sec 3), CLAUDE.md integration (Sec 4) | Items 5, 8, 10 |

These files are part of the cc-toolkit-generator-enhanced skill at:
`.claude/skills/cc-toolkit-generator-enhanced/references/`

---

## Reusability

The P0 generation pattern can be templated for **any toolkit with mandatory core
items**:

1. **Define the mandatory item list** -- items that are always generated
2. **Define conditional items** -- items gated by project characteristic flags
3. **Define generation order** -- resolve dependencies between items
4. **Define templates** -- reference files with placeholder fill instructions
5. **Define quality gate** -- checks that all mandatory items exist and are valid

This pattern is independent of the specific items being generated. To create a
different toolkit (e.g., a testing toolkit, a documentation toolkit, a CI/CD
toolkit):
- Replace the 16 mandatory items with domain-specific core items
- Replace conditional flags with domain-specific detection flags
- Keep the generation order framework (copy dependencies first, then config,
  then commands, then meta-files)
- Keep the quality gate structure (existence checks + content validation)

The skill copying protocol (Items 11-16) is also independently reusable for any
scenario where skills need to be redistributed with path rewrites. The protocol
handles:
- Full directory copy (SKILL.md + references/ + templates/ + scripts/)
- view() path rewriting for cross-skill references
- Informational reference updates for developer clarity
