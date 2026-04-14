---
name: knowledge-extractor
description: >
  Systematic knowledge extraction from completed projects into reusable toolkit artifacts.
  Converts project-specific code, patterns, and lessons into decontextualized, versioned,
  composable artifacts (skills, commands, hooks, rules, templates, patterns, snippets).
  Supports two extraction modes: continuous markers during work and dedicated harvest sessions.
  Uses swarm agents for parallel extraction across artifact categories. Domain-agnostic —
  works with any tech stack, language, or project type.
  Triggers: "harvest", "extract knowledge", "toolkit harvest", "извлечь знания",
  "ритуал извлечения", "harvest session", "что забрать в тулкит".
---

# Knowledge Extractor: Project → Reusable Toolkit Artifacts

Systematically extract valuable knowledge from completed projects and transform it into
reusable, decontextualized toolkit artifacts. Lightweight process — not a quarterly review,
but a natural part of every project/sprint lifecycle.

## Architecture

```
knowledge-extractor/
├── SKILL.md                              # Orchestrator (this file)
├── modules/
│   ├── 01-agent-review.md                # Phase 1: AI-assisted project review
│   ├── 02-classify.md                    # Phase 2: Categorize into artifact types
│   ├── 03-decontextualize.md             # Phase 3: Generalize before transfer
│   └── 04-integrate.md                   # Phase 4: Update toolkit index
├── references/
│   ├── artifact-categories.md            # 7 artifact types with criteria
│   ├── maturity-model.md                 # Artifact lifecycle & versioning
│   └── decontextualization-guide.md      # How to generalize artifacts
├── templates/
│   ├── toolkit-harvest.md                # TOOLKIT_HARVEST.md for projects
│   ├── artifact-card.md                  # Universal artifact documentation
│   └── harvest-report.md                 # Harvest session output report
└── examples/
    └── rate-limiting-extraction.md       # End-to-end extraction example
```

## External Dependencies (loaded via view() at runtime)

| Skill | When Used | Purpose |
|-------|-----------|---------|
| `explore` | Phase 1 (if scope unclear) | Clarify what to extract |
| `brutal-honesty-review` | Phase 3 (quality check) | BS-detect unworthy artifacts |
| `pipeline-forge` | Phase 4 (if creating new skills) | Structure new skills properly |

**Fallbacks:**
- `explore` unavailable → built-in 3 clarification questions
- `brutal-honesty-review` unavailable → built-in quality checklist
- `pipeline-forge` unavailable → use `templates/artifact-card.md` directly

## When to Use

**Trigger Patterns:**
- "harvest this project" / "extract knowledge"
- "toolkit harvest" / "harvest session"
- "что забрать в тулкит" / "ритуал извлечения"
- "обобщи паттерны из проекта"
- After merging final PR / tagging release / completing sprint
- When `TOOLKIT_HARVEST.md` exists in project

**Two Extraction Moments:**

| Moment | Effort | Duration | Output |
|--------|--------|----------|--------|
| **During work** | 30 seconds per marker | Continuous | `TOOLKIT_HARVEST.md` markers |
| **After completion** | Dedicated session | 30-60 minutes | Generalized toolkit artifacts |

## Operating Modes

| Mode | Triggers | Checkpoints | Time |
|------|----------|-------------|------|
| **MARKER** | "mark for harvest", "пометь" | 0 | ~30 sec |
| **QUICK** | "quick harvest", "auto" | 1 | ~15 min |
| **FULL** | "full harvest", "harvest session" | 4 | ~45 min |
| **AUDIT** | "audit toolkit", "check maturity" | 1 | ~10 min |

## Pipeline

```
INPUT: Project codebase + TOOLKIT_HARVEST.md (optional)
                    ↓
  MODE: MARKER ──→ Append to TOOLKIT_HARVEST.md ──→ DONE
                    ↓
  PHASE 1: AGENT REVIEW (swarm)
    Parallel agents scan: code, patterns, commands, errors, workarounds
    → Raw Findings List
    ⏸️ CHECKPOINT 1
                    ↓
  PHASE 2: CLASSIFY
    Map findings to 7 artifact categories
    Filter: what belongs, what doesn't
    → Classified Artifact List
    ⏸️ CHECKPOINT 2
                    ↓
  PHASE 3: DECONTEXTUALIZE
    Generalize each artifact: remove project specifics
    Document: when to use, prerequisites, maturity
    Quality check: is it truly reusable?
    → Generalized Artifacts
    ⏸️ CHECKPOINT 3
                    ↓
  PHASE 4: INTEGRATE
    Write artifacts to toolkit structure
    Update toolkit index (CLAUDE.md or manifest)
    Set maturity level, record provenance
    → Updated Toolkit
    ⏸️ CHECKPOINT 4 (FINAL)
                    ↓
  OUTPUT: Harvest Report + Updated Toolkit
```

## Execution Protocol

### Mode: MARKER (continuous, during work)

When user notices something worth extracting:

1. Check if `TOOLKIT_HARVEST.md` exists in project root
2. If not, create from `templates/toolkit-harvest.md`
3. Append the marker under the appropriate category
4. Done — no interruption to workflow

**Example:**
```markdown
## Паттерны
- [ ] Retry с exponential backoff — получился универсальнее, см. src/utils/retry.ts
```

---

### Phase 1: AGENT REVIEW

Read module: `modules/01-agent-review.md`

**Goal:** Find all extractable knowledge in the project using parallel agents.

**Swarm Strategy — 5 parallel extraction agents:**

| Agent | Scope | What It Looks For |
|-------|-------|-------------------|
| `extractor-patterns` | Architecture & code patterns | Reusable architectural patterns, middleware, error handling |
| `extractor-commands` | Scripts & CLI utilities | Slash commands, build scripts, dev utilities |
| `extractor-rules` | Constraints & workarounds | Edge cases, "don't do X because Y", library quirks |
| `extractor-templates` | File structures & configs | Reusable configs, project templates, scaffolds |
| `extractor-snippets` | Code fragments | Universal functions, helpers, one-liners |

**Each agent:**
1. Scans relevant parts of the codebase
2. Reads `TOOLKIT_HARVEST.md` markers (if exists)
3. Returns list of candidates with file references

**Merge strategy:** Deduplicate, combine related findings.

**Output — Raw Findings List:**
```markdown
## Raw Findings

| # | Finding | Source File | Category (tentative) | Agent |
|---|---------|------------|---------------------|-------|
| 1 | Universal retry with backoff | src/utils/retry.ts | Pattern | extractor-patterns |
| 2 | /db-migrate command | scripts/migrate.sh | Command | extractor-commands |
| 3 | Don't use nested generics >3 | multiple | Rule | extractor-rules |
```

**Checkpoint:**
```
═══════════════════════════════════════════════════════════════
✅ PHASE 1: AGENT REVIEW COMPLETE
Found: [N] candidates from [M] agents
⏸️ "ок" — classify | "добавь [finding]" | "убери #N"
═══════════════════════════════════════════════════════════════
```

---

### Phase 2: CLASSIFY

Read module: `modules/02-classify.md`

**Goal:** Map each finding to one of 7 artifact categories and filter out non-extractables.

**7 Artifact Categories:**

| Category | Directory | What Goes Here | Example |
|----------|-----------|---------------|---------|
| **Skills** | `skills/` | New or improved SKILL.md | Better DB migration technique |
| **Commands** | `commands/` | Slash commands for Claude Code | `/api-endpoint` generates CRUD |
| **Hooks** | `hooks/` | Pre-commit, post-task automation | Auto-validate OpenAPI schema |
| **Rules** | `rules/` | Constraints and limitations | "Don't use X pattern because Y" |
| **Templates** | `templates/` | Reusable file/project structures | Updated Dockerfile template |
| **Patterns** | `patterns/` | Architectural approaches as docs | Event sourcing + CQRS pattern |
| **Snippets** | `snippets/` | Small ready-to-use code fragments | Universal error handler |

See `references/artifact-categories.md` for detailed criteria.

**Exclusion Filter — Do NOT extract:**
- Domain-specific code that doesn't generalize
- Patterns used once and unvalidated
- Library-specific workarounds (they age badly)
- Secrets, credentials, API keys
- Hardcoded business logic

**Output — Classified Artifact List:**
```markdown
## Classified Artifacts

### ✅ Extract (N artifacts)
| # | Artifact | Category | Confidence | Notes |
|---|----------|----------|------------|-------|
| 1 | Retry with backoff | Pattern | HIGH | Universal, works with any HTTP client |
| 2 | /db-migrate | Command | MEDIUM | Needs decontextualization |

### ❌ Skip (M items)
| # | Finding | Reason |
|---|---------|--------|
| 3 | Auth middleware | Domain-specific, not generalizable |
```

**Checkpoint:**
```
═══════════════════════════════════════════════════════════════
✅ PHASE 2: CLASSIFICATION COMPLETE
Extract: [N] artifacts | Skip: [M] items
Categories: Skills [X], Commands [Y], Patterns [Z], ...
⏸️ "ок" — decontextualize | "переклассифицируй #N" | "верни #M"
═══════════════════════════════════════════════════════════════
```

---

### Phase 3: DECONTEXTUALIZE

Read module: `modules/03-decontextualize.md`

**Goal:** Transform project-specific artifacts into reusable, documented toolkit entries.

**The 3-Step Decontextualization:**

1. **Remove project specifics** — replace concrete names, paths, configs with parameters/placeholders
2. **Document usage** — when to use, when NOT to use, prerequisites, variants
3. **Version & provenance** — maturity level, source project, changelog

See `references/decontextualization-guide.md` for detailed process.

**Quality Gate (per artifact):**

| Check | Threshold | Blocking? |
|-------|-----------|-----------|
| No project-specific references | 0 remaining | Yes |
| "When to use" section present | Must exist | Yes |
| At least 1 usage variant | Must exist | No |
| Code compiles/runs standalone | Must pass | Yes (for code) |
| Maturity level assigned | Must exist | Yes |

**If `brutal-honesty-review` available:**
Apply Bach-mode BS detection: "Is this actually reusable, or are we fooling ourselves?"

**Output — Generalized Artifacts:**
Each artifact documented using `templates/artifact-card.md` format.

**Checkpoint:**
```
═══════════════════════════════════════════════════════════════
✅ PHASE 3: DECONTEXTUALIZATION COMPLETE
Generalized: [N] artifacts
Quality gate: [M] passed, [K] need fixes
⏸️ "ок" — integrate | "доработай #N" | "покажи #N"
═══════════════════════════════════════════════════════════════
```

---

### Phase 4: INTEGRATE

Read module: `modules/04-integrate.md`

**Goal:** Write artifacts to toolkit and update the index.

**Process:**
1. For each artifact, write to appropriate toolkit location
2. If artifact already exists → merge (update version, add variants)
3. Update toolkit index (CLAUDE.md or manifest file)
4. Record provenance (source project, date, version)
5. Generate Harvest Report

**Maturity Assignment:**
See `references/maturity-model.md`

| Level | Symbol | Meaning |
|-------|--------|---------|
| Alpha | 🔴 | First extraction, untested outside source project |
| Beta | 🟡 | Used in 2+ projects, edge cases found |
| Stable | 🟢 | Used in 3+ projects, documented, trustworthy |

**Toolkit Index Format:**
```markdown
## Toolkit Index

### Skills
| Skill | Maturity | Last Updated | Source |
|-------|----------|-------------|--------|

### Patterns
| Pattern | Maturity | Last Updated | Source |
|---------|----------|-------------|--------|

### Commands
| Command | Maturity | Last Updated | Source |
|---------|----------|-------------|--------|

[... for each category]

Last harvest: [DATE]
```

**Output — Harvest Report:**
See `templates/harvest-report.md`

**Final Checkpoint:**
```
═══════════════════════════════════════════════════════════════
✅ HARVEST COMPLETE

📊 Results:
- Scanned: [N] files
- Found: [M] candidates
- Extracted: [K] artifacts
  - Skills: [X] | Patterns: [Y] | Commands: [Z]
  - Rules: [A] | Templates: [B] | Snippets: [C] | Hooks: [D]
- Maturity: 🔴 Alpha: [N] | 🟡 Beta: [M] | 🟢 Stable: [K]

📁 Written to: [toolkit path]
📋 Report: [report path]

🔄 Automation tip:
  Add to git hooks or CI to remind about harvest on release.
═══════════════════════════════════════════════════════════════
```

---

## Automation Hook

To ensure harvest happens naturally, add this to project's `.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "pattern": "git tag v",
        "command": "echo '🌾 Release tagged. Consider running /harvest for toolkit extraction.'"
      }
    ]
  }
}
```

Or as a git hook reminder:
```bash
# .git/hooks/post-merge (on merge to main)
echo "🌾 Merge to main complete. Run '/harvest' to extract reusable knowledge."
```

## Integration with Other Skills

| Skill | Integration Point | Purpose |
|-------|-------------------|---------|
| `explore` | Phase 1 (scope) | Clarify what's worth extracting |
| `brutal-honesty-review` | Phase 3 (quality) | BS-detect unworthy artifacts |
| `pipeline-forge` | Phase 4 (skills) | Properly structure new skills |
| `requirements-validator` | Phase 3 (validation) | Validate extracted requirements |
| `problem-solver-enhanced` | Phase 3 (conflicts) | Resolve generalization conflicts via TRIZ |

## Anti-Patterns

❌ **Just copying** — artifacts must be decontextualized, not copy-pasted
❌ **Extracting everything** — if it's domain-specific, it doesn't belong
❌ **No documentation** — undocumented artifacts become technical debt
❌ **Skipping maturity** — trust level must be explicit
❌ **One-time use patterns** — wait for 2+ projects before promoting to Beta
❌ **Library workarounds** — they expire; only add as temporary rules with review dates
❌ **Heroic quarterly reviews** — extract continuously, harvest frequently
❌ **No provenance** — always record source project and date

## Quality Standards

- [ ] Every artifact has "When to use" section
- [ ] Every artifact has maturity level (🔴/🟡/🟢)
- [ ] No project-specific references in generalized artifacts
- [ ] Toolkit index is up to date
- [ ] Exclusion list applied (no domain code, no unvalidated patterns)
- [ ] Provenance recorded (source project, version, date)
- [ ] At least one usage variant documented

## Checkpoint Commands

| Command | Action | Available |
|---------|--------|-----------|
| `ок` / `далее` | Next phase | All |
| `добавь [finding]` | Add manual finding | Phase 1 |
| `убери #N` | Remove finding | Phase 1-2 |
| `переклассифицируй #N` | Change category | Phase 2 |
| `верни #M` | Un-skip excluded item | Phase 2 |
| `доработай #N` | Improve artifact | Phase 3 |
| `покажи #N` | Preview artifact | Phase 3-4 |
| `стоп` | Pause with save | All |
