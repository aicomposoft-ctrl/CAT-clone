# Validation Report: email-alerts

**Date:** 2026-04-02
**Phase:** 2 — Retroactive Validation (5 Parallel Agents)
**Status:** ✅ Pass

---

## Scores

| Agent | Scope | Score | Verdict |
|-------|-------|-------|---------|
| 1 | INVEST Criteria (User Stories) | 78/100 | Pass |
| 2 | API Contract Completeness | 82/100 | Pass |
| 3 | Acceptance Criteria Measurability | 71/100 | Pass (gaps noted for US-03 / US-04) |
| 4 | Test Coverage Completeness | 68/100 | Pass with gaps noted |
| 5 | Scope & Feasibility | 84/100 | Pass |

---

## User Story INVEST Analysis

### US-01 — Create Alert Config

| Criterion | Score | Notes |
|-----------|-------|-------|
| Independent | ✓ | No dependency on other US |
| Negotiable | ✓ | Threshold range and recipient limits are negotiable |
| Valuable | ✓ | Foundation for all alerting — no alerts without configs |
| Estimable | ✓ | CRUD endpoint with validation — 2–4h |
| Small | ✓ | Single endpoint with clear schema |
| Testable | ✓ | All ACs are verifiable: 201, 403, 422 responses are deterministic |

**Score: 85/100** — well-specified, measurable ACs.

---

### US-02 — List Alert Configs

| Criterion | Score | Notes |
|-----------|-------|-------|
| Independent | ✓ | Can be implemented alongside US-01 |
| Negotiable | ✓ | Pagination size negotiable |
| Valuable | ✓ | Required for UI and audit |
| Estimable | ✓ | Standard paginated GET |
| Small | ✓ | Simple read operation |
| Testable | ✓ | Response schema and tenant isolation are verifiable |

**Score: 88/100** — straightforward, no ambiguity.

---

### US-03 — Receive Email When Content Score Drops Below Threshold

| Criterion | Score | Notes |
|-----------|-------|-------|
| Independent | ⚠ | Depends on ContentScoreRead data existing for the check date |
| Negotiable | ✓ | Email format, grouping strategy negotiable |
| Valuable | ✓ | Core value proposition of the feature |
| Estimable | ✓ | check_and_send_alerts() is well-specified |
| Small | ⚠ | Largest story — spans repository query, service logic, and email send |
| Testable | ⚠ | Weak: "within 2–4 hours" is not testable at unit level |

**Score: 70/100** — passes threshold but has measurability gaps.

**Gap identified (Agent 3):** The AC "email sent when content_total < threshold on check date" is testable. However, the acceptance criterion "Manager receives email within 2–4 hours" (from PRD Success Metrics) is an infrastructure SLA, not a unit-testable condition. The unit/E2E test correctly mocks `send_alert_email` and verifies `emails_sent == 1`. The latency guarantee depends on Celery beat schedule — not covered by automated tests.

**Decision:** Gap is non-blocking. The test strategy correctly mocks SMTP and verifies event creation + email trigger count. Celery schedule latency is an operational concern.

---

### US-04 — Receive Email When SKU Goes Out of Stock

| Criterion | Score | Notes |
|-----------|-------|-------|
| Independent | ⚠ | Depends on ContentScoreRead with `in_stock=false` |
| Negotiable | ✓ | Same as US-03 |
| Valuable | ✓ | Equally high business value |
| Estimable | ✓ | Parallel implementation to US-03 with a different query |
| Small | ✓ | Simpler than US-03 (no threshold comparison) |
| Testable | ✓ | `test_check_oos_creates_event` verifies trigger; mock verifies email call |

**Score: 77/100** — good. One minor gap: the test verifies `events_created == 1` but does not assert `mock_send.assert_awaited_once()` (unlike the content_drop test). This is a test gap, not a specification gap.

---

### US-05 — View Alert Event History

| Criterion | Score | Notes |
|-----------|-------|-------|
| Independent | ✓ | Read-only; does not depend on email sending |
| Negotiable | ✓ | Filter options negotiable |
| Valuable | ✓ | Required for audit and debugging failed sends |
| Estimable | ✓ | Standard paginated GET with filters |
| Small | ✓ | Single endpoint |
| Testable | ✓ | Schema verifiable; tenant isolation via JOIN is testable |

**Score: 82/100** — well-specified.

**Gap (Agent 3):** No test verifying that Org B's events are invisible to Org A user (only config cross-tenant is tested). Noted in Refinement.md.

---

### US-06 — Manual Trigger (Admin)

| Criterion | Score | Notes |
|-----------|-------|-------|
| Independent | ✓ | Calls check_and_send_alerts() — already implemented |
| Negotiable | ✓ | org_name resolution behaviour is negotiable |
| Valuable | ✓ | Enables testing without waiting for scheduler |
| Estimable | ✓ | Thin router wrapper around existing service function |
| Small | ✓ | Smallest story in the set |
| Testable | ✓ | RBAC (403 for manager), 200 for admin, 500 on unhandled exception |

**Score: 80/100** — passes cleanly.

**Known limitation documented:** `org_name` passed as UUID string (not resolved from DB) in the manual trigger. Documented in Refinement.md as known limitation.

---

### US-07 — Update and Delete Alert Config

| Criterion | Score | Notes |
|-----------|-------|-------|
| Independent | ✓ | PATCH/DELETE on existing config |
| Negotiable | ✓ | Which fields are mutable is negotiable |
| Valuable | ✓ | Without this, configs are immutable — ops burden |
| Estimable | ✓ | Standard PATCH/DELETE pattern |
| Small | ✓ | Two operations, both simple |
| Testable | ✓ | update test exists; delete test + cross-tenant 404 test exist |

**Score: 78/100** — good.

**Gap (Agent 3):** Spec states `alert_type`, `sku_id`, `platform_id` are immutable after creation. This is enforced by the `AlertConfigUpdate` schema (those fields are absent). However, there is no explicit test that *attempts* to send these fields in a PATCH body and verifies they are ignored. Minor gap.

---

## Summary of Gaps

| Gap | US | Severity | Decision |
|-----|----|----------|---------|
| `test_check_oos_creates_event` does not assert `mock_send.assert_awaited_once()` | US-04 | Minor | Fix in test suite |
| No cross-tenant event isolation test (list_events) | US-05 | Major | Add test `test_list_events_cross_tenant_isolation` |
| "2–4 hour delivery" is not unit-testable | US-03 | Non-blocking | Operational SLA — not a test gap |
| org_name as UUID in manual trigger | US-06 | Minor/Known | Documented in Refinement.md |
| No test for immutability of `alert_type` in PATCH | US-07 | Minor | Add to test suite |
| Email send failure → event stays `is_sent=false` not tested | US-03/04 | Major | Add test `test_check_email_failure_event_persists` |

---

## Validation Summary

All 7 user stories score ≥ 70/100. No story is BLOCKED (< 50). The two major gaps (cross-tenant event isolation test and email failure path test) are test-coverage gaps, not specification gaps. The feature logic is correctly specified. Two gaps are tracked in Refinement.md testing strategy section.

**Verdict: PROCEED — feature is implemented and ready for Phase 4 review**
