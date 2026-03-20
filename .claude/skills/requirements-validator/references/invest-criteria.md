# INVEST Criteria Deep Dive

## Scoring Weights

| Criterion | Weight | Max Points |
|-----------|--------|------------|
| Independent | 8% | 8 |
| Negotiable | 8% | 8 |
| Valuable | 10% | 10 |
| Estimable | 8% | 8 |
| Small | 8% | 8 |
| Testable | 8% | 8 |
| **Total** | **50%** | **50** |

## Independent (8%)

**Definition**: Story can be developed, tested, and delivered separately from other stories.

**Pass criteria**:
- No explicit dependencies on unfinished stories
- Can be demo'd in isolation
- No "after X is complete" language

**Red flags**:
- "This story depends on US-XXX"
- "After the authentication module is done..."
- "Requires database schema from US-YYY"

**Fix pattern**: Split coupled stories or merge if inseparable.

## Negotiable (8%)

**Definition**: Implementation details are open to discussion, not prescribed.

**Pass criteria**:
- Describes WHAT, not HOW
- Leaves room for technical decisions
- Focuses on outcome, not mechanism

**Red flags**:
- "Must use React"
- "Implement with microservices"
- "Store in PostgreSQL table X"

**Fix pattern**: Remove implementation details. Move to technical notes if needed.

## Valuable (10%)

**Definition**: Delivers clear value to user or business.

**Pass criteria**:
- Has "so that [benefit]" clause
- Benefit is concrete and measurable
- Connects to business objective

**Red flags**:
- Missing "so that" clause
- Vague benefits: "improve experience"
- Technical tasks disguised as stories

**Fix pattern**: Add explicit benefit. If no user value, convert to technical task.

## Estimable (8%)

**Definition**: Team can estimate effort with reasonable confidence.

**Pass criteria**:
- Scope is well-defined
- Technical approach is understood
- No major unknowns

**Red flags**:
- "System should be fast" (unmeasurable)
- "Handle all edge cases" (unbounded)
- References unknown external systems

**Fix pattern**: Add specifics. Create spike if too many unknowns.

## Small (8%)

**Definition**: Fits within one sprint (typically 1-5 days of work).

**Pass criteria**:
- Single, focused feature
- Can be completed by 1-2 developers
- Has finite scope

**Red flags**:
- "Entire module"
- "All users"
- "Complete overhaul"
- Multiple acceptance criteria covering different features

**Fix pattern**: Decompose into smaller stories. Use story mapping.

## Testable (8%)

**Definition**: Has clear, verifiable acceptance criteria.

**Pass criteria**:
- Acceptance criteria exist
- Pass/fail is deterministic
- Can be automated

**Red flags**:
- No acceptance criteria
- Subjective criteria: "looks good"
- Unmeasurable outcomes

**Fix pattern**: Add Given/When/Then acceptance criteria with specific values.

## Validation Checklist

```
□ Independent: No blocking dependencies?
□ Negotiable: Describes outcome, not implementation?
□ Valuable: Clear user/business benefit?
□ Estimable: Team can size it?
□ Small: Fits in one sprint?
□ Testable: Has verifiable acceptance criteria?
```
