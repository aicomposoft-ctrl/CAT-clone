# Module: Package & Deliver

Phase 6 of the CC-Toolkit-Generator-Enhanced pipeline. Final validation, integrity checking,
and delivery of the complete toolkit package. Runs the Master Validation Checklist to ensure
100% pass rate on P0 mandatory items and verifies all placeholders are substituted before
declaring the toolkit ready for use.

## Input

- **All generated files from Phases 3-5:**
  - Phase 3 (P0): CLAUDE.md, DEVELOPMENT_GUIDE.md, settings.json, 6 lifecycle skills,
    /start, /myinsights, /feature commands, git-workflow, insights-capture, feature-lifecycle rules,
    security.md, coding-style.md rules, docs/features/ directory
  - Phase 4 (P1): planner/code-reviewer/architect agents, project-context/coding-standards/testing-patterns skills,
    /plan, /test, /deploy commands, testing.md rule.
    Conditional: /feature-ent, feature-lifecycle-ent rule, idea2prd-manual + goap-research-ed25519 skills,
    /next + feature-navigator + roadmap.json + feature-context.py,
    /go, /run, /docs commands
  - Phase 5 (P2-P3): tdd-guide agent, merged settings.json, /review command.
    Conditional: ddd-validator agent, aggregate-patterns + event-handlers skills, /validate-ddd,
    hook scripts, .mcp.json
- **Internal Project Model (IPM)** — for placeholder substitution verification and conditional validation
- **Instrument Map** — for verifying all scored items above threshold were generated

## Process

### Step 1: Run Master Validation Checklist

Execute every item from the SKILL.md Master Validation Checklist. Each item must be
verified by checking the actual generated file exists and contains the required content.

#### 1a. P0 Mandatory Checks

```
CHECK 1: CLAUDE.md
  - File exists at project root
  - Generated per references/claude-md-strategy.md
  - Contains ALL required sections:
    [ ] Parallel Execution Strategy
    [ ] Swarm Agents
    [ ] Development Insights reference
    [ ] Feature Lifecycle (/feature summary)
    [ ] Feature Roadmap (link to roadmap.json)
    [ ] Plans (/plan summary)
    [ ] Automation Commands (/go, /run, /docs)
    [ ] Available Agents table
    [ ] Available Skills table
    [ ] Available Commands table
    [ ] Git Workflow conventions
  - Total size within budget: target 4k, max 6k tokens

CHECK 2: DEVELOPMENT_GUIDE.md
  - File exists at project root
  - Contains full lifecycle instructions
  - References all generated commands
  - Includes development workflow section
  - Includes feature workflow section (if feature suggestions generated)
  - Includes autonomous development section (if automation commands generated)

CHECK 3: /start command
  - File exists at .claude/commands/start.md
  - Contains complete project generation instructions
  - Includes all packages from IPM
  - Uses Task tool for parallelism where appropriate
  - Includes Docker health check verification
  - References actual SPARC/idea2prd docs (not hallucinated paths)
  - IF has_database: includes DB migration + seed steps

CHECK 4: /myinsights command
  - File exists at .claude/commands/myinsights.md
  - Supports duplicate detection
  - Supports subcommands (list, search, add)
  - Uses index + detail architecture (myinsights/1nsights.md + myinsights/details/)

CHECK 5: insights-capture.md rule
  - File exists at .claude/rules/insights-capture.md
  - Includes auto-grep pattern for insight detection
  - References myinsights/ directory structure

CHECK 6: /feature command
  - File exists at .claude/commands/feature.md
  - Contains 4-phase lifecycle: plan -> validate -> implement -> review
  - References sparc-prd-mini, requirements-validator, brutal-honesty-review skills

CHECK 7: feature-lifecycle.md rule
  - File exists at .claude/rules/feature-lifecycle.md
  - Documents the 4-phase lifecycle protocol
  - Includes phase skip guidance

CHECK 8: 6 lifecycle skills
  - All 6 skills copied to .claude/skills/:
    [ ] sparc-prd-mini/SKILL.md
    [ ] explore/SKILL.md
    [ ] goap-research-ed25519/SKILL.md (maps to goap-research in skill name)
    [ ] problem-solver-enhanced/SKILL.md
    [ ] requirements-validator/SKILL.md
    [ ] brutal-honesty-review/SKILL.md
  - Path rewrite applied: /mnt/skills/user/ -> .claude/skills/
  - Each skill directory contains SKILL.md + references/ (if applicable)

CHECK 9: git-workflow.md rule
  - File exists at .claude/rules/git-workflow.md
  - Contains semantic commit conventions
  - Includes commit format specification

CHECK 10: settings.json
  - File exists at .claude/settings.json
  - Valid JSON (parseable)
  - Contains Stop hooks:
    [ ] Insights auto-commit hook
    [ ] Roadmap auto-commit hook (if feature suggestions generated)
    [ ] Plans auto-commit hook
  - Contains SessionStart hook:
    [ ] feature-context.py hook (if feature suggestions generated)

CHECK 11: docs/features/ directory
  - Directory exists at docs/features/
  - Ready for feature documentation output
```

#### 1b. P0 Conditional Checks

```
CHECK 12: secrets-management.md + security-patterns/ (IF has_external_apis)
  - IF has_external_apis == true:
    [ ] .claude/rules/secrets-management.md exists
    [ ] .claude/skills/security-patterns/SKILL.md exists
  - IF has_external_apis == false:
    [ ] Neither file exists (no false positives)

CHECK 13: domain-model.md rule (IF DDD Strategic docs)
  - IF has_ddd == true:
    [ ] .claude/rules/domain-model.md exists
    [ ] Contains bounded context rules, aggregate rules, entity/VO/event rules
  - IF has_ddd == false:
    [ ] File does not exist

CHECK 14: /start DB migration (IF has_database)
  - IF has_database == true:
    [ ] /start command includes database migration step
    [ ] /start command includes seed data step
  - IF has_database == false:
    [ ] No DB migration references in /start
```

#### 1c. P1 Enterprise Checks (IF DDD)

```
CHECK 15: Enterprise lifecycle (IF has_ddd)
  - IF has_ddd == true:
    [ ] .claude/commands/feature-ent.md exists with 4 phases
    [ ] .claude/rules/feature-lifecycle-ent.md exists with decision matrix
    [ ] .claude/skills/idea2prd-manual/ copied with path rewrites
    [ ] .claude/skills/goap-research-ed25519/ copied (enterprise copy)
    [ ] CLAUDE.md includes Enterprise Feature Lifecycle section
    [ ] Path rewrites verified in idea2prd-manual/SKILL.md:
        - /mnt/skills/user/explore/ -> .claude/skills/explore/
        - /mnt/skills/user/goap-research-ed25519/ -> .claude/skills/goap-research-ed25519/
        - /mnt/skills/user/problem-solver-enhanced/ -> .claude/skills/problem-solver-enhanced/
  - IF has_ddd == false:
    [ ] None of these files exist
```

#### 1d. P1 Feature Suggestions Checks

```
CHECK 16: Feature suggestions system
  [ ] .claude/feature-roadmap.json exists and is valid JSON
  [ ] feature-roadmap.json contains >= 5 features
  [ ] Feature statuses are valid: done|in_progress|next|planned|blocked
  [ ] .claude/hooks/feature-context.py exists and is valid Python syntax
  [ ] .claude/commands/next.md exists with 3 subcommands (default, update, feature-id)
  [ ] .claude/skills/feature-navigator/SKILL.md exists with priority rules
  [ ] settings.json SessionStart hook references feature-context.py
  [ ] settings.json Stop hook includes roadmap auto-commit
```

#### 1e. P1 Automation Checks

```
CHECK 17: Automation commands
  [ ] .claude/commands/go.md exists with complexity scoring matrix
  [ ] .claude/commands/run.md exists with MVP/all scope handling
  [ ] .claude/commands/docs.md exists with bilingual generation
  [ ] CLAUDE.md includes Automation Commands section
  [ ] DEVELOPMENT_GUIDE.md includes command hierarchy diagram
  [ ] /go references /plan, /feature correctly
  [ ] /go references /feature-ent ONLY if has_ddd (conditional reference)
  [ ] /run references /start, /next, /go correctly
  [ ] /docs references docs/, myinsights/, source code as inputs
```

#### 1f. Pipeline-Specific Checks (IF applicable)

```
CHECK 18: DDD pipeline artifacts (IF has_ddd)
  [ ] Bounded Contexts mapped to agent scopes (domain-expert, architect)
  [ ] Aggregates mapped to validation patterns (ddd-validator, aggregate-patterns)
  [ ] ADR decisions mapped to rules (coding-style, architect agent)
  [ ] Fitness Functions mapped to hooks (validate-aggregate-size, check-ddd-patterns)
  [ ] Gherkin features mapped to test commands (/test, testing-patterns)
  [ ] .ai-context/ integrated into CLAUDE.md (if present)

CHECK 19: P2 DDD items (IF has_ddd AND P2 generated)
  [ ] .claude/agents/ddd-validator.md exists
  [ ] .claude/skills/aggregate-patterns/SKILL.md exists
  [ ] .claude/skills/event-handlers/SKILL.md exists
  [ ] .claude/commands/validate-ddd.md exists
  [ ] .claude/hooks/validate-aggregate-size.sh exists and is executable
  [ ] .claude/hooks/check-ddd-patterns.sh exists and is executable

CHECK 20: P3 MCP (IF external integrations detected)
  [ ] .mcp.json exists in project root and is valid JSON
  [ ] No hardcoded secrets (all env vars use ${VAR_NAME} syntax)
  [ ] Enabled servers count < 10
  [ ] INSTALL.md documents all required env vars from .mcp.json
```

### Step 1.5: Automated File-Existence Validation

Before proceeding to placeholder scanning, run an automated file-existence check
against the expected output manifest. This catches the most common generation failure:
files that should exist but were silently omitted (often due to skipping module files).

```
AUTOMATED FILE CHECK PROTOCOL:

Step 1: Build expected file list from Instrument Map tiers:
  - P0 mandatory: 16 items (always expected)
  - P0 conditional: check IPM flags before expecting
  - P1 core: 10 items (if P1 was executed)
  - P1 conditional: check IPM flags
  - P2/P3: check flags and execution status

Step 2: For each expected file, run existence check:
  for file in expected_files:
    if not exists(file.path):
      log CRITICAL: "Missing file: {file.path} (expected from {file.phase})"
      missing_count++

Step 3: For each expected directory, verify SKILL.md exists inside:
  for skill_dir in expected_skill_directories:
    if not exists(skill_dir + "/SKILL.md"):
      log CRITICAL: "Missing SKILL.md in {skill_dir}"
      missing_count++

Step 4: Verify file sizes (anti-compression check):
  for file in generated_files:
    if file.size_bytes < 100:
      log WARNING: "Suspiciously small file: {file.path} ({file.size_bytes} bytes)"
      log WARNING: "Possible template compression — verify content completeness"

Step 5: Report
  if missing_count > 0:
    CRITICAL FAILURE: {missing_count} expected files are missing.
    List each missing file with its expected source phase/module.
    Attempt auto-fix by re-reading the relevant module and regenerating.
  else:
    PASS: All {total_count} expected files exist.
```

This step was added based on a real-project insight where skipping `modules/04-generate-p1.md`
caused 10+ P1 artifacts to be silently omitted without any error in the final report.

### Step 2: Verify Placeholder Substitution

Scan ALL generated files for unsubstituted placeholders:

```
Scan targets:
  - All files in .claude/ recursively (agents/, skills/, commands/, rules/, hooks/)
  - CLAUDE.md, DEVELOPMENT_GUIDE.md, INSTALL.md at project root
  - .mcp.json at project root (if exists)
  - .claude/feature-roadmap.json (if exists)

Scan patterns (all are CRITICAL if found):

  Pattern: {{[A-Z_]+}}
  Examples: {{PROJECT_NAME}}, {{LANGUAGE}}, {{MAX_ENTITIES}}, {{TECH_KEYWORDS}}
  Action: Look up value in IPM and substitute

  Pattern: {{IF_DDD}}, {{IF_EXTERNAL_APIS}}, {{IF_EXTERNAL_INTEGRATIONS}}
  Action: Remove conditional marker and enclosed block if condition is false,
          keep enclosed content (remove markers only) if condition is true

  Pattern: /mnt/skills/user/
  Action: Replace with .claude/skills/ (path rewrite was missed)

  Pattern: /mnt/user-data/uploads/
  Action: Replace with docs/ (path rewrite was missed)

  Pattern: /output/
  Action: Replace with docs/ or project root (path rewrite was missed)

Process:
  1. Glob all target files
  2. For each file, search for ALL scan patterns
  3. Collect all findings with file path, line number, and pattern
  4. Report findings as CRITICAL FAILURE if any found
  5. Attempt auto-fix for each finding:
     - {{PLACEHOLDER}} -> look up in IPM, substitute
     - {{IF_*}} -> evaluate condition, resolve block
     - /mnt/* -> apply path rewrite
  6. Re-scan after auto-fix to verify zero remaining

Expected result: ZERO unsubstituted placeholders across all generated files.
```

### Step 3: Run Integrity Checks

```
INTEGRITY CHECK 1: JSON Validity
  Parse each JSON file and verify:
  - .claude/settings.json -> must parse without errors
  - .claude/feature-roadmap.json -> must parse without errors (if exists)
  - .mcp.json -> must parse without errors (if exists)
  Common issues to auto-fix: trailing commas, missing quotes, unescaped characters

INTEGRITY CHECK 2: File Cross-References
  For every generated file, verify that all references resolve:
  - Agent frontmatter skills: field -> each skill name maps to .claude/skills/{name}/SKILL.md
  - Command text references to other commands -> .claude/commands/{name}.md exists
  - Rule text references to commands -> .claude/commands/{name}.md exists
  - settings.json hook commands -> referenced scripts exist at specified paths
  - CLAUDE.md Available Agents table -> each agent file exists
  - CLAUDE.md Available Skills table -> each skill directory exists
  - CLAUDE.md Available Commands table -> each command file exists
  Failure here means a file references something that was not generated.

INTEGRITY CHECK 3: Directory Structure
  Verify the complete directory tree exists:
  - .claude/agents/ -> contains expected agent files
  - .claude/skills/ -> contains expected skill directories, each with SKILL.md
  - .claude/commands/ -> contains expected command files
  - .claude/rules/ -> contains expected rule files
  - .claude/hooks/ -> exists if any hooks were generated
  - docs/features/ -> exists
  - docs/plans/ -> exists (if /plan command was generated)

INTEGRITY CHECK 4: Skill Completeness
  For each skill directory in .claude/skills/:
  - SKILL.md exists and is non-empty (minimum 100 bytes)
  - If the source skill had a references/ subdirectory, it was copied
  - If the source skill had scripts/, they were copied
  - SKILL.md frontmatter contains name and description fields

INTEGRITY CHECK 5: Context Budget
  Measure approximate token count for each component:

  | Component | Target | Max | Actual | Status |
  |-----------|--------|-----|--------|--------|
  | CLAUDE.md | 4k | 6k | [measure] | [OK/WARN/FAIL] |
  | /start command | 2k | 4k | [measure] | [OK/WARN/FAIL] |
  | /myinsights + /feature + /plan | 3k combined | 5.5k | [measure] | [OK/WARN/FAIL] |
  | Domain rules (all .claude/rules/) | 1.5k | 2.5k | [measure] | [OK/WARN/FAIL] |
  | Generated skills + agents | 3.5k | 5k | [measure] | [OK/WARN/FAIL] |
  | Copied lifecycle skills | 0 (on-demand) | 0 | [verify] | [OK/WARN/FAIL] |
  | Commands + hooks | 1k | 2k | [measure] | [OK/WARN/FAIL] |
  | DEVELOPMENT_GUIDE | 1k | 2k | [measure] | [OK/WARN/FAIL] |
  | TOTAL | ~18k | 30k | [sum] | [OK/WARN/FAIL] |

  Measurement method: character count / 4 (approximate tokens)
  WARN if any component exceeds Target but within Max
  FAIL if any component exceeds Max
  FAIL if Total exceeds 30k (15% of 200k context window)

  Note: Copied lifecycle skills count as 0 because they are loaded on-demand
  (only when /feature or /feature-ent is invoked), not at session start.

INTEGRITY CHECK 6: Executable Permissions
  For all scripts in .claude/hooks/:
  - .sh files have executable permission (chmod +x)
  - .py files have executable permission (chmod +x)
  - .sh files have correct shebang: #!/bin/bash
  - .py files have correct shebang: #!/usr/bin/env python3
```

### Step 4: Create Output Structure Summary

Compile the complete file tree of everything produced, annotated with phase and status:

```
[project-name]-cc-toolkit/
|-- CLAUDE.md                              <- P0 [size] [PASS/FAIL]
|-- DEVELOPMENT_GUIDE.md                   <- P0 [size] [PASS/FAIL]
|-- INSTALL.md                             <- P0 (updated P3) [size] [PASS/FAIL]
|-- .mcp.json                              <- P3 (IF integrations) [size] [PASS/FAIL]
|-- .claude/
|   |-- settings.json                      <- P0+P1+P2 merged [size] [PASS/FAIL]
|   |-- feature-roadmap.json               <- P1 [size] [PASS/FAIL]
|   |-- hooks/
|   |   |-- feature-context.py             <- P1 [size] [PASS/FAIL]
|   |   |-- validate-aggregate-size.sh     <- P2 IF DDD [size] [PASS/FAIL]
|   |   |-- check-ddd-patterns.sh          <- P2 IF DDD [size] [PASS/FAIL]
|   |-- agents/
|   |   |-- planner.md                     <- P1 [size] [PASS/FAIL]
|   |   |-- code-reviewer.md               <- P1 [size] [PASS/FAIL]
|   |   |-- architect.md                   <- P1 [size] [PASS/FAIL]
|   |   |-- tdd-guide.md                   <- P2 [size] [PASS/FAIL]
|   |   |-- ddd-validator.md               <- P2 IF DDD [size] [PASS/FAIL]
|   |-- skills/
|   |   |-- sparc-prd-mini/                <- P0 lifecycle [PASS/FAIL]
|   |   |-- explore/                       <- P0 lifecycle [PASS/FAIL]
|   |   |-- goap-research-ed25519/         <- P0 lifecycle [PASS/FAIL]
|   |   |-- problem-solver-enhanced/       <- P0 lifecycle [PASS/FAIL]
|   |   |-- requirements-validator/        <- P0 lifecycle [PASS/FAIL]
|   |   |-- brutal-honesty-review/         <- P0 lifecycle [PASS/FAIL]
|   |   |-- idea2prd-manual/              <- P1 IF DDD (path-rewritten) [PASS/FAIL]
|   |   |-- feature-navigator/            <- P1 [PASS/FAIL]
|   |   |-- project-context/              <- P1 [PASS/FAIL]
|   |   |-- coding-standards/             <- P1 [PASS/FAIL]
|   |   |-- testing-patterns/             <- P1 [PASS/FAIL]
|   |   |-- security-patterns/            <- P0 IF external APIs [PASS/FAIL]
|   |   |-- aggregate-patterns/           <- P2 IF DDD [PASS/FAIL]
|   |   |-- event-handlers/               <- P2 IF DDD [PASS/FAIL]
|   |-- commands/
|   |   |-- start.md                       <- P0 [size] [PASS/FAIL]
|   |   |-- myinsights.md                  <- P0 [size] [PASS/FAIL]
|   |   |-- feature.md                     <- P0 [size] [PASS/FAIL]
|   |   |-- feature-ent.md                <- P1 IF DDD [size] [PASS/FAIL]
|   |   |-- next.md                        <- P1 [size] [PASS/FAIL]
|   |   |-- plan.md                        <- P1 [size] [PASS/FAIL]
|   |   |-- test.md                        <- P1 [size] [PASS/FAIL]
|   |   |-- deploy.md                      <- P1 [size] [PASS/FAIL]
|   |   |-- go.md                          <- P1 [size] [PASS/FAIL]
|   |   |-- run.md                         <- P1 [size] [PASS/FAIL]
|   |   |-- docs.md                        <- P1 [size] [PASS/FAIL]
|   |   |-- review.md                      <- P2 [size] [PASS/FAIL]
|   |   |-- validate-ddd.md               <- P2 IF DDD [size] [PASS/FAIL]
|   |-- rules/
|       |-- security.md                    <- P0 [size] [PASS/FAIL]
|       |-- coding-style.md                <- P0 [size] [PASS/FAIL]
|       |-- git-workflow.md                <- P0 [size] [PASS/FAIL]
|       |-- insights-capture.md            <- P0 [size] [PASS/FAIL]
|       |-- feature-lifecycle.md           <- P0 [size] [PASS/FAIL]
|       |-- feature-lifecycle-ent.md       <- P1 IF DDD [size] [PASS/FAIL]
|       |-- secrets-management.md          <- P0 IF external APIs [size] [PASS/FAIL]
|       |-- domain-model.md                <- P0 IF DDD [size] [PASS/FAIL]
|       |-- fitness-functions.md           <- P2 IF DDD [size] [PASS/FAIL]
|       |-- testing.md                     <- P1 [size] [PASS/FAIL]
|-- docs/
|   |-- features/                          <- P0 (empty, ready for use)
|   |-- plans/                             <- P1 (empty, ready for use)
|-- myinsights/                            <- created on first /myinsights use
```

Annotate each item with:
- Phase that generated it (P0/P1/P2/P3)
- Conditional flag (IF DDD, IF external APIs, etc.)
- File size in bytes
- Validation status (PASS/FAIL) from Step 1 checks

### Step 5: Generate Validation Report

Present the validation report to the user (not saved as a file):

```
=====================================================================
TOOLKIT VALIDATION REPORT
=====================================================================

Pipeline: [SPARC | IDEA2PRD_FULL | IDEA2PRD_PARTIAL | MINIMAL]
Project: [project name from IPM]
Mode: [AUTO | HYBRID | MANUAL]

---------------------------------------------------------------------
CHECKLIST RESULTS
---------------------------------------------------------------------

P0 MANDATORY:                    [X/11 passed]
P0 CONDITIONAL:                  [X/Y passed]  (Y = applicable checks)
P1 CORE:                         [X/10 passed]
P1 ENTERPRISE (IF DDD):          [X/5 passed | N/A]
P1 FEATURE SUGGESTIONS:          [X/8 passed]
P1 AUTOMATION:                   [X/9 passed]
P2 UNIVERSAL:                    [X/3 passed]
P2 DDD-ONLY (IF DDD):           [X/5 passed | N/A]
P3 MCP:                          [X/4 passed | N/A]

PLACEHOLDER SCAN:                [0 found | N found -- CRITICAL]
INTEGRITY CHECKS:                [6/6 passed | X/6 passed]
CONTEXT BUDGET:                  [Xk / 30k tokens -- OK | OVER]

---------------------------------------------------------------------
FILE SUMMARY
---------------------------------------------------------------------

  Agents:    X files
  Skills:    X directories (Y copied with path rewrite, Z generated new)
  Commands:  X files
  Rules:     X files
  Hooks:     X files (scripts)
  Configs:   X files (settings.json, roadmap.json, .mcp.json)
  Docs:      CLAUDE.md, DEVELOPMENT_GUIDE.md, INSTALL.md

  TOTAL:     X files across Y directories

---------------------------------------------------------------------
RESULT
---------------------------------------------------------------------

IF all P0 mandatory checks pass AND placeholder scan is clean:

  TOOLKIT READY

  The toolkit is complete and validated. Next steps:
  1. Run /start to bootstrap the project
  2. Run /next to see the feature roadmap
  3. Run /feature [name] to start your first feature
  4. Run /go [name] for autonomous implementation

IF any P0 mandatory check fails:

  TOOLKIT INCOMPLETE -- P0 failures must be fixed

  FAILED CHECKS:
    - [Check N]: [description of what failed and where]
    - [Check N]: [description of what failed and where]

  Auto-fix attempted: [Y/N]
  Remaining failures after auto-fix: [count]

  Action required: Fix the listed failures and re-run Phase 6 validation.

IF placeholder scan found unresolved tokens:

  UNRESOLVED PLACEHOLDERS FOUND -- must be fixed

  FILES WITH PLACEHOLDERS:
    - [file path]: {{PLACEHOLDER_NAME}} (line N)
    - [file path]: /mnt/skills/user/ (line N)

  Auto-fix attempted: [Y/N]
  Remaining after auto-fix: [count]

=====================================================================
```

### Step 6: MANUAL Mode Final Checkpoint

```
IF mode == MANUAL:

  =====================================================================
  MANUAL CHECKPOINT 6: Final Review
  =====================================================================

  [Full validation report from Step 5]

  Available actions:
    "ok"              -- accept and finalize toolkit
    "preview [file]"  -- preview contents of a specific generated file
    "add [tool]"      -- add a missing instrument to the toolkit
    "regenerate [N]"  -- regenerate a specific failed check item
    "download"        -- package toolkit for download

  =====================================================================

  Wait for user confirmation before finalizing.

IF mode == HYBRID:

  =====================================================================
  HYBRID CHECKPOINT 2: Final Validation
  =====================================================================

  [Abbreviated validation report: tier counts + any failures]

  "ok" to finalize | "fix" to address failures

  =====================================================================

IF mode == AUTO:

  [No checkpoint -- proceed directly to finalization]
  [Only stop if P0 mandatory checks fail]
```

### Step 7: Failure Protocol

```
IF any hard requirement fails after all checks:

  1. LOG the specific failure:
     - File path
     - Check number and description
     - Expected vs actual state
     - Root cause (if determinable)

  2. ATTEMPT auto-fix (one attempt per failure):

     Missing file:
       -> Identify which phase module (03/04/05) should have generated it
       -> Re-execute that specific generation step
       -> Verify file now exists

     Unsubstituted placeholder:
       -> Look up placeholder name in IPM
       -> IF value found: substitute in file
       -> IF value not found: use sensible default and WARN user

     Invalid JSON:
       -> Attempt common fixes: remove trailing commas, add missing brackets
       -> Re-parse to verify
       -> IF still invalid: regenerate the file

     Unrewritten path (/mnt/*):
       -> Apply the standard path rewrite rules:
          /mnt/skills/user/ -> .claude/skills/
          /mnt/user-data/uploads/ -> docs/
          /output/ -> docs/ or project root
       -> Verify no /mnt/ paths remain

     Missing cross-reference:
       -> Identify which file is referenced but missing
       -> Check if it should have been generated (consult Instrument Map)
       -> IF yes: regenerate it
       -> IF no: remove the reference from the referring file

  3. RE-RUN the failed check after auto-fix

  4. IF still failing after auto-fix:
     -> Report to user with full details
     -> Suggest manual intervention
     -> Do NOT declare toolkit ready

  5. NEVER declare TOOLKIT READY if any P0 mandatory check fails
```

## Output

### Primary Output

- **Validation Report** -- displayed to user, not persisted as a file
  - Per-tier pass/fail counts
  - Placeholder scan results
  - Integrity check results (6 checks)
  - Context budget measurements per component
  - Complete file count summary
  - Clear READY or INCOMPLETE verdict

### Verification State (internal)

- Output structure manifest (complete file tree with per-file annotations)
- Cross-reference verification map
- Context budget measurements table
- Placeholder scan results log

### Delivery State

Upon successful validation (all hard requirements pass):
- All generated files are in their final locations within the project directory
- No temporary or intermediate files remain
- All JSON files parse without errors
- All hook scripts have executable permissions
- All placeholders are resolved
- All cross-references resolve to existing files
- Context budget is within limits
- The project is ready for `/start` to bootstrap

## Quality Gate

The Phase 6 quality gate IS the Master Validation Checklist. The gate passes when:

### Hard Requirements (must ALL pass -- blocking)

- [ ] P0 Mandatory: 100% pass rate (all 11 checks green)
- [ ] P0 Conditional: 100% pass rate for all applicable checks
- [ ] Placeholder scan: ZERO unsubstituted `{{PLACEHOLDER}}` patterns found
- [ ] Placeholder scan: ZERO unrewritten `/mnt/` paths found
- [ ] JSON validity: ALL JSON files parse without errors
- [ ] File cross-references: ALL referenced files exist
- [ ] Context budget: Total < 30k tokens

### Soft Requirements (warning if failed, not blocking)

- [ ] P1/P2/P3 checks pass for all generated tiers
- [ ] Context budget within target (not just max) per component
- [ ] All skill directories contain references/ subdirectory (when source had one)
- [ ] Feature roadmap contains >= 5 features with correct statuses
- [ ] All agents have trigger keywords in their description frontmatter
- [ ] Hook scripts have correct shebang lines

### Failure Protocol Summary

```
Hard requirement fails -> auto-fix attempt -> re-check -> report if still failing
Soft requirement fails -> WARN in report -> proceed with delivery
P0 failure after auto-fix -> BLOCK delivery, require user intervention
```

## Dependencies

### Upstream Modules (all prior phases)

| Module | Provides |
|--------|----------|
| `01-detect-parse.md` | IPM with detection flags and project characteristics for conditional checks |
| `02-analyze-map.md` | Instrument Map for verifying scored items were generated |
| `03-generate-p0.md` | P0 mandatory files to validate |
| `04-generate-p1.md` | P1 recommended files to validate |
| `05-generate-p2p3.md` | P2/P3 optional files to validate |

### Reference Files

| Reference | Used For |
|-----------|----------|
| `references/claude-md-strategy.md` | Verifying CLAUDE.md structure follows the generation strategy |
| SKILL.md "Master Validation Checklist" section | Authoritative checklist source |
| SKILL.md "Output Structure" section | Expected directory tree reference |
| SKILL.md "Context Budget" section | Token budget limits |

### No External Dependencies

This module operates entirely on generated files from prior phases. It does not read
source documentation, invoke external skills, or generate new content (except auto-fixes).
Its sole purpose is validation, integrity verification, and delivery reporting.

## Reusability

### Package Validation Pattern for Multi-File Generation Systems

The validation approach in this module is a universal pattern for any system that generates
multiple interdependent files across several phases:

1. **Tiered checklist validation** -- organize checks by priority (mandatory vs optional)
   so that critical failures are caught first and block delivery while non-critical issues
   produce warnings but allow proceeding

2. **Placeholder sweep** -- scan all generated files for template markers that should have
   been substituted, catching generation errors that single-file validation would miss.
   This is especially important in multi-phase pipelines where later phases may assume
   earlier phases resolved all placeholders

3. **Cross-reference verification** -- verify that every reference between generated files
   (agent -> skill, command -> command, config -> script, documentation -> file) resolves
   to an actual existing file. This catches orphaned references from conditional generation
   where a file was gated out but references to it were not

4. **Context budget enforcement** -- measure aggregate resource consumption across all
   generated files against defined limits. In AI-assisted development, context window
   budget is a hard constraint that determines whether the toolkit is usable

5. **Auto-fix protocol** -- attempt mechanical fixes for common failure modes before
   escalating to the user. This reduces friction in the generation pipeline while
   maintaining strict quality gates

6. **Structured reporting** -- present validation results in a clear, actionable format
   with per-tier counts, specific failure descriptions, and explicit next-step guidance

This pattern is directly applicable to:
- Project scaffolding tools (cookiecutter, yeoman, create-* CLIs)
- Infrastructure-as-code generators (Terraform modules, Kubernetes manifests)
- API SDK generators (OpenAPI codegen, gRPC generators)
- Documentation site generators (Docusaurus, Sphinx)
- Any multi-phase pipeline producing interdependent output artifacts
