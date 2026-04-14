# Pipeline Template: {{PIPELINE_NAME}}

Use this template to design a multi-phase pipeline orchestrator.
Fill in all `{{PLACEHOLDERS}}` with domain-specific content.

---

## Pipeline Overview

| Property | Value |
|----------|-------|
| Name | {{PIPELINE_NAME}} |
| Purpose | {{PURPOSE}} |
| Phases | {{N_PHASES}} |
| Quality Gates | {{N_GATES}} |
| Checkpoints | {{N_CHECKPOINTS}} |
| Estimated Time | {{TIME_ESTIMATE}} |

## Phase Map

```
INPUT: {{INPUT_DESCRIPTION}}
                    ↓
  PHASE 1: {{PHASE_1_NAME}}
    Skill: {{SKILL_1}}
    Output: {{OUTPUT_1}}
    ⏸️ CHECKPOINT 1
                    ↓
  PHASE 2: {{PHASE_2_NAME}}
    Skill: {{SKILL_2}}
    Output: {{OUTPUT_2}}
    Quality Gate: {{GATE_CRITERIA}}
    ⏸️ CHECKPOINT 2
                    ↓
  PHASE N: {{PHASE_N_NAME}}
    Skill: {{SKILL_N}}
    Output: {{OUTPUT_N}}
    ⏸️ FINAL CHECKPOINT
                    ↓
  OUTPUT: {{FINAL_OUTPUT_DESCRIPTION}}
```

## Context Flow

| From Phase | To Phase | Context Passed |
|-----------|----------|---------------|
| Phase 1 | Phase 2 | {{CONTEXT_1_TO_2}} |
| Phase 2 | Phase 3 | {{CONTEXT_2_TO_3}} |

## Skills Used

| Skill | Phase | Mode | Fallback |
|-------|-------|------|----------|
| {{SKILL_1}} | Phase 1 | {{MODE}} | {{FALLBACK}} |
| {{SKILL_2}} | Phase 2 | {{MODE}} | {{FALLBACK}} |

## Quality Gates

### Gate 1: After Phase {{N}}

| Criterion | Weight | Threshold |
|-----------|--------|-----------|
| {{CRITERION_1}} | {{WEIGHT}}% | ≥{{THRESHOLD}} |
| {{CRITERION_2}} | {{WEIGHT}}% | ≥{{THRESHOLD}} |

**Verdicts:**

| Verdict | Conditions | Action |
|---------|-----------|--------|
| 🟢 READY | All ≥ threshold, avg ≥ 70 | Proceed |
| 🟡 CAVEATS | Warnings, no blocked | Proceed with notes |
| 🔴 NEEDS WORK | Blocked items | Fix and re-validate |

**Iterative fix:** Max {{MAX_ITERATIONS}} iterations.

## Swarm Opportunities

### Swarm at Phase {{N}}

| Agent | Scope | Criteria | Independence |
|-------|-------|----------|-------------|
| {{AGENT_A}} | {{SCOPE}} | {{CRITERIA}} | Full |
| {{AGENT_B}} | {{SCOPE}} | {{CRITERIA}} | Full |
| {{AGENT_C}} | {{SCOPE}} | {{CRITERIA}} | Reads A,B |

## Git Discipline

| After Phase | Commit Message |
|------------|----------------|
| Phase 1 | `{{TYPE}}: {{MESSAGE}}` |
| Phase 2 | `{{TYPE}}: {{MESSAGE}}` |
| Final | `{{TYPE}}: {{MESSAGE}}` |

## Checkpoint Commands

| Command | Action | Available |
|---------|--------|-----------|
| `ок` / `далее` | Next phase | All |
| `превью [artifact]` | View artifact | All |
| `назад` | Return to previous | All |
| `стоп` | Pause with save | All |

## Error Handling

| Error | Phase | Recovery |
|-------|-------|----------|
| {{ERROR_1}} | Phase {{N}} | {{RECOVERY}} |
| {{ERROR_2}} | Phase {{N}} | {{RECOVERY}} |

## Master Validation Checklist

### Mandatory
- [ ] All phases have documented inputs/outputs
- [ ] Context flow is complete (no data gaps)
- [ ] Quality gates have blocking thresholds
- [ ] Checkpoints have user command reference
- [ ] Git commits defined for each phase
- [ ] Error handling documented

### Per Phase
- [ ] Phase {{N}}: {{CHECK}}

## Files Generated

```
{{PROJECT_STRUCTURE}}
├── .claude/
│   ├── skills/
│   │   └── {{GENERATED_SKILLS}}
│   ├── commands/
│   │   └── {{GENERATED_COMMANDS}}
│   ├── agents/
│   │   └── {{GENERATED_AGENTS}}
│   └── rules/
│       └── {{GENERATED_RULES}}
└── {{OTHER_FILES}}
```
