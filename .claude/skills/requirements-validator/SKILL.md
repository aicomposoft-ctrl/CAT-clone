---
name: requirements-validator
description: >
  Validate requirements for testability, completeness, and clarity using INVEST and SMART criteria.
  Generate BDD scenarios and acceptance criteria from user stories. Use when: (1) Validating user stories
  or requirements before development, (2) Checking acceptance criteria quality, (3) Generating Gherkin/BDD
  scenarios, (4) Analyzing requirements testability, (5) User says "validate requirements", "check user story",
  "generate BDD", "testability analysis", "INVEST check", "SMART criteria". Blocks requirements with score <50
  from proceeding to development.
---

# Requirements Validator

Validate requirements using INVEST + SMART criteria. Generate BDD scenarios. Block untestable requirements.

## Workflow

1. **Analyze** → Apply INVEST to user stories, SMART to acceptance criteria
2. **Score** → Calculate testability score (0-100)
3. **Generate** → Create BDD scenarios (happy path, errors, edge cases)
4. **Report** → Output validation results with actionable fixes

## Quick Reference

### INVEST Criteria (User Stories) — 50% weight

| Criterion | Question | Red Flags |
|-----------|----------|-----------|
| **I**ndependent | Can develop separately? | "after X is done", "depends on" |
| **N**egotiable | Open to discussion? | "must be exactly", rigid specs |
| **V**aluable | Clear user benefit? | No "so that" clause |
| **E**stimable | Can estimate effort? | "system should be fast" |
| **S**mall | Fits in one sprint? | "entire module", "all users" |
| **T**estable | Has pass/fail criteria? | No acceptance criteria |

### SMART Criteria (Acceptance Criteria) — 30% weight

| Criterion | Question | Red Flags |
|-----------|----------|-----------|
| **S**pecific | Clear, unambiguous? | "fast", "easy", "user-friendly" |
| **M**easurable | Has metrics? | No numbers/thresholds |
| **A**chievable | Technically feasible? | "100% uptime", "instant" |
| **R**elevant | Supports story goal? | Unrelated to user value |
| **T**ime-bound | Has timing context? | No response times |

### Vague Terms to Flag

Always flag these terms and suggest specific replacements:
- "fast" → "<200ms p95 response time"
- "easy" → "completed in <3 clicks"
- "user-friendly" → "passes usability test with >80% task completion"
- "secure" → "passes OWASP Top 10 security scan"
- "scalable" → "handles 10,000 concurrent users"
- "reliable" → "99.9% uptime SLA"

## Scoring System

| Score | Rating | Action | INVEST | SMART |
|-------|--------|--------|--------|-------|
| 90-100 | Excellent | Ready for dev | 6/6 ✓ | 5/5 ✓ |
| 70-89 | Good | Minor fixes | 5+/6 | 4+/5 |
| 50-69 | Fair | Needs work | 4/6 | 3/5 |
| **0-49** | **Poor** | **BLOCKED** | <4/6 | <3/5 |

**Score <50 = BLOCKED from development.** Provide rewrite suggestions.

## Output Format

### Requirements Analysis Report

```markdown
# Requirements Testability Analysis

## Summary
- Stories analyzed: X
- Average score: XX/100
- Blocked: X (score <50)

## Results

| Story | Title | Score | INVEST | SMART | Status |
|-------|-------|-------|--------|-------|--------|
| US-001 | ... | 92/100 | 6/6 ✓ | 5/5 ✓ | READY |
| US-002 | ... | 45/100 | 3/6 ✗ | 2/5 ✗ | BLOCKED |

## Detailed Analysis: US-002 (BLOCKED)

### INVEST Analysis
| Criterion | Pass | Issue |
|-----------|------|-------|
| Independent | ✓ | - |
| Valuable | ✗ | No user benefit stated |
| Testable | ✗ | No measurable criteria |

### SMART Analysis
| Criterion | Pass | Issue |
|-----------|------|-------|
| Specific | ✗ | "fast" is vague |
| Measurable | ✗ | No metrics |

### Suggestions
- Rewrite: "As a [user], I want [specific action] within [time], so that [benefit]"
- Add AC: "Given X, when Y, then Z within 200ms"
```

### Security Acceptance Criteria (10% bonus weight)

When requirements involve authentication, data storage, external APIs, or multi-tenancy,
apply additional security validation:

| Criterion | Check | Red Flags |
|-----------|-------|-----------|
| Input Validation | All user inputs sanitized? | No validation mentioned, "trust client" |
| Authentication | Auth mechanism specified? | "users can access", no auth context |
| Authorization | Access control defined? | No role/permission model |
| Data Protection | Sensitive data handling specified? | PII without encryption rules |
| Multi-Tenant Isolation | Tenant boundary enforced? | Shared queries, no tenant context |
| Secret Management | Secrets externalized? | Hardcoded keys, fallback defaults |
| Webhook Security | Signature verification? | "Accept POST", no HMAC |

**Scoring Bonus:** +5 points if security criteria present and specific, +0 if not applicable,
-10 if security-relevant requirement lacks any security criteria (BLOCKED if score drops below 50).

**Security BDD Scenarios:** For security-relevant requirements, ALWAYS generate:
- Auth bypass attempt scenario
- Input injection scenario (SQL, XSS, command)
- Cross-tenant access attempt (if multi-tenant)
- Rate limiting / brute force scenario (if auth endpoint)

### BDD Scenario Generation

For each requirement, generate scenarios covering:
1. **Happy path** (1-2 scenarios) — Primary success flow
2. **Error handling** (2-3 scenarios) — Validation, network, server errors
3. **Edge cases** (1-2 scenarios) — Boundaries, concurrent access
4. **Security** (1-3 scenarios) — Auth bypass, injection, cross-tenant, rate limiting

See `references/bdd-patterns.md` for Gherkin templates and examples.

## Detailed References

- **INVEST deep dive**: See `references/invest-criteria.md`
- **SMART deep dive**: See `references/smart-criteria.md`
- **BDD patterns**: See `references/bdd-patterns.md`
- **Scoring formula**: See `references/scoring-system.md`
