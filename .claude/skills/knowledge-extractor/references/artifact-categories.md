# Artifact Categories Reference

Detailed criteria for classifying extracted knowledge into 7 toolkit categories.

---

## Category 1: Skills

**Directory:** `skills/[name]/SKILL.md`

**What belongs:**
- New techniques or improved approaches to common tasks
- Multi-step workflows that can be reused across projects
- AI-assisted capabilities (Claude Code skill definitions)

**Criteria:**
- Involves a multi-step process (not a single function)
- Has clear input → transformation → output
- Can be described with trigger patterns
- Benefits from documentation (when to use, anti-patterns)

**Structure:** Follow `pipeline-forge` skill anatomy
```
skills/[name]/
├── SKILL.md
├── references/    (optional)
└── templates/     (optional)
```

**Examples:**
- Better database migration technique
- API integration pattern with retry + circuit breaker
- Testing strategy for event-driven systems

**NOT a skill:** A single utility function (→ snippet), a config file (→ template)

---

## Category 2: Commands

**Directory:** `commands/[name].md`

**What belongs:**
- Slash commands for Claude Code
- CLI utilities that automate common dev tasks
- Build/deploy/test shortcuts

**Criteria:**
- Invoked explicitly by the user (not automatic)
- Has clear arguments and expected output
- Saves significant time on repetitive tasks
- Works across different projects (not project-specific)

**Structure:** Claude Code command format
```markdown
---
description: What the command does. $ARGUMENTS: what it expects.
---

# /command-name $ARGUMENTS

## Steps
1. [step]
2. [step]
```

**Examples:**
- `/api-endpoint` generates CRUD for a resource
- `/db-migrate` runs migration with safety checks
- `/perf-check` profiles and reports performance

**NOT a command:** An automation trigger (→ hook), a file structure (→ template)

---

## Category 3: Hooks

**Directory:** `.claude/settings.json` or `.claude/hooks/`

**What belongs:**
- Pre-commit validation hooks
- Post-task automation (auto-format, auto-test)
- CI pipeline triggers
- Git hooks for quality gates
- Claude Code hooks (PreToolUse, PostToolUse, Stop)

**Criteria:**
- Triggered automatically (not manually invoked)
- Attached to a specific event (commit, merge, task completion)
- Enforces a quality standard or automates a chore
- Low overhead (runs fast, doesn't block workflow)

**Structure:**
```json
{
  "hooks": {
    "EventName": [{
      "matcher": "ToolName",
      "command": "echo 'hook output'"
    }]
  }
}
```

**Examples:**
- Auto-validate OpenAPI schema on save
- Run linter on pre-commit
- Remind about harvest on release tag
- Auto-commit insights on Stop

**NOT a hook:** A manual command (→ command), a constraint (→ rule)

---

## Category 4: Rules

**Directory:** `rules/[name].md`

**What belongs:**
- Constraints and limitations discovered empirically
- "Don't do X because Y" lessons
- Framework/language quirks worth remembering
- Security constraints
- Performance constraints
- AI (Claude Code) limitations and workarounds

**Criteria:**
- States a constraint, not a how-to
- Has a clear "because" (reason, not just assertion)
- Applies beyond the source project
- Saves future debugging time

**Structure:**
```markdown
# Rule: [Short Name]

## Rule
[Don't do X because Y]

## Why
[Technical explanation]

## Example (what goes wrong)
[Code or scenario]

## Correct Approach
[What to do instead]

## Scope
Universal | Language: [lang] | Framework: [fw]

## Expiry
Permanent | Check after [condition]
```

**Examples:**
- "Don't use nested generics >3 levels — Claude Code loses context"
- "Always use parameterized queries — never string concat for SQL"
- "Redis SCAN is O(N) — don't use for large keyspaces in hot path"

**NOT a rule:** A code pattern (→ pattern), an automation (→ hook)

---

## Category 5: Templates

**Directory:** `templates/[name]/` or standalone files

**What belongs:**
- Reusable file structures (Dockerfile, CI config, etc.)
- Project scaffold templates
- Configuration file templates
- Document templates (ADR, RFC, etc.)

**Criteria:**
- Has `{{PLACEHOLDERS}}` for project-specific values
- Works by filling in parameters, not rewriting
- Structure is more valuable than content
- Tested with at least one real project

**Structure:**
```markdown
# Template: [Name]

## Parameters
| Placeholder | Description | Default | Required |
|------------|-------------|---------|----------|
| {{NAME}} | [desc] | [default] | YES/NO |

## Template Content
[the actual template with placeholders]

## Usage
[how to use this template]
```

**Examples:**
- Dockerfile for Node.js + PostgreSQL
- GitHub Actions CI/CD pipeline
- ADR (Architecture Decision Record) template
- docker-compose.yml for dev environment

**NOT a template:** Code logic (→ snippet/pattern), a process (→ skill)

---

## Category 6: Patterns

**Directory:** `patterns/[name].md` or `docs/patterns/`

**What belongs:**
- Architectural approaches documented as knowledge
- Design patterns adapted to specific contexts
- Integration patterns between systems
- Error handling strategies
- Data access patterns

**Criteria:**
- Describes an APPROACH, not specific code
- Has multiple valid implementations
- Includes trade-offs and when-to-use/when-not
- More than just a code snippet — includes reasoning

**Structure:**
```markdown
# Pattern: [Name]

## Intent
[What problem this pattern solves]

## When to Use
[Conditions]

## When NOT to Use
[Anti-conditions]

## Structure
[Diagram or pseudocode]

## Implementation Variants
### Variant A: [context]
[implementation]

### Variant B: [context]
[implementation]

## Trade-offs
| Pro | Con |
|-----|-----|
| [+] | [-] |

## Related Patterns
[links to complementary or alternative patterns]
```

**Examples:**
- Rate limiting (in-memory vs. Redis-backed)
- Circuit breaker with fallback
- Event sourcing + CQRS
- Repository pattern with caching

**NOT a pattern:** Specific code (<50 lines → snippet), a constraint (→ rule)

---

## Category 7: Snippets

**Directory:** `snippets/[language]/[name].[ext]` or inline in docs

**What belongs:**
- Small, self-contained code fragments (<50 lines)
- Utility functions that solve common problems
- One-liners or short helpers
- Type definitions / interfaces that are universal

**Criteria:**
- Self-contained (works without project context)
- Under 50 lines of code
- Solves a common problem
- No domain-specific dependencies
- Can be copy-pasted and used immediately

**Structure:**
```markdown
# Snippet: [Name]

**Language:** [lang]
**Lines:** [N]
**Dependencies:** None | [list]

## Code
\`\`\`[lang]
[code]
\`\`\`

## Usage
[how and when to use]
```

**Examples:**
- Universal retry with exponential backoff
- Safe JSON parse with default
- Debounce/throttle function
- Type-safe environment variable reader

**NOT a snippet:** >50 lines (→ pattern), a process (→ skill), a config (→ template)

---

## Decision Flowchart

```
Start with a finding
    │
    ├── Is it a multi-step process/workflow?
    │   ├── YES → Skill or Command
    │   │   ├── User-invoked? → Command
    │   │   └── AI-assisted workflow? → Skill
    │   └── NO ↓
    │
    ├── Is it triggered automatically?
    │   ├── YES → Hook
    │   └── NO ↓
    │
    ├── Is it a constraint / "don't do X"?
    │   ├── YES → Rule
    │   └── NO ↓
    │
    ├── Is it a file/config structure?
    │   ├── YES → Template
    │   └── NO ↓
    │
    ├── Is it <50 lines of executable code?
    │   ├── YES → Snippet
    │   └── NO ↓
    │
    ├── Is it an architectural approach?
    │   ├── YES → Pattern
    │   └── NO → Reconsider extraction
    │
    └── END
```
