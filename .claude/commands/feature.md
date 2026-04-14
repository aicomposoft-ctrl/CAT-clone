# /feature <name> — 4-Phase Feature Lifecycle

## Usage
```
/feature content-scoring
/feature distribution-alerts
/feature excel-export
```

## Phase 0: Pre-flight

Verify required skills exist:
```
.claude/skills/sparc-prd-mini/SKILL.md        ← REQUIRED
.claude/skills/requirements-validator/SKILL.md ← REQUIRED
.claude/skills/brutal-honesty-review/SKILL.md  ← REQUIRED
.claude/skills/explore/SKILL.md               ← OPTIONAL
.claude/skills/goap-research-ed25519/SKILL.md  ← OPTIONAL
```

**ABORT** if any REQUIRED skill is missing.

## Phase 1: PLAN

1. If feature description is vague → run `explore` skill for clarification
2. Execute `sparc-prd-mini` skill:
   - Input: feature name + project context from `CLAUDE.md` + `docs/Architecture.md`
   - Output: `docs/features/<name>/sparc/` (9 SPARC documents)
3. Commit: `docs(feature): SPARC planning for <name>`

**Gate:** Are all 9 SPARC docs generated and internally consistent? If not, iterate.

## Phase 2: VALIDATE

Run 5 parallel validation agents using `requirements-validator` skill:
- Agent 1: User story completeness
- Agent 2: BDD scenario coverage
- Agent 3: Acceptance criteria clarity
- Agent 4: Technical feasibility
- Agent 5: Security/multi-tenant implications

**Gate:** Score ≥ 70/100 per user story. Zero BLOCKED items (score < 50).

Save to: `docs/features/<name>/validation-report.md`
Commit: `docs(feature): validation complete for <name>`

## Phase 3: IMPLEMENT

1. **Read** validated SPARC docs — treat as source of truth
2. Use parallel Tasks for independent work:
   ```
   Task("Implement API endpoint") || Task("Write DB migration") || Task("Write tests")
   ```
3. Each service module self-contained (import from `core/`, not sibling services)
4. Commit per logical unit: `feat(<name>): <what>`

**Gate:** All tests pass. `org_id` filter on every DB query verified.

## Phase 4: REVIEW

Run 5 parallel review agents using `brutal-honesty-review` skill:
- Agent 1: Code quality (Linus mode)
- Agent 2: Security (OWASP checklist)
- Agent 3: Multi-tenant isolation
- Agent 4: Performance (N+1, missing indexes)
- Agent 5: Test coverage

**Fix all Critical and Major issues before merging.**

Save to: `docs/features/<name>/review-report.md`
Commit: `docs(feature): review complete for <name>`

## Output Directory

```
docs/features/<name>/
├── sparc/
│   ├── PRD.md
│   ├── Specification.md
│   ├── Architecture.md
│   ├── Pseudocode.md
│   └── Refinement.md
├── validation-report.md
└── review-report.md
```
