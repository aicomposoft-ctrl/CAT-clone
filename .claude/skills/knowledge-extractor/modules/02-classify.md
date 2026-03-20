# Phase 2: Classify

Map raw findings to the 7 artifact categories and filter out non-extractables.

## Goal

Transform the Raw Findings List into a curated Classified Artifact List.
Every finding must either be assigned a category or explicitly excluded with reason.

## 7 Artifact Categories

| # | Category | Directory | What Belongs | Example |
|---|----------|-----------|-------------|---------|
| 1 | **Skills** | `skills/` | New or improved SKILL.md techniques | Better API integration technique |
| 2 | **Commands** | `commands/` | Slash commands for Claude Code | `/api-endpoint` generates CRUD |
| 3 | **Hooks** | `hooks/` | Pre-commit, post-task, CI automation | Auto-validate OpenAPI schema |
| 4 | **Rules** | `rules/` | Constraints, limitations, "don't do X" | "Nested generics >3 levels break AI" |
| 5 | **Templates** | `templates/` | Reusable file/project structures | Dockerfile for Node+Postgres |
| 6 | **Patterns** | `patterns/` | Architectural approaches as docs | Event sourcing + CQRS |
| 7 | **Snippets** | `snippets/` | Small ready code fragments (<50 lines) | Universal retry with backoff |

See `references/artifact-categories.md` for detailed criteria per category.

## Classification Process

For each finding from Phase 1:

### Step 1: Apply Exclusion Filter

**Exclude if ANY of these are true:**

| Exclusion Criteria | Reason |
|-------------------|--------|
| Domain-specific (business logic) | Won't generalize |
| Used exactly once, unvalidated | Not proven enough |
| Library bugfix workaround | Will expire with next lib version |
| Contains secrets/credentials | Security risk |
| Hardcoded business rules | Not transferable |
| Extremely framework-specific | Too narrow scope |

**Exception:** Library workarounds CAN be extracted as temporary rules
with a review date: `## Expiry: Check after [library] v[next]`

### Step 2: Determine Primary Category

Use this decision tree:

```
Is it executable logic (<50 lines)?
  → YES: Snippet
  → NO: Continue

Is it a complete workflow/process?
  → YES: Is it a Claude Code slash command?
    → YES: Command
    → NO: Skill
  → NO: Continue

Is it an automation trigger?
  → YES: Hook
  → NO: Continue

Is it a constraint or lesson?
  → YES: Rule
  → NO: Continue

Is it a file structure or config?
  → YES: Template
  → NO: Continue

Is it an architectural approach?
  → YES: Pattern
  → NO: Reconsider — may not be extractable
```

### Step 3: Assess Cross-Category

Some artifacts span categories. Mark secondary categories:

| Primary | Common Secondary |
|---------|-----------------|
| Pattern | Template (implementation scaffold) |
| Snippet | Pattern (if part of larger pattern) |
| Command | Hook (if automatable) |
| Rule | Snippet (code that enforces the rule) |
| Skill | Command (entry point for the skill) |

### Step 4: Confidence Rating

| Rating | Meaning | Criteria |
|--------|---------|----------|
| **HIGH** | Definitely extract | Universal, proven, well-tested |
| **MEDIUM** | Likely extract | Needs some generalization |
| **LOW** | Maybe extract | Needs significant rework, questionable reusability |

## Output: Classified Artifact List

```markdown
## Classified Artifacts

### ✅ Extract ([N] artifacts)

| # | Artifact | Primary | Secondary | Confidence | Notes |
|---|----------|---------|-----------|------------|-------|
| 1 | Retry with backoff | Pattern | Snippet | HIGH | Universal HTTP retry |
| 2 | /db-migrate | Command | - | MEDIUM | Needs param extraction |
| 3 | Error boundary pattern | Pattern | Template | HIGH | Works with any framework |

### ❌ Skip ([M] items)

| # | Finding | Reason |
|---|---------|--------|
| 4 | Auth middleware | Domain-specific (user model tied) |
| 5 | Stripe webhook handler | Too platform-specific |
| 6 | Temp fix for lib bug #123 | Will expire, library-specific |

### ⚠️ Uncertain ([K] items)

| # | Finding | Question | Decision Needed |
|---|---------|----------|-----------------|
| 7 | Custom ORM wrapper | Generalizable or too specific? | User input |
```
