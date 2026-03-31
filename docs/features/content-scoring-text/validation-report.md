# Requirements Validation Report — Content Scoring: Text (multilingual-e5)

**Date:** 2026-03-31  
**Sprint:** 3b  
**Validator:** requirements-validator skill (INVEST + SMART + Security)

---

## Summary

| Metric | Value |
|--------|-------|
| Stories analyzed | 2 |
| Average score | 91/100 |
| Blocked (score <50) | 0 |
| Status | **PASS — ready for implementation** |

---

## Results

| Story | Title | Score | INVEST | SMART | Security | Status |
|-------|-------|-------|--------|-------|----------|--------|
| US-1 | Daily Text Scoring | 93/100 | 6/6 ✓ | 5/5 ✓ | +5 bonus | READY |
| US-2 | Per-row Text Scoring + content_total | 89/100 | 6/6 ✓ | 5/5 ✓ | +5 bonus | READY |

---

## Detailed Analysis

### US-1: Daily Text Scoring (93/100)

#### INVEST Analysis

| Criterion | Pass | Notes |
|-----------|------|-------|
| Independent | ✓ | Standalone Beat trigger, no prerequisite tasks declared |
| Negotiable | ✓ | 06:30 UTC timing discussed in context of image scoring (06:00) |
| Valuable | ✓ | Clear benefit: "full content quality picture by time I start work" |
| Estimable | ✓ | Mirrors existing image scoring orchestrator — effort well-bounded |
| Small | ✓ | Orchestrator-only story; per-row logic isolated in US-2 |
| Testable | ✓ | SQL verification query specified in ACs |

**Score: 6/6 ✓**

#### SMART Analysis

| Criterion | Pass | Notes |
|-----------|------|-------|
| Specific | ✓ | Filter condition spelled out: `scored_at = today() AND collected_description IS NOT NULL AND (description_score IS NULL OR composition_score IS NULL)` |
| Measurable | ✓ | "≥ 99% of matching rows scored within 5 min" — verifiable via SQL |
| Achievable | ✓ | Text scoring has no MinIO download — faster than image pipeline |
| Relevant | ✓ | Directly supports brand manager morning review workflow |
| Time-bound | ✓ | Beat trigger at 06:30 UTC; 5-minute SLA stated |

**Score: 5/5 ✓**

#### Security (Multi-tenant)
- Orchestrator query joins `content_scores → sku_platforms` but does not expose org_id in dispatched task args
- UUID uniqueness of sku_id provides namespace isolation in Redis keys
- **+5 bonus: isolation requirements explicitly stated**

#### BDD Scenarios

```gherkin
Scenario: Orchestrator dispatches tasks for unscored rows
  Given 50 content_scores rows for today with collected_description set
  And description_score IS NULL for all 50
  When score_text_content_all runs at 06:30 UTC
  Then 50 score_text_content tasks are dispatched via Celery group

Scenario: Orchestrator skips fully-scored rows (idempotency)
  Given 100 content_scores rows for today
  And 60 rows have description_score IS NOT NULL AND composition_score IS NOT NULL
  When score_text_content_all runs
  Then only 40 tasks are dispatched

Scenario: No rows to score — no group dispatched
  Given no content_scores rows match today's filter
  When score_text_content_all runs
  Then no Celery group is dispatched
  And INFO log "0 rows to score" is emitted
```

---

### US-2: Per-row Text Scoring + content_total (89/100)

#### INVEST Analysis

| Criterion | Pass | Notes |
|-----------|------|-------|
| Independent | ✓ | Single-row operation, no dependency on other per-row tasks |
| Negotiable | ✓ | Weights 0.40/0.35/0.25 and rounding rule (ROUND_HALF_UP) acknowledged as MVP constants |
| Valuable | ✓ | "Atomicity prevents misleading aggregated metrics" — business value clear |
| Estimable | ✓ | Algorithm explicit; mirrors image scoring per-row task |
| Small | ✓ | Single task, single DB row, single transaction |
| Testable | ✓ | Detailed ACs for each code path including NULL handling |

**Score: 6/6 ✓**

#### SMART Analysis

| Criterion | Pass | Notes |
|-----------|------|-------|
| Specific | ✓ | Model name, prefix string, dimension all explicit |
| Measurable | ✓ | `clamp(score, 0.0, 1.0).round(2)` — exact numeric contract |
| Achievable | ✓ | multilingual-e5-base already in embedding_tasks.py; pattern proven |
| Relevant | ✓ | Directly computes the scores brand managers view |
| Time-bound | ✓ | Same-transaction write; retry backoff capped (max_retries=3) |

**Score: 5/5 ✓**

#### Security (Multi-tenant)
- Redis keys scoped to `ref_emb:{sku_id}:{field}` — UUID uniqueness provides org isolation
- DB UPDATE scoped to `content_scores.id` (PK) — cannot overwrite other orgs' rows
- AC explicitly states: "DB UPDATE is scoped to content_scores.id (PK) — no cross-org write"
- **+5 bonus: isolation acceptance criteria present and testable**

#### BDD Scenarios

```gherkin
Scenario: Description scored, composition NULL
  Given cs_id=X, sku_id=SKU-A, description="premium olive oil", composition=None
  And ref_emb:SKU-A:desc exists in Redis (768-dim)
  When score_text_content runs
  Then description_score = cosine_sim(e5("query: premium olive oil"), ref) rounded to 2dp
  And composition_score remains NULL
  And content_total remains NULL (image_score not all-present)

Scenario: Both fields scored + content_total computed
  Given cs_id=X with image_score=0.85 already set
  And description="premium olive oil", composition="100% extra virgin"
  And ref_emb:SKU-A:desc and ref_emb:SKU-A:comp both in Redis
  When score_text_content runs
  Then description_score AND composition_score are written
  And content_total = round(0.40*0.85 + 0.35*desc_score + 0.25*comp_score, 2)
  And all three writes occur in a single DB transaction

Scenario: Redis missing for desc — skip desc, still score comp
  Given ref_emb:SKU-A:desc missing in Redis
  And ref_emb:SKU-A:comp present
  When score_text_content runs
  Then description_score is NOT written
  And composition_score IS written
  And WARNING log "no ref_emb:desc" is emitted

Scenario: Empty description after strip — skip desc scoring
  Given description = "   " (whitespace only)
  When score_text_content runs
  Then description_score is NOT written
  And INFO log "empty/null description" is emitted

Scenario: Cross-tenant isolation — Redis key namespace
  Given org A has sku_id=SKU-A, org B has sku_id=SKU-B
  When score_text_content runs for org A row
  Then Redis GET is called only for ref_emb:SKU-A:desc and ref_emb:SKU-A:comp
  And ref_emb:SKU-B:* keys are never accessed

Scenario: DB error triggers retry with backoff
  Given DB raises OperationalError on first UPDATE
  When score_text_content runs
  Then task retries with countdown=1s (attempt 1), 2s (attempt 2), 4s (attempt 3)
  And raises after 3 retries exhausted

Scenario: Zero-norm embedding raises ValueError — skip field
  Given e5 model returns all-zero vector for collected description
  When score_text_content runs
  Then ValueError is caught
  And description_score is NOT written
  And ERROR log emitted
```

---

## Validation Decision

**PASS** — both stories score ≥ 70/100 with 0 blocked items.

Implementation may proceed against this Specification as authoritative source of truth.

Key constraints to enforce during implementation:
1. `"query: "` prefix mandatory for all collected texts
2. Redis shape validation must be `(768,)` for desc/comp fields (not 512 from CLIP)
3. content_total written in **same** DB transaction as text scores
4. desc and comp failures are independent — one failing must not block the other
5. Orchestrator idempotency: filter excludes fully-scored rows
