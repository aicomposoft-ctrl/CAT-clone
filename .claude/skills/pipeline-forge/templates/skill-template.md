---
name: {{SKILL_NAME}}
description: >
  {{DESCRIPTION_1_PARAGRAPH}}
  Triggers: {{TRIGGER_PATTERNS}}.
---

# {{SKILL_TITLE}}

{{ONE_SENTENCE_PURPOSE}}

## Architecture

```
{{SKILL_NAME}}/
├── SKILL.md
{{#IF_REFERENCES}}
├── references/
│   └── {{REFERENCE_FILES}}
{{/IF_REFERENCES}}
{{#IF_TEMPLATES}}
├── templates/
│   └── {{TEMPLATE_FILES}}
{{/IF_TEMPLATES}}
{{#IF_MODULES}}
├── modules/
│   └── {{MODULE_FILES}}
{{/IF_MODULES}}
```

{{#IF_EXTERNAL_DEPS}}
## External Dependencies (loaded via view() at runtime)

| Phase | Skill | Path | Purpose |
|-------|-------|------|---------|
| {{PHASE}} | {{SKILL}} | `.claude/skills/{{SKILL}}/SKILL.md` | {{PURPOSE}} |

**Fallbacks:**
- `{{SKILL}}` unavailable → {{FALLBACK_STRATEGY}}
{{/IF_EXTERNAL_DEPS}}

## When to Use

**Trigger Patterns:**
- "{{TRIGGER_1}}"
- "{{TRIGGER_2}}"
- "{{TRIGGER_3}}"

**Use Cases:**
- {{USE_CASE_1}}
- {{USE_CASE_2}}

## Operating Modes

| Mode | Triggers | Checkpoints | Time |
|------|----------|-------------|------|
| AUTO | "auto", "fast" | 0 | ~{{AUTO_TIME}} min |
| MANUAL | "manual", "step by step" | {{N_CHECKPOINTS}} | ~{{MANUAL_TIME}} min |

## Input

```markdown
{{INPUT_FORMAT}}
```

## Workflow

```
INPUT → {{PHASE_1}} → {{PHASE_2}} → ... → OUTPUT
```

### Phase 1: {{PHASE_1_NAME}}

**Goal:** {{PHASE_1_GOAL}}

**Process:**
1. {{STEP_1}}
2. {{STEP_2}}
3. {{STEP_3}}

**Output:**
```markdown
{{PHASE_1_OUTPUT_FORMAT}}
```

**Checkpoint (MANUAL mode):**
```
═══════════════════════════════════════════════════════════════
⏸️ CHECKPOINT 1: {{PHASE_1_NAME}}
{{SUMMARY}}
"ок" — next | "уточни X" — clarify
═══════════════════════════════════════════════════════════════
```

### Phase N: {{PHASE_N_NAME}}

<!-- Repeat phase template for each phase -->

## Output Format

```markdown
## {{OUTPUT_TITLE}}

### {{SECTION_1}}
{{TEMPLATE}}

### {{SECTION_2}}
| Column A | Column B |
|----------|----------|
```

## Anti-Patterns

❌ {{ANTI_PATTERN_1}} — {{REASON}}
❌ {{ANTI_PATTERN_2}} — {{REASON}}
❌ {{ANTI_PATTERN_3}} — {{REASON}}

## Quality Standards

- [ ] {{CHECK_1}}
- [ ] {{CHECK_2}}
- [ ] {{CHECK_3}}

## Checkpoint Commands

| Command | Action |
|---------|--------|
| `ок` / `далее` | Next phase |
| `уточни [topic]` | Clarify aspect |
| `добавь [element]` | Add element |
| `измени [element]` | Modify element |
| `стоп` | Save state, pause |
