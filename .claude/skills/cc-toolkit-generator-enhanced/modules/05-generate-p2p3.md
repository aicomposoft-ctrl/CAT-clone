# Module: Generate P2-P3 (Optional)

Phase 5 of the CC-Toolkit-Generator-Enhanced pipeline. Generates optional advanced instruments
across two tiers: P2 (enhanced development workflow) and P3 (external integrations).
Items are feature-flagged by project characteristics — DDD-specific items only generate
when DDD documentation is detected.

## Input

- **Internal Project Model (IPM)** — from Phase 1 (Detect & Parse)
  - `project_name`, `tech_stack`, `docker_services`, `monorepo_packages`
  - `has_ddd`, `has_gherkin`, `has_fitness`, `has_adr`, `has_c4`
  - `has_external_apis`, `has_database`
  - `detected_integrations[]` — list of external services found in Architecture.md
  - `pipeline_type` — SPARC | IDEA2PRD_FULL | IDEA2PRD_PARTIAL | MINIMAL
- **Instrument Map** — from Phase 2 (Analyze & Map)
  - Scored instrument list; P2 items have score 8-11, P3 items are external/MCP
- **P0/P1 Outputs** — from Phase 3-4
  - Existing `.claude/settings.json` with hooks (insights, roadmap, plans, SessionStart)
  - Generated agents, skills, commands, and rules to extend
  - Confirmed file paths and naming conventions

## Process

> **ANTI-COMPRESSION DIRECTIVE:** When generating files from templates in this module,
> COPY the FULL text of each template. Do NOT summarize, compress, or "interpret" templates.
> Every section, every placeholder, every comment must be preserved verbatim.
> AI systems routinely compress 211-line templates to 60 lines — this is a CRITICAL defect.
> Validate: generated file line count must be >= 80% of template line count.

### Tier Overview

```
P2 — Enhanced Development Workflow (score 8-11):
  Universal:  tdd-guide.md agent, settings.json hooks, /review command
  DDD-only:   ddd-validator.md agent, aggregate-patterns/ skill, event-handlers/ skill, /validate-ddd command

P3 — External Integrations:
  Universal:  .mcp.json
  Specific:   Coolify MCP, Docker MCP (based on detection)
```

### Step 1: Generate P2 Universal Items

#### 1a. tdd-guide.md Agent

Source: Pseudocode (SPARC/idea2prd) + Gherkin tests (idea2prd) + Fitness Functions (idea2prd)

Read template: `view("references/templates/ddd-agents.md")` section "tdd-guide.md Agent (Enhanced)"
> CRITICAL: COPY the full template. Do NOT compress or summarize.

```
Generate .claude/agents/tdd-guide.md:
  - Set frontmatter:
    name: tdd-guide
    description: TDD guide with Gherkin and pseudocode awareness (include trigger keywords)
    tools: Read, Write, Edit, Bash
    model: sonnet
    skills: testing-patterns
  - Include TDD workflow: Red → Green → Refactor
  - IF has_pseudocode: index all .pseudo files with descriptions
    Fill {{PSEUDOCODE_INDEX}} from docs/pseudocode/*.pseudo file listing
  - IF has_gherkin: index all .feature files with scenario counts
    Fill {{GHERKIN_FEATURES_LIST}} from docs/tests/*.feature file listing
    Include Gherkin-to-test mapping example for the project's tech stack
    Fill {{EXAMPLE_SCENARIO}} from first feature file
    Fill {{TEST_TEMPLATE}} with language-appropriate test boilerplate
  - IF has_fitness: extract coverage requirements
    Fill {{TARGET_LINE}} from fitness function line coverage target
    Fill {{TARGET_BRANCH}} from fitness function branch coverage target
  - ELSE (no Gherkin/Pseudocode): derive from Refinement.md test strategy
    Include standard TDD patterns for the tech stack
    Fill coverage targets with sensible defaults (80% line, 70% branch)
  - Fill {{LANGUAGE}} from IPM tech_stack primary language
```

#### 1b. settings.json Hooks (Merge)

Source: Fitness Functions + DDD Tactical

Read template: `view("references/templates/ddd-hooks-commands.md")` section "Fitness Function Hooks"

```
Merge additional hooks into existing .claude/settings.json:

EXISTING hooks from P0/P1:
  - Stop: insights auto-commit, roadmap auto-commit, plans auto-commit
  - SessionStart: feature-context.py

NEW hooks to ADD (do NOT overwrite existing):

  IF has_fitness:
    - PreToolUse (matcher: "Write|Edit"):
        command: "$CLAUDE_PROJECT_DIR"/.claude/hooks/validate-aggregate-size.sh "$CLAUDE_FILE_PATH"
        timeout: 10

    - PostToolUse (matcher: "Write|Edit"):
        command: check-ddd-patterns.sh on aggregate/entity files
        timeout: 30

    - PostToolUse (matcher: "Write|Edit"):
        command: run tests on .test./.spec. files with coverage
        timeout: 120

  IF has_ddd:
    - Stop (additional prompt):
        "Before stopping, verify: 1) All aggregate invariants enforced,
         2) Domain events emitted for state changes, 3) Tests cover Gherkin scenarios,
         4) Fitness functions pass."
        timeout: 30

  Generate hook scripts:
    IF has_fitness OR has_ddd:
      - .claude/hooks/validate-aggregate-size.sh
        Fill {{MAX_ENTITIES_FROM_FITNESS}} from fitness functions (default: 7)
        Fill {{MAX_METHODS_FROM_FITNESS}} from fitness functions (default: 15)
        Make executable: chmod +x

      - .claude/hooks/check-ddd-patterns.sh
        Validates: no direct entity modification outside aggregate,
                   state changes emit domain events
        Make executable: chmod +x

Merge strategy:
  1. Read existing settings.json
  2. Parse JSON
  3. For each hook event type (PreToolUse, PostToolUse, Stop, SessionStart):
     - Append new hook entries to existing array
     - Never remove or modify existing entries
  4. Write back valid JSON
  5. Verify JSON validity with json.parse or equivalent
```

#### 1c. /review Command

```
Generate .claude/commands/review.md:
  - Purpose: On-demand code review using code-reviewer agent
  - $ARGUMENTS: file path, directory, "all", or "staged" (git staged files)
  - Process:
    1. Parse scope from $ARGUMENTS
    2. Gather files to review
    3. Invoke code-reviewer agent analysis
    4. IF has_ddd: include DDD compliance check
    5. IF has_fitness: include fitness function verification
    6. IF has_adr: include ADR compliance check
    7. Generate review report
  - Output format:
    Summary → DDD Compliance → Fitness Functions → ADR Compliance →
    Code Quality → Verdict (APPROVE/REQUEST_CHANGES/COMMENT)
  - Reference code-reviewer.md agent for the actual review logic
```

### Step 2: Generate P2 DDD-Only Items

**Trigger:** `IPM.has_ddd == true`

All items in this step are gated by the DDD feature flag. If `has_ddd == false`,
skip this entire step.

#### 2a. ddd-validator.md Agent

Source: DDD Tactical (aggregates) + Fitness Functions

Read template: `view("references/templates/ddd-agents.md")` section "ddd-validator.md Agent"
> CRITICAL: COPY the full template. Do NOT compress or summarize.

```
IF has_ddd:
  Generate .claude/agents/ddd-validator.md:
    - Set frontmatter:
      name: ddd-validator
      description: DDD tactical design validator (include trigger keywords)
      tools: Read, Glob, Grep, Bash
      model: sonnet
      skills: aggregate-patterns, coding-standards
    - Extract aggregate invariants from docs/ddd/tactical/aggregates/
      Fill {{AGGREGATE_INVARIANTS}} with invariant rules per aggregate
    - Extract size limits from fitness functions:
      Fill {{MAX_ENTITIES}} (default: 7)
      Fill {{MAX_METHODS}} (default: 15)
      Fill {{MAX_DEPTH}} (default: 3)
    - Include validation rules:
      - Aggregate rules (root controls modifications, events emitted)
      - Entity rules (identity-based equals, immutable ID)
      - Value Object rules (immutable, property-based equals, no ID)
      - Domain Event rules (past tense naming, immutable payload, aggregate ID, timestamp)
    - Include validation checklist:
      - Aggregate root controls all modifications
      - No direct entity/VO modification from outside
      - Events emitted for state changes
      - Invariants checked before state change
      - Repository per aggregate only
    - Output format: Valid/Warning/Violation per aspect + Fitness Score
```

#### 2b. aggregate-patterns/ Skill

Source: DDD Tactical (aggregates, entities, value-objects)

Read template: `view("references/templates/ddd-skills.md")` section "aggregate-patterns/ Skill"
> CRITICAL: COPY the full template. Do NOT compress or summarize.

```
IF has_ddd:
  Generate .claude/skills/aggregate-patterns/SKILL.md:
    - Extract all aggregates from docs/ddd/tactical/aggregates/
      Fill {{AGGREGATE_LIST_WITH_DESCRIPTIONS}} with name + description
    - Generate language-specific templates based on tech_stack:
      Fill {{LANGUAGE}} from primary language
      Fill {{AGGREGATE_TEMPLATE_FOR_STACK}} — aggregate root class/struct
      Fill {{VALIDATION_PATTERN}} — invariant validation pattern
      Fill {{FACTORY_PATTERN}} — aggregate factory method
      Fill {{ENTITY_ID_PATTERN}} — entity identity pattern
      Fill {{VALUE_OBJECT_PATTERN}} — immutable value object pattern
    - Extract invariants table:
      Fill {{INVARIANTS_TABLE}} with aggregate | invariant | validation mapping
```

#### 2c. event-handlers/ Skill

Source: DDD Tactical (events)

Read template: `view("references/templates/ddd-skills.md")` section "event-handlers/ Skill"
> CRITICAL: COPY the full template. Do NOT compress or summarize.

```
IF has_ddd:
  Generate .claude/skills/event-handlers/SKILL.md:
    - Extract all domain events from docs/ddd/tactical/events/
      Fill {{EVENTS_TABLE}} with event | aggregate | payload | handlers mapping
    - Generate language-specific patterns:
      Fill {{LANGUAGE}} from primary language
      Fill {{EVENT_EMISSION_PATTERN}} — how aggregates emit events
      Fill {{EVENT_HANDLER_PATTERN}} — handler implementation template
      Fill {{SUBSCRIPTION_PATTERN}} — event subscription/registration
    - Include event flow diagrams:
      Fill {{AGGREGATE}}, {{EVENT}}, {{HANDLER}}, {{TARGET}} per event chain
    - Include anti-patterns section (hardcoded, universal):
      - DON'T modify aggregate state in handler
      - DON'T throw exceptions in handlers (use dead letter)
      - DON'T create circular event chains
```

#### 2d. /validate-ddd Command

Source: Fitness Functions + DDD Tactical

Read template: `view("references/templates/ddd-hooks-commands.md")` section "/validate-ddd Command"

```
IF has_ddd:
  Generate .claude/commands/validate-ddd.md:
    - $ARGUMENTS: scope — "all" | "aggregate [name]" | "context [name]"
    - Validation checks:
      Aggregate Validation:
        - Single aggregate root per file
        - All modifications through aggregate root
        - Invariants checked before state changes
        - Events emitted for state changes
      Fitness Functions:
        Fill {{FITNESS_FUNCTIONS_LIST}} from docs/fitness/fitness-functions.md
      Bounded Context Validation:
        - No cross-context direct dependencies
        - Anti-corruption layers in place
        - Shared kernel properly isolated
    - Process: parse scope → scan files → run checks → calculate scores → report
    - Output format: DDD Validation Report with:
      - Per-aggregate status (Valid/Warning/Violation)
      - Fitness function results (Target vs Actual vs Status)
      - Violation details with fix suggestions
      - Overall score out of 100
```

#### 2e. fitness-functions.md Rule

Source: Fitness Functions document

Read template: `view("references/templates/ddd-hooks-commands.md")` section "Fitness Functions Rule"

```
IF has_ddd AND has_fitness:
  Generate .claude/rules/fitness-functions.md:
    - Extract fitness functions from docs/fitness/fitness-functions.md
    - Map each function to a measurable quality gate:
      Fill {{FITNESS_FUNCTIONS_TABLE}} with name | metric | target | frequency
    - Include enforcement guidance:
      - Which functions run on every commit (fast)
      - Which functions run on PR review (medium)
      - Which functions run on release (slow)
    - Reference /validate-ddd command for DDD-specific fitness checks
```

### Step 3: Generate P3 Items — MCP Configuration

Read complete template: `view("references/templates/mcp.md")`
> CRITICAL: COPY the full template. Do NOT compress or summarize.

```
Generate .mcp.json in project root:

Step 1: Extract integrations from Architecture.md:
  - Scan for "External Integrations", "Third-Party Services", "API" sections
  - Match each integration against known MCP server list

Step 2: Match integrations to MCP servers:
  Priority order:
    1. Exact match → use official server config
    2. Category match → use generic server (e.g., any SQL → postgres server)
    3. No match → add comment for custom consideration

Step 3: Build .mcp.json:
  Base structure:
    { "mcpServers": { ... }, "disabledMcpServers": [] }

  For each matched integration:
    - Add server config with command, args, env
    - Always use ${VAR_NAME} syntax for secrets (never hardcode)
    - Use descriptive env var names

  Common server configs (from template):
    | Integration | Package | Env Vars |
    |-------------|---------|----------|
    | GitHub | @modelcontextprotocol/server-github | GITHUB_TOKEN |
    | PostgreSQL | @modelcontextprotocol/server-postgres | DATABASE_URL |
    | Supabase | @supabase/mcp-server | SUPABASE_URL, SUPABASE_KEY |
    | Slack | @modelcontextprotocol/server-slack | SLACK_BOT_TOKEN |
    | Notion | @modelcontextprotocol/server-notion | NOTION_TOKEN |
    | Brave Search | @anthropic/mcp-server-brave-search | BRAVE_API_KEY |
    | Puppeteer | @anthropic/mcp-server-puppeteer | (none) |
    | Sequential Thinking | @anthropic/mcp-server-sequential-thinking | (none) |
    | Memory | @anthropic/mcp-server-memory | (none) |
    | Filesystem | @anthropic/mcp-server-filesystem | (path arg) |

Step 4: Conditionally add infrastructure MCP servers:

  IF "Coolify" detected in Architecture.md or docker-compose.yml:
    Add Coolify MCP server configuration
    Score boost: +8 from recommendations engine

  IF "Docker" detected in docker_services or Architecture.md:
    Add Docker MCP server configuration
    Score boost: +5 from recommendations engine

Step 5: Apply best practices:
  - Keep total enabled servers < 10 (context window impact)
  - Move rarely-used servers to disabledMcpServers[]
  - Document required env vars in INSTALL.md

Step 6: Verify output:
  - Parse .mcp.json as JSON — must be valid
  - Verify no hardcoded secrets
  - Verify all env vars use ${} syntax
```

### Step 4: Update INSTALL.md

```
IF .mcp.json was generated:
  Add MCP Configuration section to INSTALL.md:
    - List all required environment variables from .mcp.json
    - Include setup instructions for each MCP server
    - Note which servers are optional (in disabledMcpServers)
```

## Output

### Generated Files (P2 Universal)

| File | Type | Path |
|------|------|------|
| tdd-guide.md | Agent | `.claude/agents/tdd-guide.md` |
| settings.json | Config (merge) | `.claude/settings.json` |
| review.md | Command | `.claude/commands/review.md` |

### Generated Files (P2 DDD-Only — IF has_ddd)

| File | Type | Path |
|------|------|------|
| ddd-validator.md | Agent | `.claude/agents/ddd-validator.md` |
| aggregate-patterns/ | Skill | `.claude/skills/aggregate-patterns/SKILL.md` |
| event-handlers/ | Skill | `.claude/skills/event-handlers/SKILL.md` |
| validate-ddd.md | Command | `.claude/commands/validate-ddd.md` |

### Generated Files (P2 DDD-Only — Hook Scripts, IF has_fitness OR has_ddd)

| File | Type | Path |
|------|------|------|
| validate-aggregate-size.sh | Hook Script | `.claude/hooks/validate-aggregate-size.sh` |
| check-ddd-patterns.sh | Hook Script | `.claude/hooks/check-ddd-patterns.sh` |

### Generated Files (P3)

| File | Type | Path |
|------|------|------|
| .mcp.json | Config | `.mcp.json` (project root) |

### Modified Files

| File | Modification |
|------|-------------|
| `.claude/settings.json` | Merged PreToolUse, PostToolUse, Stop hooks (if DDD/fitness) |
| `INSTALL.md` | Added MCP environment variable documentation (if .mcp.json generated) |

## Quality Gate

All of the following must pass before proceeding to Phase 6:

### P2 Universal Validation

- [ ] `tdd-guide.md` agent generated with correct frontmatter (model, tools, skills)
- [ ] `tdd-guide.md` includes TDD workflow (Red/Green/Refactor)
- [ ] `tdd-guide.md` has Gherkin mapping IF has_gherkin, pseudocode index IF has_pseudocode
- [ ] `settings.json` is valid JSON after merge
- [ ] Existing hooks preserved — no P0/P1 hooks removed or modified
- [ ] New hooks correctly appended to existing hook event arrays
- [ ] `/review` command generated with scope handling ($ARGUMENTS parsing)

### P2 DDD-Only Validation (IF has_ddd)

- [ ] `ddd-validator.md` agent generated ONLY if `has_ddd == true`
- [ ] `ddd-validator.md` includes aggregate invariants extracted from source docs
- [ ] `ddd-validator.md` includes fitness function size limits (or sensible defaults)
- [ ] `aggregate-patterns/SKILL.md` generated ONLY if `has_ddd == true`
- [ ] `aggregate-patterns/SKILL.md` includes language-specific templates matching tech stack
- [ ] `aggregate-patterns/SKILL.md` includes all aggregates from DDD tactical docs
- [ ] `event-handlers/SKILL.md` generated ONLY if `has_ddd == true`
- [ ] `event-handlers/SKILL.md` includes event table with aggregate mapping
- [ ] `event-handlers/SKILL.md` includes anti-patterns section
- [ ] `/validate-ddd` command generated ONLY if `has_ddd == true`
- [ ] `/validate-ddd` supports all three scopes: all, aggregate, context
- [ ] Hook scripts are executable (`chmod +x` applied)
- [ ] Hook scripts have correct shebang (`#!/bin/bash`)
- [ ] DDD items have NO presence in output when `has_ddd == false`

### P3 Validation

- [ ] `.mcp.json` is valid JSON (parseable without errors)
- [ ] `.mcp.json` contains no hardcoded secrets (all use `${VAR_NAME}` syntax)
- [ ] Only actually-needed MCP servers are enabled (matched to detected integrations)
- [ ] Total enabled servers < 10 (context window budget)
- [ ] `disabledMcpServers` array present (even if empty)
- [ ] `INSTALL.md` documents all required env vars from `.mcp.json`

### Cross-Phase Consistency

- [ ] All `{{PLACEHOLDER}}` values substituted with actual project data
- [ ] No `{{IF_DDD}}` markers in output when `has_ddd == false`
- [ ] Agent `skills:` references only point to skills that actually exist (generated in P0/P1/P2)
- [ ] Command cross-references only point to commands that exist
- [ ] settings.json hook `command` paths reference scripts that exist in `.claude/hooks/`

## Dependencies

### Template Files (read via view())

| Template | Used For |
|----------|----------|
| `references/templates/ddd-hooks-commands.md` | DDD hooks, /validate-ddd command, /test enhanced, /deploy enhanced |
| `references/templates/mcp.md` | .mcp.json generation — server configs, matching rules, best practices |
| `references/templates/ddd-agents.md` | tdd-guide.md, ddd-validator.md, code-reviewer.md (enhanced) agent templates |
| `references/templates/ddd-skills.md` | aggregate-patterns/, event-handlers/ skill templates |

### Upstream Modules

| Module | Provides |
|--------|----------|
| `01-detect-parse.md` | IPM with detection flags and integration list |
| `02-analyze-map.md` | Instrument Map with P2/P3 scored items |
| `03-generate-p0.md` | Base settings.json, CLAUDE.md, rules to extend |
| `04-generate-p1.md` | P1 agents/skills/commands that P2 items reference |

### Source Documents (from uploads)

| Document | Used By |
|----------|---------|
| Pseudocode.md / docs/pseudocode/*.pseudo | tdd-guide.md agent |
| docs/tests/*.feature (Gherkin) | tdd-guide.md, testing hooks |
| docs/fitness/fitness-functions.md | hooks, ddd-validator, /validate-ddd |
| docs/ddd/tactical/aggregates/ | ddd-validator, aggregate-patterns |
| docs/ddd/tactical/events/ | event-handlers skill |
| docs/ddd/strategic/ | /validate-ddd bounded context validation |
| Architecture.md | .mcp.json integration detection |

## Reusability

### Optional Tier Generation with Feature Flags Pattern

The P2-P3 generation approach demonstrates a reusable pattern for optional-tier output
in any multi-file generation system:

1. **Feature flag detection** — boolean flags from input analysis control which items generate
2. **Strict gating** — items only appear in output when their flag is true; no partial generation
3. **Merge-not-overwrite** — new configuration is merged into existing files, preserving prior content
4. **Tier isolation** — P2 and P3 items are independent; either can be generated without the other
5. **Graceful absence** — when flags are false, no trace of gated items appears in output

This pattern is applicable to:
- Plugin systems with optional feature modules
- Configuration generators with tiered complexity
- Scaffold tools that adapt to detected capabilities
- Any system where output should contain zero artifacts for disabled features

### MCP Configuration Generation Pattern

The .mcp.json generation logic is a reusable pattern for matching detected integrations
to known service configurations:

1. Scan source documents for integration signals
2. Match against a known server registry with priority (exact > category > none)
3. Generate configurations with templated environment variables
4. Apply budget constraints (max servers for context window)
5. Document requirements in installation guide

This pattern works for any system that needs to auto-configure integrations based on
project analysis — CI/CD configs, docker-compose services, package dependencies, etc.

### Hook Merge Strategy

The settings.json merge approach (append new hooks to existing event arrays without
modifying prior entries) is a reusable pattern for incremental configuration building
across pipeline phases. Each phase can independently add hooks without coordination,
as long as the merge is additive-only.
