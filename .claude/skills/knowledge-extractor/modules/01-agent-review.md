# Phase 1: Agent Review

AI-assisted project scanning using a swarm of 5 parallel extraction agents.

## Goal

Find all extractable knowledge in the project — patterns, commands, rules, templates,
snippets, skills, and hooks that could be reused in other projects.

## Input

- Project codebase (current working directory)
- `TOOLKIT_HARVEST.md` markers (if exists in project root)
- User context about what was valuable (if provided)

## Swarm of Extraction Agents

Launch 5 parallel agents via Task tool. Each agent independently scans the codebase
from its perspective.

### Agent: extractor-patterns

**Scope:** Architecture and code patterns

**Scan for:**
- Middleware implementations (rate limiting, auth, logging, caching)
- Error handling patterns (retries, circuit breakers, fallbacks)
- Data access patterns (repository, DAO, query builders)
- Communication patterns (pub/sub, event sourcing, CQRS)
- Configuration patterns (env loading, feature flags, multi-env)
- Testing patterns (fixtures, factories, custom matchers)

**How to scan:**
1. Look at directory structure for architectural patterns
2. Scan for abstract/generic implementations (not domain-specific)
3. Check for reusable middleware or interceptors
4. Look for utility modules that solve common problems
5. Check `TOOLKIT_HARVEST.md` → Patterns section

**Output per finding:**
```markdown
- **Name:** [Pattern Name]
- **File:** [path/to/file.ext:line]
- **Description:** [1 sentence]
- **Reusability:** HIGH | MEDIUM | LOW
- **Why reusable:** [reason]
```

### Agent: extractor-commands

**Scope:** Scripts, CLI utilities, slash commands

**Scan for:**
- Shell scripts in `scripts/`, `bin/`, `tools/`
- Package.json scripts / Makefile targets / Taskfile tasks
- Database migration commands
- Code generation utilities
- Dev environment setup scripts
- CI/CD pipeline steps that could be local commands
- Existing `.claude/commands/` that are generalizable

**How to scan:**
1. List all executable scripts
2. Check package.json / Makefile / Taskfile for useful targets
3. Check `.claude/commands/` for project-specific commands worth generalizing
4. Check `TOOLKIT_HARVEST.md` → Commands section

**Output per finding:**
```markdown
- **Name:** [Command Name]
- **File:** [path]
- **What it does:** [1 sentence]
- **Generalizability:** HIGH | MEDIUM | LOW
- **Dependencies:** [external tools needed]
```

### Agent: extractor-rules

**Scope:** Constraints, workarounds, lessons learned

**Scan for:**
- Comments with `TODO`, `HACK`, `WORKAROUND`, `NOTE`, `FIXME`
- Known issues documented in README or docs
- Edge cases in tests (especially ones that were hard to find)
- Library-specific quirks discovered during development
- Performance constraints discovered empirically
- Security constraints that weren't obvious
- Claude Code limitations (things that don't work well with AI)

**How to scan:**
1. Grep for `TODO|HACK|WORKAROUND|NOTE|FIXME|XXX|BUG`
2. Check README/docs for "gotchas" or "known issues"
3. Look at test names for edge case descriptions
4. Check git commit messages for "fix:" — these often encode lessons
5. Check `TOOLKIT_HARVEST.md` → Lessons/Rules section

**Output per finding:**
```markdown
- **Rule:** [Don't do X because Y]
- **Source:** [file:line or commit:hash]
- **Type:** Constraint | Workaround | Lesson | Limitation
- **Scope:** Universal | Language-specific | Framework-specific
- **Expiry:** Permanent | Check in [timeframe]
```

### Agent: extractor-templates

**Scope:** File structures, configs, project scaffolds

**Scan for:**
- Dockerfile / docker-compose.yml patterns
- CI/CD configuration (.github/workflows, .gitlab-ci.yml)
- Linter/formatter configs (.eslintrc, .prettierrc, rustfmt.toml)
- Project structure conventions
- Testing configuration
- Monitoring/logging setup
- Environment configuration templates

**How to scan:**
1. List all config/dot files
2. Identify which configs are project-specific vs. generalizable
3. Check for well-structured Dockerfiles worth reusing
4. Check CI/CD configs for reusable job definitions
5. Check `TOOLKIT_HARVEST.md` → Templates section

**Output per finding:**
```markdown
- **Name:** [Template Name]
- **File:** [path]
- **What it templates:** [1 sentence]
- **Parameterizable:** YES (what params) | NO (why)
- **Tech stack:** [language/framework]
```

### Agent: extractor-snippets

**Scope:** Small, ready-to-use code fragments

**Scan for:**
- Utility functions in `utils/`, `helpers/`, `lib/`, `common/`
- One-liners that solve common problems
- Type definitions / interfaces that are universal
- Error handler implementations
- Validation functions
- Date/time helpers
- String manipulation utilities
- HTTP client wrappers

**How to scan:**
1. Scan utility directories
2. Look for small (<50 lines) functions with no domain dependencies
3. Check for functions used across multiple modules (sign of universality)
4. Check `TOOLKIT_HARVEST.md` → Snippets section

**Output per finding:**
```markdown
- **Name:** [Snippet Name]
- **File:** [path:line]
- **Language:** [lang]
- **Lines:** [count]
- **Dependencies:** None | [list]
- **What it does:** [1 sentence]
```

## Merging Strategy

After all 5 agents complete:

1. **Deduplicate** — same finding reported by multiple agents → keep richest description
2. **Cross-reference** — if a pattern is also a template, note both categories
3. **Sort by confidence** — HIGH reusability first
4. **Count** — total findings, per-category breakdown
5. **Include TOOLKIT_HARVEST.md markers** — merge manual markers with auto-discovered

## Output: Raw Findings List

```markdown
## Raw Findings

### Summary
- Total candidates: [N]
- From agents: [M] (unique after dedup)
- From TOOLKIT_HARVEST.md markers: [K]
- By category: Skills [X], Commands [Y], Patterns [Z], Rules [A], Templates [B], Snippets [C], Hooks [D]

### Findings Table

| # | Finding | Source | Category | Reusability | Agent |
|---|---------|--------|----------|-------------|-------|
| 1 | [name] | [file:line] | [category] | HIGH | extractor-patterns |
| 2 | [name] | [file:line] | [category] | MEDIUM | extractor-commands |
```
