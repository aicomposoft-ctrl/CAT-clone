# Skill Interface Protocol

Standard protocol for how skills discover, reference, and interact in this ecosystem.
All skills, orchestrators, and agents MUST follow these rules.

## 1. Skill Identity (Frontmatter)

Every `SKILL.md` MUST begin with YAML frontmatter containing:

```yaml
---
name: kebab-case-name          # REQUIRED — unique identifier
description: >                 # REQUIRED — what, when, triggers (2-5 sentences)
  What the skill does. When to use it. Trigger words/phrases.
version: "1.0"                 # RECOMMENDED — semver
maturity: production           # RECOMMENDED — see Maturity Tagging below
---
```

A skill without `name` and `description` in frontmatter is invalid.

## 2. view() Contract

Skills reference each other via `view()` — a read-only lookup that loads another skill's content at runtime.

**Rules:**
- `view()` is read-only. Never modify a referenced skill's files.
- Always resolve the path using the Path Mapping Rules below before reading.
- If the target file does not exist, apply the Fallback Protocol (section 6).
- Never inline another skill's content into your own SKILL.md. Always use view() at runtime.

**Syntax:**
```
view() .claude/skills/[skill-name]/SKILL.md
view() .claude/skills/[skill-name]/references/[file].md
```

## 3. Path Mapping Rules

Skills originating from claude.ai use `/mnt/` paths. Apply these rewrites in order:

| Source Pattern | Target Pattern | Notes |
|----------------|----------------|-------|
| `/mnt/skills/user/[name]/` | `.claude/skills/[name]/` | Skill root directories |
| `/mnt/user-data/uploads/` | `docs/` | User-uploaded documents |
| `/output/` | `docs/` or project root | Generated artifacts |

**Skill Name Aliases:** `goap-research` always resolves to `goap-research-ed25519`.

**Rewrite order:** Resolve aliases first, then apply path pattern mapping.

## 4. Module Interface Contract

Skills with `modules/` subdirectories MUST structure each module with these sections:

| Section | Required | Purpose |
|---------|----------|---------|
| **Input** | YES | Parameters with types, descriptions, required flag |
| **Process** | YES | Numbered steps describing the transformation |
| **Output** | YES | Artifacts produced, with location and format |
| **Quality Gate** | YES | Checks, thresholds, and whether they block |
| **Dependencies** | YES | External skills or system capabilities needed |
| **Reusability** | RECOMMENDED | How this module can be extracted or reused elsewhere |

Modules are numbered (`01-name.md`, `02-name.md`) to indicate execution order.
SKILL.md acts as orchestrator, referencing modules in sequence.

## 5. Dependency Declaration

Skills declare dependencies in a table within SKILL.md under `## External Dependencies (loaded via view() at runtime)`:

| Phase | Skill | Path | Required | Purpose |
|-------|-------|------|----------|---------|
| Phase 1 | explore | `.claude/skills/explore/SKILL.md` | OPTIONAL | Task clarification |

**Dependency types:**
- **REQUIRED** — skill will not function without it. Pipeline halts if missing.
- **OPTIONAL** — skill has a documented fallback if missing.

## 6. Fallback Protocol

Every OPTIONAL dependency MUST have a documented fallback immediately after the dependency table:

```markdown
**Fallbacks:**
- `explore` unavailable → built-in 3-5 clarification questions
```

**Rules:**
1. Check if the dependency's SKILL.md exists before loading.
2. REQUIRED and missing — halt with error naming the missing skill.
3. OPTIONAL and missing — execute fallback and log warning in output.
4. Never silently ignore a missing dependency.

## 7. Maturity Tagging

Skills declare maturity in frontmatter. Consumers use this to decide trust level.

| Level | Meaning | Safe to Depend On |
|-------|---------|-------------------|
| `experimental` | Prototype, interface may change | No — use with fallback only |
| `beta` | Functional, interface stabilizing | Yes — with fallback recommended |
| `production` | Stable, tested in pipelines | Yes — safe for REQUIRED dependencies |
| `deprecated` | Being replaced, will be removed | No — migrate to replacement |

**Rule:** REQUIRED dependencies SHOULD point to `production` or `beta` skills only.

## 8. Composition Rules

**Orchestrator skills** (e.g., `replicate-coordinator`, `pipeline-forge`):
- Invoke other skills in a defined phase sequence
- Own the checkpoint and context-passing logic
- Never duplicate skill logic — always delegate via view()
- Handle dependency resolution and fallbacks for the entire pipeline

**Foundation skills** (e.g., `explore`, `goap-research-ed25519`):
- Self-contained with no required cross-skill dependencies
- Provide a single well-defined capability
- Declare explicit input/output formats
- Can be used independently outside any pipeline

**Composite skills** (e.g., `sparc-prd-mini`, `cc-toolkit-generator-enhanced`):
- Combine multiple foundation skills to produce complex output
- Declare all dependencies (both required and optional)
- Split complex logic into `modules/` with SKILL.md as orchestrator

## 9. Output Path Convention

All skill output goes directly into the project. Never create a separate output directory.

| Artifact Type | Path |
|---------------|------|
| Documentation (SPARC, validation, BDD, features) | `docs/` |
| Plans | `docs/plans/` |
| Commands, Agents, Rules, Skills | `.claude/commands/`, `.claude/agents/`, `.claude/rules/`, `.claude/skills/` |
| Hooks config | `.claude/settings.json` |
| Project context | `CLAUDE.md` (root) |
| Scaffolds (Dockerfile, docker-compose, .gitignore) | Project root |

## Anti-Patterns

- Hardcoding `/mnt/` paths without a mapping table
- Using view() to write or modify another skill's files
- Declaring a dependency as OPTIONAL without providing a fallback
- Depending on an `experimental` skill as REQUIRED
- Duplicating another skill's logic instead of referencing via view()
- Creating output directories outside the project root
- Circular dependencies between skills (always detected, always blocked)
