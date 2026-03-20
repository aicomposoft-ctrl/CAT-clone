# Quality Gates Reference

Patterns for validation, scoring, verdicts, and blocking thresholds in AI pipelines.
Extracted from `requirements-validator` and `doc-validator` in PU Unicorn Replicate.

---

## What is a Quality Gate?

A quality gate is a checkpoint between pipeline phases that:
1. **Evaluates** output against defined criteria
2. **Scores** the output numerically
3. **Renders a verdict** (READY / CAVEATS / BLOCKED)
4. **Blocks progression** if quality is insufficient
5. **Provides actionable feedback** for improvement

---

## Gate Structure

```
PHASE OUTPUT
    ↓
┌──────────────────────┐
│    QUALITY GATE       │
│                       │
│  1. Apply Criteria    │ ← INVEST, SMART, custom
│  2. Score (0-100)     │ ← per-item and aggregate
│  3. Render Verdict    │ ← READY / CAVEATS / BLOCKED
│  4. Decision          │ ← proceed / fix / abort
│                       │
└──────────────────────┘
    ↓
NEXT PHASE (if READY/CAVEATS)
```

---

## Scoring System Design

### Scoring Scale

| Score | Rating | Meaning | Action |
|-------|--------|---------|--------|
| 90-100 | Excellent | Exceeds requirements | Proceed immediately |
| 70-89 | Good | Meets requirements | Proceed with minor notes |
| 50-69 | Fair | Partially meets | Fix issues, then proceed |
| **0-49** | **Poor** | **Fails requirements** | **BLOCKED — must fix** |

### Scoring Formula

```
total_score = Σ(criterion_weight × criterion_score) / Σ(weights)
```

**Example (requirements validation):**
```
score = (INVEST_score × 0.50) + (SMART_score × 0.30) + (coverage_score × 0.20)
```

### Per-Criterion Scoring

Each criterion is binary (pass/fail) or graduated:

**Binary example (INVEST):**
```
| Criterion | Pass | Issue |
|-----------|------|-------|
| Independent | ✓ | - |
| Negotiable | ✓ | - |
| Valuable | ✗ | No "so that" clause |
| Estimable | ✓ | - |
| Small | ✗ | "entire module" |
| Testable | ✗ | No acceptance criteria |

Score: 3/6 = 50% → 50 × 0.50 weight = 25 points
```

---

## Verdict System

### Three-Tier Verdicts

| Verdict | Symbol | Conditions | Action |
|---------|--------|-----------|--------|
| **READY** | 🟢 | All items ≥50, average ≥70, no contradictions | Proceed to next phase |
| **CAVEATS** | 🟡 | Warnings exist, no blocked items, limitations described | Proceed with notes |
| **NEEDS WORK** | 🔴 | Any blocked item (score <50) exists | Return to previous phase |

### Verdict Decision Logic

```
IF any_item.score < 50:
    verdict = NEEDS_WORK (🔴)
ELIF average_score < 70:
    verdict = NEEDS_WORK (🔴)
ELIF any_item.score < 70:
    verdict = CAVEATS (🟡)
ELSE:
    verdict = READY (🟢)
```

---

## Iterative Validation

When output fails a quality gate, use iterative fix-and-revalidate:

```
FOR iteration = 1 TO max_iterations (typically 3):
    1. ANALYZE — run all validators (parallel swarm)
    2. AGGREGATE — merge results, build Gap Register
    3. CHECK — apply verdict logic
    4. IF verdict == READY or CAVEATS:
         EXIT with verdict
    5. FIX — resolve gaps in source material
    6. RE-VALIDATE — go to step 1

IF max_iterations reached AND still NEEDS_WORK:
    EXIT with NEEDS_WORK + Gap Register
```

### Gap Register Format

```markdown
| ID | Source | Issue | Severity | Status | Fix |
|----|--------|-------|----------|--------|-----|
| G-001 | PRD.md | Missing NFRs | BLOCKED | Fixed | Added performance section |
| G-002 | Architecture.md | No DB schema | WARNING | Open | Needs data model |
```

---

## Common Quality Criteria

### For Requirements (INVEST)

| Criterion | Question | Red Flags |
|-----------|----------|-----------|
| **I**ndependent | Can develop separately? | "after X is done", "depends on" |
| **N**egotiable | Open to discussion? | "must be exactly", rigid specs |
| **V**aluable | Clear user benefit? | No "so that" clause |
| **E**stimable | Can estimate effort? | "system should be fast" |
| **S**mall | Fits in one sprint? | "entire module", "all users" |
| **T**estable | Has pass/fail criteria? | No acceptance criteria |

### For Acceptance Criteria (SMART)

| Criterion | Question | Red Flags |
|-----------|----------|-----------|
| **S**pecific | Clear, unambiguous? | "fast", "easy", "user-friendly" |
| **M**easurable | Has metrics? | No numbers/thresholds |
| **A**chievable | Technically feasible? | "100% uptime", "instant" |
| **R**elevant | Supports story goal? | Unrelated to user value |
| **T**ime-bound | Has timing context? | No response times |

### For Architecture

| Criterion | Question |
|-----------|----------|
| Constraints compliance | Matches target architecture (monolith/micro/etc.)? |
| Completeness | All layers covered (frontend, backend, DB, infra)? |
| Consistency | Tech stack choices don't contradict? |
| Security | Authentication, authorization, encryption addressed? |
| Scalability | Growth path defined? |

### For Cross-Document Consistency

| Check | What to verify |
|-------|---------------|
| Terminology | Same terms used across all documents? |
| Feature coverage | Every PRD feature has pseudocode + architecture? |
| Story coverage | Every user story has test scenario? |
| Stack alignment | Architecture.md stack matches Pseudocode.md assumptions? |
| Contradiction | No conflicting statements across documents? |

---

## Vague Terms Detection

Always flag these and suggest specific replacements:

| Vague Term | Specific Replacement |
|-----------|---------------------|
| "fast" | "<200ms p95 response time" |
| "easy" | "completed in <3 clicks" |
| "user-friendly" | "passes usability test with >80% task completion" |
| "secure" | "passes OWASP Top 10 security scan" |
| "scalable" | "handles 10,000 concurrent users" |
| "reliable" | "99.9% uptime SLA" |
| "responsive" | "renders above-the-fold in <1.5s on 3G" |
| "intuitive" | "zero training required, <30s to first action" |

---

## Validation Report Format

```markdown
# Validation Report

## Summary
- Items analyzed: [N]
- Average score: [XX]/100
- Blocked: [N] (score <50)
- Warnings: [N] (score 50-69)
- Ready: [N] (score ≥70)
- Iterations: [N] of max 3

## Results

| Item | Score | Criteria Met | Status |
|------|-------|-------------|--------|
| [item-1] | 92/100 | 6/6 INVEST, 5/5 SMART | READY |
| [item-2] | 45/100 | 3/6 INVEST, 2/5 SMART | BLOCKED |

## Gap Register

| ID | Source | Issue | Severity | Status |
|----|--------|-------|----------|--------|

## Cross-Document Consistency

| Check | Status | Notes |
|-------|--------|-------|

## Readiness Verdict

🟢 READY / 🟡 CAVEATS / 🔴 NEEDS WORK

[Explanation of verdict]
```

---

## Designing Custom Quality Gates

When creating a quality gate for a new domain:

1. **Identify criteria** — what makes output "good" in this domain?
2. **Weight criteria** — which matter most? (sum to 100%)
3. **Define scoring** — how to evaluate each criterion (binary or graduated)
4. **Set thresholds** — what score blocks progression?
5. **Define verdicts** — what are the possible outcomes?
6. **Design iteration** — how many fix cycles? Max iterations?
7. **Write report template** — what does the validation output look like?

### Template

```markdown
## Quality Gate: [Gate Name]

### Criteria (weighted)
| Criterion | Weight | Scoring | Threshold |
|-----------|--------|---------|-----------|
| [criterion-1] | 40% | 0-100 | ≥50 (blocking) |
| [criterion-2] | 30% | Pass/Fail | Must pass |
| [criterion-3] | 30% | 0-100 | ≥60 (warning) |

### Verdicts
| Verdict | Conditions | Action |
|---------|-----------|--------|
| READY | All ≥ thresholds, avg ≥ 70 | Proceed |
| CAVEATS | Warnings, no blocked | Proceed with notes |
| BLOCKED | Any below threshold | Fix and re-validate |

### Max Iterations: 3
```
