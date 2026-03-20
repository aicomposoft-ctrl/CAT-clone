# SMART Criteria for Acceptance Criteria

## Scoring Weights

| Criterion | Weight | Max Points |
|-----------|--------|------------|
| Specific | 6% | 6 |
| Measurable | 8% | 8 |
| Achievable | 6% | 6 |
| Relevant | 5% | 5 |
| Time-bound | 5% | 5 |
| **Total** | **30%** | **30** |

## Specific (6%)

**Definition**: Clear, unambiguous language with no room for interpretation.

**Pass criteria**:
- Concrete nouns and verbs
- Exact values and conditions
- No vague qualifiers

**Vague term mapping**:

| Vague Term | Specific Alternative |
|------------|---------------------|
| fast | <200ms p95 |
| slow | >2000ms |
| easy | <3 clicks/steps |
| user-friendly | 80%+ task completion rate |
| intuitive | no training required |
| responsive | <100ms interaction feedback |
| secure | passes OWASP Top 10 |
| robust | handles 10x normal load |
| efficient | <50MB memory usage |
| simple | single-page form |

**Fix pattern**: Replace every vague term with a measurable value.

## Measurable (8%)

**Definition**: Has quantifiable success criteria.

**Pass criteria**:
- Contains numbers, percentages, or counts
- Defines thresholds (min, max, exact)
- Can be verified automatically

**Examples**:
- ✗ "Page loads quickly" → ✓ "Page loads in <2s at p95"
- ✗ "Most users succeed" → ✓ "95% of users complete task"
- ✗ "Handles errors" → ✓ "Returns 4xx/5xx with error code and message"

**Fix pattern**: Add "how much", "how many", "how fast" to every criterion.

## Achievable (6%)

**Definition**: Technically feasible within constraints.

**Pass criteria**:
- Within current technology stack
- Resources available
- No physical impossibilities

**Red flags**:
- "100% uptime" (impossible)
- "Zero latency" (impossible)
- "Infinite scalability" (unbounded)
- "Works on all devices" (untestable)

**Fix pattern**: Add realistic bounds. "99.9% uptime" instead of "100%".

## Relevant (5%)

**Definition**: Directly supports the user story's value proposition.

**Pass criteria**:
- Connects to "so that" clause
- Tests user-facing behavior
- Not implementation detail

**Red flags**:
- Tests internal methods
- Checks database schemas
- Verifies code structure

**Fix pattern**: Reframe as user-observable behavior.

## Time-bound (5%)

**Definition**: Includes timing context where applicable.

**Pass criteria**:
- Response time requirements
- Timeout specifications
- Deadline/expiration handling

**Examples**:
- "API responds within 500ms"
- "Session expires after 30 minutes"
- "Email sent within 1 minute of registration"
- "Retry 3 times with 1s backoff"

**Fix pattern**: Add "within X time" for async operations and user-facing responses.

## AC Quality Checklist

```
□ Specific: No vague terms (fast, easy, etc.)?
□ Measurable: Contains numbers/thresholds?
□ Achievable: Technically possible?
□ Relevant: Supports user value?
□ Time-bound: Has timing requirements?
```

## AC Template

```gherkin
Given [precondition with specific values]
When [action with specific parameters]
Then [outcome with measurable result] within [time constraint]
```

**Example**:
```gherkin
Given a registered user with valid credentials
When they submit the login form
Then they are redirected to the dashboard within 2 seconds
And a session cookie is set expiring in 24 hours
```
