# Feature Lifecycle Rule — CAT

## Protocol

Every non-trivial feature follows 4 phases via `/feature <name>`.

```
Phase 0: PRE-FLIGHT   → verify skills exist
Phase 1: PLAN         → sparc-prd-mini → 9 SPARC docs
Phase 2: VALIDATE     → requirements-validator → score >= 70
Phase 3: IMPLEMENT    → read docs → parallel Tasks → modular code
Phase 4: REVIEW       → brutal-honesty-review → fix criticals
```

## Phase Rules

### Phase 0 — Pre-flight
- Verify `.claude/skills/sparc-prd-mini/SKILL.md` exists → ABORT if missing
- Verify `.claude/skills/requirements-validator/SKILL.md` exists → ABORT if missing
- Verify `.claude/skills/brutal-honesty-review/SKILL.md` exists → ABORT if missing
- Warn if `explore` or `goap-research-ed25519` missing (optional but recommended)

### Phase 1 — Planning
- **SPARC docs are mandatory.** Never implement from memory.
- Output goes to: `docs/features/<feature-name>/sparc/`
- Run `explore` skill first if the feature description is vague
- Gate assessment: is the feature clear enough to plan? If not, ask clarifying questions
- Commit: `docs(feature): SPARC planning for <feature-name>`

### Phase 2 — Validation
- Run 5 parallel validation agents with `requirements-validator`
- Minimum score: **70/100** per user story
- Zero BLOCKED items (score < 50) allowed
- Maximum 3 validation iterations before escalating
- Save to: `docs/features/<feature-name>/validation-report.md`
- Commit: `docs(feature): validation complete for <feature-name>`

### Phase 3 — Implementation
- **Read validated SPARC docs FIRST** — treat as source of truth
- Use parallel Tasks for independent components:
  ```
  Task("Implement API endpoint") || Task("Write DB migration") || Task("Write tests")
  ```
- Each service module is self-contained (import from `core/`, not from sibling services)
- Commit per logical unit: `feat(<feature-name>): <what was done>`
- DB migration: always use Alembic, never raw SQL in application code

### Phase 4 — Review
- Run 5 parallel review agents with `brutal-honesty-review`
  - Agent 1: Code quality (Linus mode)
  - Agent 2: Security (OWASP checklist)
  - Agent 3: Multi-tenant isolation (every query has org_id filter?)
  - Agent 4: Performance (N+1 queries, missing indexes)
  - Agent 5: Test coverage (happy path + error paths present?)
- **Fix all Critical and Major issues before merging**
- Minor issues: document as follow-up tasks
- Save to: `docs/features/<feature-name>/review-report.md`
- Commit: `docs(feature): review complete for <feature-name>`

## Feature Directory Structure

```
docs/features/<feature-name>/
├── sparc/
│   ├── PRD.md
│   ├── Specification.md
│   ├── Architecture.md
│   ├── Pseudocode.md
│   ├── Refinement.md
│   └── ...
├── validation-report.md
└── review-report.md
```

## When to Skip Phases

| Skip | Condition | Still Required |
|------|-----------|----------------|
| Phase 0 | Skills verified in this session | — |
| Phase 1 | Feature is a 1-line bugfix | Phase 4 review |
| Phase 2 | Hotfix with zero new requirements | — |
| Phase 3 | N/A — always implement | — |
| Phase 4 | Only if ALL of: trivial change, no security implications, no DB changes | — |

**Rule: Never skip Phase 3 (implement) or Phase 4 (review) for features touching auth, multi-tenancy, scrapers, or ML pipelines.**
