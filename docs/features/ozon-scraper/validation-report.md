# Validation Report — Ozon Scraper

**Date:** 2026-03-27
**Phase:** 2 — Validation (5 parallel agents)
**Result:** Issues found → SPARC docs updated → Re-scored PASS

---

## Agent Scores (Initial → After Fixes)

| Agent | Area | Initial | After Fix | Verdict |
|-------|------|---------|-----------|---------|
| Agent 1 | User Story Completeness | 80/100 | 88/100 | PASS |
| Agent 2 | BDD Scenario Coverage | 44/100 → **BLOCKED** | 78/100 | PASS |
| Agent 3 | Acceptance Criteria Clarity | 60/100 | 74/100 | PASS |
| Agent 4 | Technical Feasibility | 74/100 | 88/100 | PASS |
| Agent 5 | Security/Multi-tenant | 62/100 | 82/100 | PASS |

---

## Issues Found and Fixed

### BLOCKED Issues (must fix before implementation)

**B1: Cross-tenant isolation BDD missing for US-O02, US-O03, US-O04** (Agent 2)
- Root cause: Cross-tenant scenario existed only for content collection task.
- Fix: Added cross-tenant isolation Gherkin scenarios to US-O02 (price), US-O03 (stock), US-O04 (reviews).

**B2: Error codes NOT_FOUND/API_UNAVAILABLE/NO_ITEM_ID not systematically applied** (Agent 2)
- Root cause: Error paths documented for content only; other tasks assumed same behavior implicitly.
- Fix: Added explicit error path scenarios for each task where applicable.

**B3: SSRF guard scenario absent** (Agent 2 — security-critical missing test)
- Fix: Added SSRF guard scenarios to US-O01: non-Ozon CDN URL rejected, no HTTP fetch made.

---

### Major Issues Fixed

**M1: `_OZ_IMAGE_CDN_RE` regex used `[a-f0-9]` (hex) instead of `[a-z0-9]` (alphanumeric)** (Agent 4)
- Impact: Would silently reject ~30-50% of valid Ozon CDN URLs, causing mass image collection failure.
- Fix: Changed `[a-f0-9]+` to `[a-z0-9]+` in Architecture.md regex definition.

**M2: `_parse_item_id()` not in pseudocode task flow** (Agent 5)
- Impact: Implementor following pseudocode literally would skip numeric validation, enabling URL injection with non-numeric item_ids.
- Fix: Added explicit `_parse_item_id()` call at step 2 of all task pseudocode with `ScraperError("PARSE_ERROR")` on failure.

**M3: SELECT-then-INSERT race condition on content_scores upsert** (Agent 5)
- Impact: Concurrent content + stock tasks could both pass `IF existing is None` check and both attempt INSERT, causing unique constraint violation crash.
- Fix: Replaced ORM-level SELECT-then-INSERT with `pg_insert(...).on_conflict_do_update(constraint="uq_content_scores_sp_date", set_={...})` in both content and stock task pseudocode. Content task sets content fields only; stock task sets stock fields only — partial-row contract preserved.

**M4: `available_qty` field name mismatch — migration 0003 uses `warehouse_qty`** (Agent 4)
- Impact: Runtime `AttributeError` if implemented with wrong field name.
- Fix: Changed `available_qty` → `warehouse_qty` in PRD.md target data table and Specification.md output schema.

**M5: `availability` integer mapping ambiguous** (Agent 3)
- Impact: Implementor unclear whether availability=1 means in_stock=true; string "outOfStock" vs integer inconsistency.
- Fix: Specification.md US-O03 scenarios now show exact fixture: `{"availability": 1, "count": 42}` with explicit mapping. Split "out of stock" into two scenarios: availability=0 and count=0 with availability=1.

**M6: Image download re-validation absent from `_download_image_async`** (Agent 5)
- Fix: Architecture.md now shows `_download_image_async` re-validates URL against `_OZ_IMAGE_CDN_RE` before HTTP call.

**M7: Image CDN failure non-fatal scenario missing** (Agents 2, 3)
- Fix: Added BDD scenario to US-O01: CDN timeout → content still saved, image_url=null.

**M8: Empty widgetStates treated as NOT_FOUND not in BDD** (Agent 2)
- Fix: Added scenario to US-O01.

**M9: Non-numeric external_id not in BDD** (Agents 2, 5)
- Fix: Added scenario to US-O01: PARSE_ERROR raised, no HTTP call, no DB write.

---

### Minor Issues — Documented (follow-up)

| # | Issue | Priority |
|---|-------|----------|
| m1 | `_parse_price_str` no `InvalidOperation` guard around `Decimal(cleaned)` | Follow-up |
| m2 | widgetStates: only first widget per prefix kept (variant/bundle pages) | Follow-up |
| m3 | `x-o3-app-version: "2.68.0"` hardcoded — needs update strategy at scale | Follow-up |
| m4 | Playwright fallback absent — required before >500 active Ozon SKUs | Sprint 3 |
| m5 | Reviews pagination: only page 1 fetched; may return <50 reviews for popular products | Follow-up |
| m6 | `external_review_id` not length-capped; Ozon UUIDs are bounded but unvalidated | Follow-up |

---

## User Story Scores (Post-Fix)

| Story | Score | Verdict |
|-------|-------|---------|
| US-O01: Content Collection | 92/100 | PASS |
| US-O02: Price Collection | 86/100 | PASS |
| US-O03: Stock Collection | 84/100 | PASS |
| US-O04: Review Collection | 85/100 | PASS |
| **Average** | **87/100** | **PASS** |

Zero BLOCKED items after fixes. All scores ≥ 70/100. Gate passed.

---

## Ready for Phase 3: Implementation
