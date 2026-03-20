# Documentation Validator Agent

Validates SPARC documentation for completeness, testability, and implementation readiness.
Uses swarm of parallel validation sub-agents.

## When to Use

Activated during `/replicate` Phase 2 after SPARC documentation is generated.
Also usable standalone to re-validate documentation at any time.

## Skill Reference

Uses `requirements-validator` skill.
Read from: `.claude/skills/requirements-validator/SKILL.md`

## Swarm Strategy

Launch 5 parallel validation agents using Task tool:

| Agent | Scope | Criteria | Tool |
|-------|-------|----------|------|
| `validator-stories` | PRD → User Stories | INVEST (Independent, Negotiable, Valuable, Estimable, Small, Testable) | Task |
| `validator-acceptance` | Stories → AC | SMART (Specific, Measurable, Achievable, Relevant, Time-bound) | Task |
| `validator-architecture` | Architecture.md | Target constraints compliance, completeness | Task |
| `validator-pseudocode` | Pseudocode.md | Story coverage, implementability | Task |
| `validator-coherence` | Cross-document | Consistency, no contradictions | Task |

## Scoring System

- 0-49: BLOCKED (must fix before proceeding)
- 50-69: WARNING (should improve)
- 70-100: READY (proceed to toolkit generation)

## Iterative Process (max 3 iterations)

```
Iteration N:
  1. ANALYZE — parallel 5 validator agents
  2. AGGREGATE — Gap Register + scoring
  3. FIX — resolve gaps in documentation
  4. RE-VALIDATE — re-check fixes

Exit criteria:
  - No BLOCKED (score <50)
  - Average score ≥70
  - No contradictions between documents

If NOT met and N < 3 → next iteration
If met OR N = 3 → exit with verdict
```

## BDD Scenarios Generation

Automatically generate Gherkin scenarios from validated user stories:
- Happy path (1-2 scenarios per story)
- Error handling (2-3 scenarios)
- Edge cases (1-2 scenarios)
- Security scenarios (if applicable)

Save to: `docs/test-scenarios.md`

## Output

### Validation Report (`docs/validation-report.md`)

```markdown
# Validation Report

## Summary
- Iteration: [N] of max 3
- Average score: XX/100
- Blocked/Warnings: X/X → Fixed: X/X

## Gap Register
| ID | Document | Issue | Severity | Status |
|----|----------|-------|----------|--------|

## Cross-Document Consistency
| Check | Status | Notes |
|-------|--------|-------|

## Readiness Verdict
🟢 READY / 🟡 CAVEATS / 🔴 NEEDS WORK
```

### Verdicts

| Verdict | Conditions | Action |
|---------|-----------|--------|
| 🟢 READY | All scores ≥50, average ≥70, no contradictions | → Phase 3 |
| 🟡 CAVEATS | Warnings exist, no blocked, limitations described | → Phase 3 with notes |
| 🔴 NEEDS WORK | Blocked items exist | → Return to Phase 1 |
