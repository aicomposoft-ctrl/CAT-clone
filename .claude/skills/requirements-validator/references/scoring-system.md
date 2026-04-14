# Testability Scoring System

## Score Calculation Formula

```
Total Score = INVEST Score (50%) + SMART Score (30%) + Quality Score (20%)
```

## INVEST Score Breakdown (50 points max)

| Criterion | Weight | Points | Calculation |
|-----------|--------|--------|-------------|
| Independent | 8% | 0-8 | Binary: 8 if pass, 0 if fail |
| Negotiable | 8% | 0-8 | Binary: 8 if pass, 0 if fail |
| Valuable | 10% | 0-10 | 10 if clear benefit, 5 if vague, 0 if missing |
| Estimable | 8% | 0-8 | 8 if estimable, 4 if partially, 0 if not |
| Small | 8% | 0-8 | 8 if sprint-sized, 4 if 2 sprints, 0 if larger |
| Testable | 8% | 0-8 | 8 if AC exist and clear, 4 if vague AC, 0 if none |

## SMART Score Breakdown (30 points max)

| Criterion | Weight | Points | Calculation |
|-----------|--------|--------|-------------|
| Specific | 6% | 0-6 | -2 per vague term found |
| Measurable | 8% | 0-8 | 8 if metrics exist, 4 if partial, 0 if none |
| Achievable | 6% | 0-6 | 6 if realistic, 3 if stretch, 0 if impossible |
| Relevant | 5% | 0-5 | 5 if connected to value, 0 if disconnected |
| Time-bound | 5% | 0-5 | 5 if timing specified, 0 if missing |

## Quality Score Breakdown (20 points max)

| Criterion | Weight | Points | Calculation |
|-----------|--------|--------|-------------|
| Traceability | 10% | 0-10 | 10 if linked to tests, 5 if partial, 0 if none |
| Completeness | 10% | 0-10 | See completeness rubric below |

### Completeness Rubric

| AC Coverage | Points |
|-------------|--------|
| Happy path + errors + edges | 10 |
| Happy path + errors | 7 |
| Happy path only | 4 |
| Incomplete happy path | 2 |
| No AC | 0 |

## Score Interpretation

| Score | Rating | Status | Action |
|-------|--------|--------|--------|
| 90-100 | Excellent | ✅ READY | Proceed to development |
| 70-89 | Good | ⚠️ REVIEW | Fix minor issues, then proceed |
| 50-69 | Fair | 🔶 REWORK | Significant clarification needed |
| **0-49** | **Poor** | **🚫 BLOCKED** | **Requires complete rewrite** |

## Quality Gate Rules

### BLOCKED (Score < 50)

Requirements scoring below 50 are **automatically blocked** from development.

**Mandatory actions**:
1. Identify all failing criteria
2. Provide specific rewrite suggestions
3. Generate improved AC examples
4. Require re-validation after fixes

### REVIEW (Score 50-69)

**Recommended actions**:
1. List all issues clearly
2. Suggest specific improvements
3. Allow development if product owner accepts risk

### READY (Score 70+)

**Actions**:
1. Generate BDD scenarios
2. Create traceability links
3. Proceed to development

## Example Score Calculation

**User Story**: "As a user, I want the system to be fast so I can work efficiently"

### INVEST Analysis

| Criterion | Score | Reasoning |
|-----------|-------|-----------|
| Independent | 8 | No dependencies stated |
| Negotiable | 8 | Implementation open |
| Valuable | 5 | Benefit is vague ("efficiently") |
| Estimable | 0 | Cannot estimate "fast" |
| Small | 0 | "System" scope undefined |
| Testable | 0 | No measurable criteria |
| **Subtotal** | **21/50** | |

### SMART Analysis (for "System responds fast")

| Criterion | Score | Reasoning |
|-----------|-------|-----------|
| Specific | 0 | "fast" is vague (-6) |
| Measurable | 0 | No metrics |
| Achievable | 3 | Probably possible |
| Relevant | 5 | Performance matters |
| Time-bound | 0 | No timing specified |
| **Subtotal** | **8/30** | |

### Quality Analysis

| Criterion | Score | Reasoning |
|-----------|-------|-----------|
| Traceability | 0 | No test links |
| Completeness | 2 | Incomplete happy path |
| **Subtotal** | **2/20** | |

### Final Score

```
Total = 21 + 8 + 2 = 31/100
Status: 🚫 BLOCKED
```

**Rewrite suggestion**:
"As a customer, I want the product search to return results within 200ms at p95, so I can quickly find items without waiting."

**Improved AC**:
```gherkin
Given 1000 concurrent users
And 100,000 products in the catalog
When a user searches for "laptop"
Then 95% of responses complete in <200ms
And all responses complete in <500ms
```
