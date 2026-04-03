# Validation Report: excel-export-stock

**Date:** 2026-04-02
**Phase:** 2 — Validation (retroactive, 5 parallel agents)
**Status:** Pass

---

## Scores

| Agent | Scope | Score | Verdict |
|-------|-------|-------|---------|
| 1 | INVEST Criteria — US-01 (Download report) | 88/100 | Pass |
| 2 | INVEST Criteria — US-02 (Date range filter) | 85/100 | Pass |
| 3 | INVEST Criteria — US-03 (Platform filter) | 80/100 | Pass |
| 4 | INVEST Criteria — US-04 (Color coding) | 82/100 | Pass |
| 5 | INVEST Criteria — US-05 (Plan vs Fact column) | 78/100 | Pass |

All scores above threshold (70). No BLOCKED items (score < 50).

---

## US-01: Download Stock Excel Report — Score 88/100

### INVEST Analysis

| Criterion | Score | Notes |
|-----------|-------|-------|
| **I**ndependent | 95 | No dependency on other in-flight features; reuses existing reports module |
| **N**egotiable | 80 | Sheet name "Stock", title text "Отчёт по дистрибуции", column headers are negotiable details that don't affect the contract |
| **V**aluable | 95 | Directly eliminates the manual VLOOKUP process; immediate ROI |
| **E**stimable | 90 | Pattern is proven (content-export exists); implementation time predictable |
| **S**mall | 85 | Single endpoint, no migration, no frontend changes |
| **T**estable | 85 | Acceptance criteria fully specified; 6 E2E tests already written and passing |

### SMART Acceptance Criteria

| Criterion | S | M | A | R | T |
|-----------|---|---|---|---|---|
| HTTP 200 with correct Content-Type | ✓ | ✓ | ✓ | ✓ | ✓ |
| Content-Disposition with dynamic filename | ✓ | ✓ | ✓ | ✓ | ✓ |
| Sheet named "Stock" | ✓ | ✓ | ✓ | ✓ | ✓ |
| Row 1 merged title cell | ✓ | ✓ | ✓ | ✓ | ✓ |
| Data at row 3, freeze panes A3 | ✓ | ✓ | ✓ | ✓ | ✓ |
| 401 for unauthenticated request | ✓ | ✓ | ✓ | ✓ | ✓ |

**Deduction (12 pts):** "No disk I/O" is verified indirectly (BytesIO pattern) but not asserted in tests.

---

## US-02: Filter by Date Range — Score 85/100

### INVEST Analysis

| Criterion | Score | Notes |
|-----------|-------|-------|
| **I**ndependent | 95 | Date params are standard HTTP query params |
| **N**egotiable | 85 | The 366-day limit is negotiable; exact error message text is negotiable |
| **V**aluable | 90 | Without a date filter the report would be unusably large |
| **E**stimable | 95 | `_validate_date_range` is a simple helper; already implemented |
| **S**mall | 90 | 12 lines of validation logic |
| **T**estable | 88 | Four distinct validation paths, each tested |

### SMART Acceptance Criteria

| Criterion | S | M | A | R | T |
|-----------|---|---|---|---|---|
| Missing params → 422 | ✓ | ✓ | ✓ | ✓ | ✓ |
| date_to < date_from → 400 with INVALID_DATE_RANGE | ✓ | ✓ | ✓ | ✓ | ✓ |
| Range > 366 days → 400 with INVALID_DATE_RANGE | ✓ | ✓ | ✓ | ✓ | ✓ |
| Empty range returns 200 (not 404) | ✓ | ✓ | ✓ | ✓ | ✓ |

**Deduction (15 pts):** No test for same-day range (`date_from == date_to`). No test verifying exactly 366 days is allowed while 367 is rejected (boundary case).

---

## US-03: Filter by Platform — Score 80/100

### INVEST Analysis

| Criterion | Score | Notes |
|-----------|-------|-------|
| **I**ndependent | 90 | Optional param; feature works without it |
| **N**egotiable | 85 | Optional behavior — absence means "all platforms" |
| **V**aluable | 85 | Large orgs on 110+ platforms need this filter to get usable files |
| **E**stimable | 95 | Same pattern as content-export platform filter; already implemented |
| **S**mall | 95 | One `.where()` clause addition |
| **T**estable | 72 | Valid UUID for wrong org returns empty workbook (not 403) — acceptable but not tested |

### SMART Acceptance Criteria

| Criterion | S | M | A | R | T |
|-----------|---|---|---|---|---|
| Absent platform_id → all platforms | ✓ | ✓ | ✓ | ✓ | ✓ |
| Invalid UUID format → 422 | ✓ | ✓ | ✓ | ✓ | ✓ |
| Wrong-org platform UUID → 200 empty workbook | ✓ | ✓ | ✓ | Partial | ✓ |

**Deduction (20 pts):** The "wrong-org platform UUID → empty workbook" behavior is documented in the spec but has no dedicated test. Agent notes this is a security-adjacent behavior that should be verified.

---

## US-04: Color-Coded Rows — Score 82/100

### INVEST Analysis

| Criterion | Score | Notes |
|-----------|-------|-------|
| **I**ndependent | 95 | Pure rendering concern; no external dependencies |
| **N**egotiable | 80 | Specific hex values (#C6EFCE, #FFC7CE) are negotiable; the green/red semantic is not |
| **V**aluable | 85 | Color coding is the primary UX benefit of the Excel format over CSV |
| **E**stimable | 95 | `_stock_row_fill` is a simple 3-branch function |
| **S**mall | 90 | 5 lines of pure logic |
| **T**estable | 88 | Three fill branches tested: green, red, no-fill |

### SMART Acceptance Criteria

| Criterion | S | M | A | R | T |
|-----------|---|---|---|---|---|
| in_stock=True → all 10 cols green #C6EFCE | ✓ | ✓ | ✓ | ✓ | ✓ |
| in_stock=False → all 10 cols red #FFC7CE | ✓ | ✓ | ✓ | ✓ | ✓ |
| in_stock=None → no fill | ✓ | ✓ | ✓ | ✓ | Partial |

**Deduction (18 pts):** The "no fill" test uses a flexible assertion (`fill_type in (None, "none", "patternType")`) because `openpyxl` returns different representations for "no fill" depending on version. This is a test fragility issue, not a behavioral issue.

---

## US-05: Plan vs Fact Column — Score 78/100

### INVEST Analysis

| Criterion | Score | Notes |
|-----------|-------|-------|
| **I**ndependent | 80 | Depends on distribution_plans table existing (it does) |
| **N**egotiable | 85 | Column name "План (ТТ)" and "—" placeholder are negotiable |
| **V**aluable | 95 | This is the core differentiating feature — combines two data sources |
| **E**stimable | 80 | LEFT JOIN on func.extract is slightly complex but documented |
| **S**mall | 75 | The JOIN condition involves 4 matching keys including computed expressions |
| **T**estable | 72 | LEFT JOIN behavior tested at workbook level (pre-built StockRow with plan_tt_count=None) but not at repository level with real DB |

### SMART Acceptance Criteria

| Criterion | S | M | A | R | T |
|-----------|---|---|---|---|---|
| Plan exists for week → plan_tt_count shown as string | ✓ | ✓ | ✓ | ✓ | ✓ |
| No plan for week → "—" in Plan (ТТ) cell | ✓ | ✓ | ✓ | ✓ | ✓ |
| Stock rows always appear (LEFT JOIN, not INNER) | ✓ | ✓ | ✓ | ✓ | Partial |
| ISO week match (not date range join) | ✓ | ✓ | ✓ | ✓ | Partial |

**Deduction (22 pts):** The ISO week matching semantics (ISO 8601 week vs SQLite strftime week) are documented but not tested at integration level. The "stock rows always appear" guarantee relies on the LEFT JOIN but has no test that proves a stock row with no matching plan still appears in the output.

---

## Issues Found and Fixed

No documentation fixes were required. The implemented code matches the specifications in all aspects. Edge cases are documented in Refinement.md.

---

## Gaps Accepted (Non-Blocking)

| Gap | Agent | Decision |
|-----|-------|---------|
| No cross-tenant isolation test (Org B cannot see Org A data) | 3 | Documented in Refinement.md; should be added in follow-up |
| No repository-level LEFT JOIN integration test | 5 | Workbook-level test covers the "—" rendering; DB-level test deferred |
| No boundary date test (exactly 366 days allowed) | 2 | Low risk; `(date_to - date_from).days > 366` is unambiguous |
| No-fill openpyxl assertion fragility | 4 | Test passes; fragility documented |
| SQLite week numbering divergence | 5 | Production uses PostgreSQL; divergence documented in Refinement.md |

---

## Validation Summary

All 5 user stories pass INVEST + SMART criteria with scores ranging from 78–88 (all above 70 threshold). No BLOCKED items. The retroactive nature of this validation confirms the implementation is complete and well-specified. Test gaps are documented and deferred to follow-up tasks.

**Verdict: PASS — Feature is implemented and validated**
