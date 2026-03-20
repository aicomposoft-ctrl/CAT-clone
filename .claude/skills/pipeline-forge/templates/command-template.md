---
description: >
  {{COMMAND_DESCRIPTION}}
  $ARGUMENTS: {{ARGUMENTS_DESCRIPTION}}
---

# /{{COMMAND_NAME}} $ARGUMENTS

## Role

{{ROLE_DESCRIPTION}}

## Skills (loaded from .claude/skills/)

| Skill | Path | Phase |
|-------|------|-------|
| {{SKILL_1}} | `.claude/skills/{{SKILL_1}}/SKILL.md` | Phase {{N}} |
| {{SKILL_2}} | `.claude/skills/{{SKILL_2}}/SKILL.md` | Phase {{N}} |

## Pipeline

```
INPUT → [{{PHASE_1}}] → [{{PHASE_2}}] → ... → OUTPUT
         {{SKILL_1}}     {{SKILL_2}}
```

## Execution

### Start

1. Briefly explain the phases
2. Determine context from $ARGUMENTS
3. Begin with Phase 1

### Phase 1: {{PHASE_1_NAME}}

Read the skill: `.claude/skills/{{SKILL_1}}/SKILL.md`

**Goal:** {{GOAL}}

**Pass context:**
```yaml
{{CONTEXT_TO_PASS}}
```

**Output location:** `{{OUTPUT_PATH}}`

Git commit: `{{COMMIT_TYPE}}: {{COMMIT_MESSAGE}}`

**Checkpoint:**
```
═══════════════════════════════════════════════════════════════
✅ PHASE 1: {{PHASE_1_NAME}}
{{SUMMARY}}
⏸️ "ок" — next | "превью [filename]" — show file
═══════════════════════════════════════════════════════════════
```

### Phase N: {{PHASE_N_NAME}}

<!-- Repeat for each phase -->

## Checkpoint Commands

| Command | Action |
|---------|--------|
| `ок` | Next phase |
| `превью [filename]` | View generated file |

## Critical Rules

### ALWAYS
- Read skill SKILL.md before executing
- Checkpoint after each phase
- Write output to specified paths

### NEVER
- Don't skip validation phases
- Don't generate from memory (read docs)
- Don't overwrite existing template files
