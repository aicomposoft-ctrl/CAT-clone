# {{AGENT_NAME}} Agent

{{ONE_SENTENCE_PURPOSE}}

## When to Use

{{ACTIVATION_CONDITIONS}}

## Skill Reference

Uses `{{SKILL_NAME}}` skill.
Read from: `.claude/skills/{{SKILL_NAME}}/SKILL.md`

## Responsibilities

1. **{{RESPONSIBILITY_1}}** — {{DESCRIPTION}}
2. **{{RESPONSIBILITY_2}}** — {{DESCRIPTION}}
3. **{{RESPONSIBILITY_3}}** — {{DESCRIPTION}}

## Scope

| Aspect | Value |
|--------|-------|
| Input | {{WHAT_AGENT_RECEIVES}} |
| Output | {{WHAT_AGENT_PRODUCES}} |
| Criteria | {{PASS_FAIL_CRITERIA}} |
| Independence | {{FULL_OR_DEPENDS_ON}} |

## Process

```
1. {{STEP_1}}
2. {{STEP_2}}
3. {{STEP_3}}
4. {{STEP_4}}
```

## Output Format

```markdown
## {{AGENT_NAME}} Report

### Summary
{{SUMMARY_TEMPLATE}}

### Findings
| Item | Status | Details |
|------|--------|---------|

### Verdict
{{VERDICT_FORMAT}}
```

## Anti-Hallucination Rules

- Search first — never answer from memory for facts
- Source attribution — every fact → URL
- "NOT FOUND" > fabrication
- Hypotheses marked with `[H]` tag
- Confidence score at end
