# Review Report: email-alerts

**Date:** 2026-04-02 (reviewed) / 2026-04-03 (fixes applied)
**Phase:** 4 — 5 Parallel Review Agents (brutal-honesty-review)
**Status:** ✅ All Critical and Major issues resolved — ready to merge

---

## Scores

| Agent | Scope | Score | Verdict |
|-------|-------|-------|---------|
| 1 | Code Quality (Linus mode) | 62/100 | 2 Critical, 3 Major |
| 2 | Security (OWASP — STRICT) | 58/100 | 2 Critical, 4 Major |
| 3 | Multi-tenant Isolation | 72/100 | 0 Critical, 2 Major |
| 4 | Performance (N+1, indexes) | 65/100 | 0 Critical, 3 Major |
| 5 | Test Coverage | 60/100 | 0 Critical, 4 Major gaps |

---

## Critical Issues (MUST fix before merge)

### CRITICAL-1 — Agent 2: SMTP password read from env but not validated at startup

**File:** `services/api/app/alerts/email.py` (line 115), `services/api/app/core/config.py`

**Problem:**
`SMTP_PASSWORD` is read lazily inside `send_alert_email()` via `os.environ.get("SMTP_PASSWORD", "")`. The project's secrets management rule requires all secrets to be validated at startup via `validate_secrets()` with `sys.exit(1)` on missing values. This is inconsistent — other services exit on missing SMTP config, but the alerts module silently falls back to unauthenticated SMTP.

More critically: `SMTP_PASSWORD` is not in the `REQUIRED_SECRETS` list in `core/config.py`. An empty string is silently passed as `password=None` to `aiosmtplib.send()`. If the SMTP server requires auth, this causes a runtime failure at alert send time — hours after deployment — rather than at startup.

**Fix required:**
Add `SMTP_HOST` and `SMTP_PASSWORD` to `REQUIRED_SECRETS` in `core/config.py`, OR explicitly document that SMTP is optional and the startup validator must distinguish "SMTP enabled" (SMTP_HOST set) from "SMTP not configured" (SMTP_HOST empty). If SMTP_HOST is set, SMTP_PASSWORD should be validated as non-empty.

---

### CRITICAL-2 — Agent 1: `already_alerted()` is not atomic with `create_event()`

**File:** `services/api/app/alerts/repository.py` (lines 212–224, 227–255)

**Problem:**
`check_and_send_alerts()` performs a two-step check: (1) `already_alerted()` SELECT COUNT, (2) `create_event()` INSERT with flush. Between these two operations in an async context, another concurrent invocation (e.g., two Celery workers or two overlapping `/check` requests) can pass both the SELECT COUNT check and both reach the INSERT. The `IntegrityError` path in `create_event()` handles this, BUT the `await db.rollback()` in `create_event()` rolls back the entire transaction savepoint, not just the one row. This means if events for other candidates in the same config loop iteration were already flushed to the same transaction, they are also rolled back.

The fundamental issue is that `create_event()` calls `await db.rollback()` on an `AsyncSession` that is shared across the entire `check_and_send_alerts()` call. A full session rollback here would lose all previously flushed events for the same org/run.

**Fix required:**
Use `async with db.begin_nested()` (SQLAlchemy savepoint) in `create_event()` instead of `await db.rollback()`. This rolls back only the failed INSERT, not the entire session:

```python
async def create_event(db, ...) -> AlertEvent | None:
    event = AlertEvent(...)
    db.add(event)
    try:
        async with db.begin_nested():  # savepoint
            await db.flush()
        return event
    except IntegrityError:
        return None  # savepoint rolled back automatically — session intact
```

---

## Major Issues (fix before merge or document as tracked debt)

### MAJOR-1 — Agent 2: No rate limiting on POST /alerts/check

**File:** `services/api/app/alerts/router.py` (line 127)

**Problem:**
`POST /alerts/check` triggers the full check pipeline: multiple DB queries per active config, candidate queries with JOINs, email sends. There is no rate limiting on this endpoint. An admin user (or a stolen admin token) can trigger this endpoint repeatedly, causing:
- Duplicate email sends (dedup prevents duplicate events, but emails for configs with newly alerted candidates will fire)
- DB load proportional to number of active configs and SKUs

The project security rules state export endpoints are limited to 5 req/min per org; `POST /check` is at least as expensive as an export.

**Fix required:** Apply `5 req/min per org` rate limiting to `POST /alerts/check`. Use the existing Redis sliding-window rate limiter pattern from the project toolkit.

**Deferred if not blocking merge:** Can be tracked as security backlog item if rate limiting infrastructure is not yet available for this endpoint pattern.

---

### MAJOR-2 — Agent 2: No audit log for sent alerts (A09)

**File:** `services/api/app/alerts/service.py`, `services/api/app/alerts/repository.py`

**Problem:**
OWASP A09 requires logging of security-relevant events. Alert sends are security-relevant: they disclose internal operational data (SKU names, scores, stock status) to email recipients. Currently:
- `mark_events_sent()` silently updates DB rows with no structured log entry.
- There is no log line for "alert sent to recipients X for config Y at time Z".
- The only log is `logger.info("Alert email sent: type=%s recipients=%s rows=%d", ...)` in `email.py` — this is in the right place but logs recipients (PII/sensitive) at INFO level.

**Fix required:**
- Ensure `send_alert_email` log is at INFO (already is — acceptable).
- Add a `logger.info("Alert events marked sent: config=%s event_ids=%s", ...)` in `mark_events_sent()` or its caller.
- Consider whether logging email recipient addresses at INFO level is acceptable under the org's data privacy policy (could be PII). Consider logging only recipient count rather than addresses.

---

### MAJOR-3 — Agent 3: alert_events tenant isolation is not enforced by a DB constraint — relies entirely on application code

**File:** `services/api/app/alerts/models.py` (lines 106–162), `repository.py` (lines 277–308)

**Problem:**
`alert_events` has no `org_id` column. Tenant isolation is enforced by the JOIN pattern in `list_events()`. If any future developer adds a direct query against `alert_events` (e.g., a reporting query, a background job, an admin endpoint) without the JOIN, they will return cross-tenant data.

The model docstring warns about this, but warnings in docstrings are weak enforcement. Unlike `alert_configs` where a missing `org_id` filter causes an obvious query error (no column), missing the JOIN on `alert_events` silently returns all events.

**Fix required:**
Two options:
1. **Preferred:** Add `org_id` as a denormalised column to `alert_events` (populated at insert time from `config.org_id`). This enables direct filtering and is self-documenting. Requires migration 0008.
2. **Acceptable short-term:** Add a PostgreSQL RLS policy on `alert_events` that enforces the JOIN requirement at the DB level.

**If neither is implemented before merge:** Document this as a Critical Known Risk with a follow-up migration task. Ensure `list_events()` is the only function that reads from `alert_events` and enforce via code review.

---

### MAJOR-4 — Agent 4: N+1 queries in check_and_send_alerts() — one already_alerted() call per candidate

**File:** `services/api/app/alerts/service.py` (lines 162–184), `repository.py` (lines 211–224)

**Problem:**
For each candidate returned by `get_content_drop_candidates()` or `get_oos_candidates()`, the service calls `already_alerted()` — one SELECT COUNT per candidate. If a config matches 500 SKU×Platform combinations, this is 500 individual SELECT queries before any INSERT.

For an org with 5 active configs × 200 candidates each = 1000 `already_alerted()` queries per check run, plus 1000 potential INSERT queries. This will cause noticeable latency (seconds to tens of seconds) at scale.

**Fix required:**
Replace the per-candidate `already_alerted()` loop with a bulk pre-load of existing events for the check date:

```python
# Bulk load existing event keys for this config + date
existing = await repository.get_alerted_sku_platforms(
    db, config_id=config.id, scored_at=check_date
)
existing_set = {row["sku_platform_id"] for row in existing}

for candidate in candidates:
    sp_id = candidate["sku_platform_id"]
    if sp_id in existing_set:
        continue
    # create event...
```

This reduces N+1 to 1 query per config (bulk fetch of existing events).

**Deferred if not blocking merge:** Acceptable for MVP with < 100 SKUs per config; must be fixed before scaling to 1000+ SKUs.

---

### MAJOR-5 — Agent 5: Email send failure path not tested

**File:** `services/api/tests/e2e/test_alerts_api.py`

**Problem:**
No test covers the scenario where `send_alert_email()` raises an exception. The expected behaviour (event persists with `is_sent=false`, error appears in `errors[]`, response is still 200) is critical to the commit-before-email guarantee but is entirely untested.

**Fix required:**

```python
@pytest.mark.asyncio
async def test_check_email_failure_event_persists(db_session, org_a):
    """When send_alert_email raises, event must persist with is_sent=false."""
    # ... setup config + candidate data ...
    with patch(
        "app.alerts.service.send_alert_email",
        new_callable=AsyncMock,
        side_effect=Exception("SMTP timeout"),
    ):
        result = await alert_service.check_and_send_alerts(
            db=db_session, org_id=org_a.id, org_name="Org A", check_date=check_date
        )

    assert result.events_created == 1
    assert result.emails_sent == 0
    assert len(result.errors) == 1
    assert "SMTP timeout" in result.errors[0]

    # Verify event is persisted with is_sent=false
    events = await repository.list_events(db_session, org_id=org_a.id, limit=10, offset=0)
    assert events[0][0].is_sent is False
    assert events[0][0].sent_at is None
```

---

### MAJOR-6 — Agent 5: No cross-tenant event isolation test

**File:** `services/api/tests/e2e/test_alerts_api.py`

**Problem:**
`test_delete_config_cross_tenant_returns_404` validates config-level isolation. There is no equivalent test for events: creating an event for Org B and verifying it is invisible to Org A's `GET /alerts/events` call.

This matters because events have no direct `org_id` and the JOIN-based isolation is the sole guard. It must be explicitly tested.

**Fix required:**

```python
@pytest.mark.asyncio
async def test_list_events_cross_tenant_isolation(client, viewer_user, org_b, db_session):
    """Events from org_b must not appear in org_a's event list."""
    # Create a config + event directly for org_b
    config_b = AlertConfig(org_id=org_b.id, ...)
    db_session.add(config_b)
    event_b = AlertEvent(config_id=config_b.id, ...)
    db_session.add(event_b)
    await db_session.flush()

    # Query as org_a viewer
    resp = await client.get("/api/v1/alerts/events", headers=_auth(viewer_user))
    assert resp.status_code == 200
    event_ids = [e["id"] for e in resp.json()["items"]]
    assert str(event_b.id) not in event_ids, "Cross-tenant event leakage!"
```

---

## Deferred Issues (Non-Critical, Tracked Debt)

| # | Agent | Issue | Reason Deferred |
|---|-------|-------|----------------|
| D1 | Agent 2 | SMTP_FROM_EMAIL has a hardcoded fallback `alerts@cat.local` | Not a security secret, but should be configurable in prod |
| D2 | Agent 1 | `value_before` is always NULL — dead field | Reserved for future trend comparison; acceptable |
| D3 | Agent 1 | `check_and_send_alerts` is 60+ lines — exceeds 50-line function guideline | Extract into smaller helpers in a follow-up refactor |
| D4 | Agent 4 | `get_content_drop_candidates` and `get_oos_candidates` both do JOIN on skus+platforms — duplicate logic | Extract shared JOIN base query; defer to refactor sprint |
| D5 | Agent 4 | No index on `(org_id, is_active)` for event listing — wait for profiling | Use `idx_alert_events_pending` for now; add org_id to events if MAJOR-3 is addressed |
| D6 | Agent 5 | `test_check_oos_creates_event` does not assert `mock_send.assert_awaited_once()` | Minor test quality gap; add assertion |
| D7 | Agent 2 | HTML email content uses org_name and sku_name without escaping for HTML | Internal data only — no user-controlled input; low risk |
| D8 | Agent 1 | `_render_html()` builds HTML via string concatenation — no templating engine | Acceptable for internal HTML; jinja2 would be cleaner but introduces a dependency |
| D9 | Agent 3 | No RLS policy on `alert_events` | See MAJOR-3; deferred if migration not in scope |
| D10 | Agent 5 | No test for PATCH 404 (non-existent config) | Minor; standard pattern |
| D11 | Agent 5 | No test for immutability of `alert_type` in PATCH body | Minor; schema enforces it |

---

## Required Fixes Summary

| ID | Severity | File | Fix |
|----|----------|------|-----|
| CRITICAL-1 | Critical | `core/config.py`, `alerts/email.py` | Add SMTP secret validation at startup |
| CRITICAL-2 | Critical | `alerts/repository.py` | Use `begin_nested()` savepoint in `create_event()` |
| MAJOR-1 | Major | `alerts/router.py` | Rate limit `POST /check` (5/min per org) |
| MAJOR-2 | Major | `alerts/service.py` | Structured audit log for sent alerts |
| MAJOR-3 | Major | DB schema | Add `org_id` to `alert_events` OR add RLS policy |
| MAJOR-4 | Major | `alerts/service.py`, `repository.py` | Bulk pre-load existing events; remove per-candidate N+1 |
| MAJOR-5 | Major | `tests/e2e/test_alerts_api.py` | Add email failure path test |
| MAJOR-6 | Major | `tests/e2e/test_alerts_api.py` | Add cross-tenant event isolation test |

---

## Fixes Applied (2026-04-03)

| ID | Fix | Files Changed |
|----|-----|---------------|
| CRITICAL-1 | Conditional SMTP validation at startup: if SMTP_HOST set, SMTP_PASSWORD required | `core/config.py` |
| CRITICAL-2 | `create_event()` uses `begin_nested()` savepoint — IntegrityError only rolls back the single INSERT | `alerts/repository.py` |
| MAJOR-1 | Rate limit `POST /check`: 5 req/min per org via Redis sliding window | `alerts/router.py` |
| MAJOR-2 | Structured audit log in `mark_events_sent()`: count + event IDs; email log now uses recipient count not addresses | `alerts/repository.py`, `alerts/email.py` |
| MAJOR-3 | `org_id` denormalised column added to `AlertEvent`; migration 0008; `list_events()` now filters directly | `alerts/models.py`, `0008_add_org_id_to_alert_events.py`, `alerts/repository.py` |
| MAJOR-4 | Bulk pre-load of `already_alerted_set` per config; `already_alerted()` removed; N+1 eliminated | `alerts/repository.py`, `alerts/service.py` |
| MAJOR-5 | `test_check_email_failure_event_persists` added | `tests/e2e/test_alerts_api.py` |
| MAJOR-6 | `test_list_events_cross_tenant_isolation` added | `tests/e2e/test_alerts_api.py` |
| D6 | `test_check_oos_creates_event` now asserts `mock_send.assert_awaited_once()` | `tests/e2e/test_alerts_api.py` |

All 22 tests pass.

## Final Status

**Ready to merge.** All Critical and Major issues resolved. Deferred items D1–D11 (excluding D6, now fixed) remain tracked as tech debt.
