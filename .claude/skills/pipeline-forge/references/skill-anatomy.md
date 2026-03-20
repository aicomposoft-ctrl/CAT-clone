# Skill Anatomy Reference

How to structure composable skills for Claude Code. Based on analysis of 8 production
skills from the PU Unicorn Replicate methodology.

---

## Minimum Viable Skill

The simplest possible skill:

```
skill-name/
└── SKILL.md
```

A single `SKILL.md` file with:

```markdown
---
name: my-skill
description: >
  One paragraph. What it does. When to use it. Trigger words.
---

# My Skill Name

One sentence of purpose.

## When to Use

- Trigger pattern 1
- Trigger pattern 2

## Input

[What the skill receives]

## Execution

1. Step 1
2. Step 2
3. Step 3

## Output

[Structured output format]
```

---

## Full Skill Structure

For complex skills:

```
skill-name/
├── SKILL.md                    # Entry point (REQUIRED)
├── references/                 # Supporting knowledge (OPTIONAL)
│   ├── methodology.md          # Frameworks, criteria, scoring
│   ├── best-practices.md       # Domain expertise
│   └── templates.md            # Reference templates
├── templates/                  # Output templates (OPTIONAL)
│   ├── output-template.md      # Template with {{PLACEHOLDERS}}
│   └── report-template.md
├── modules/                    # Sub-phases (OPTIONAL)
│   ├── 01-phase-one.md         # Numbered for ordering
│   ├── 02-phase-two.md
│   └── 03-phase-three.md
├── examples/                   # Few-shot examples (OPTIONAL)
│   └── example-output.md
└── scripts/                    # Executable helpers (OPTIONAL)
    └── helper.sh
```

---

## SKILL.md Sections (Recommended Order)

### 1. Frontmatter (REQUIRED)

```yaml
---
name: skill-name-kebab-case
description: >
  One paragraph (2-5 sentences). What the skill does, when to use it,
  trigger words/patterns. This appears in skill listings.
---
```

### 2. Title and Purpose (REQUIRED)

```markdown
# Skill Name: Short Description

One sentence explaining what this skill transforms (input → output).
```

### 3. Architecture (RECOMMENDED for complex skills)

```markdown
## Architecture

\`\`\`
skill-name/
├── SKILL.md
├── references/
│   └── ...
└── templates/
    └── ...
\`\`\`
```

### 4. External Dependencies (IF ANY)

```markdown
## External Dependencies (loaded via view() at runtime)

| Phase | Skill | Path | Purpose |
|-------|-------|------|---------|
| Phase 1 | explore | `.claude/skills/explore/SKILL.md` | Task clarification |

**Fallbacks:**
- `explore` unavailable → built-in 3-5 questions
```

### 5. When to Use (REQUIRED)

```markdown
## When to Use

**Trigger Patterns:**
- "keyword phrase 1"
- "keyword phrase 2"
- "keyword phrase 3" (also in Russian/other language if bilingual)

**Use Cases:**
- Use case 1
- Use case 2
```

### 6. Operating Modes (IF MULTIPLE)

```markdown
## Operating Modes

| Mode | Triggers | Checkpoints | Time |
|------|----------|-------------|------|
| AUTO | "auto", "fast" | 0 | ~5 min |
| MANUAL | "manual", "step by step" | N | ~20 min |
```

### 7. Workflow / Pipeline (REQUIRED)

```markdown
## Workflow

\`\`\`
INPUT → PHASE 1 → PHASE 2 → ... → OUTPUT
\`\`\`

### Phase 1: [Name]

**Goal:** [one sentence]

**Process:**
1. [step]
2. [step]

**Output:**
[structured format]

**Checkpoint (MANUAL mode):**
\`\`\`
═════════════════════════════════════════════
⏸️ CHECKPOINT 1: [Phase Name]
[summary]
"ок" — next | "уточни X" — clarify
═════════════════════════════════════════════
\`\`\`
```

### 8. Output Format (REQUIRED)

```markdown
## Output Format

\`\`\`markdown
## [Output Title]

### Section 1
[template]

### Section 2
| Column | Column |
|--------|--------|
\`\`\`
```

### 9. Anti-Patterns (RECOMMENDED)

```markdown
## Anti-Patterns

❌ [What NOT to do — reason]
❌ [What NOT to do — reason]
```

### 10. Quality Standards (RECOMMENDED)

```markdown
## Quality Standards

- [ ] Check 1
- [ ] Check 2
- [ ] Check 3
```

### 11. Integration Notes (IF APPLICABLE)

```markdown
## Integration Notes

After this skill, hand off to:
- `skill-A` for [purpose]
- `skill-B` for [purpose]
```

---

## Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Skill directory | `kebab-case` | `problem-solver-enhanced` |
| SKILL.md | Always uppercase | `SKILL.md` |
| References | `kebab-case.md` | `scoring-system.md` |
| Templates | `kebab-case.md` | `prd-template.md` |
| Modules | `NN-kebab-case.md` | `01-intelligence.md` |
| Examples | `descriptive-name.md` | `noom-cjm-example.md` |
| Scripts | `kebab-case.ext` | `assess-code.sh` |

---

## Skill Size Guidelines

| Complexity | SKILL.md Lines | Subdirectories | Example |
|------------|---------------|----------------|---------|
| Simple | 50-150 | None | `explore` |
| Medium | 150-400 | references/ | `requirements-validator` |
| Complex | 400-600 | references/ + templates/ | `sparc-prd-mini` |
| Very Complex | 300-400 + modules/ | All | `reverse-engineering-unicorn` |

**Rule:** If SKILL.md exceeds 600 lines, split logic into `modules/` and keep
SKILL.md as orchestrator (~200-300 lines).

---

## Frontmatter Description Tips

**Good descriptions include:**
- What the skill does (1 sentence)
- When to use it (conditions/triggers)
- Trigger words/phrases for auto-activation

**Example:**
```yaml
description: >
  Validate requirements for testability, completeness, and clarity using
  INVEST and SMART criteria. Generate BDD scenarios from user stories.
  Use when: validating user stories before development, checking acceptance
  criteria quality, generating Gherkin/BDD scenarios. Triggers: "validate
  requirements", "check user story", "generate BDD", "INVEST check".
  Blocks requirements with score <50 from proceeding.
```

---

## Checklist: Is My Skill Well-Structured?

- [ ] Has SKILL.md with frontmatter (name + description)
- [ ] Purpose is clear in 1 sentence
- [ ] Trigger patterns listed (when to activate)
- [ ] Input format documented
- [ ] Output format documented with template
- [ ] Execution steps are numbered and clear
- [ ] Anti-patterns listed (what NOT to do)
- [ ] If has dependencies → fallback strategy documented
- [ ] If complex → split into modules/
- [ ] If generates output → templates/ provided
- [ ] References are read-only knowledge, not executable logic
- [ ] No hardcoded paths (use path mapping if cross-environment)
