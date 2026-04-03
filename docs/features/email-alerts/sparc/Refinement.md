# Refinement: Email Alerts

**Feature:** `email-alerts`
**Date:** 2026-04-02

---

## Edge Cases

### Email Send Failure

**Scenario:** SMTP connection succeeds but `aiosmtplib.send()` raises an exception (timeout, auth failure, relay rejection).

**Handling:**
- `send_alert_email()` re-raises the exception after logging `logger.error(...)`.
- `check_and_send_alerts()` catches it in the per-config try/except block.
- The error string is appended to `errors[]` in `AlertCheckResponse`.
- `mark_events_sent()` is NOT called — events remain `is_sent=false`.
- Events are NOT deleted — they persist in the database and can be queried via `GET /alerts/events?is_sent=false`.
- The response is still HTTP 200 (non-fatal per config); the `errors[]` field communicates the failure.

**Key invariant:** No alert event is ever silently discarded. Either `is_sent=true` (delivered) or `is_sent=false` (pending/failed) — always auditable.

---

### SMTP Not Configured

**Scenario:** `SMTP_HOST` environment variable is empty or not set.

**Handling:**
- `send_alert_email()` logs `logger.warning("SMTP_HOST not configured...")` and returns immediately.
- No exception is raised; the caller does not see an error.
- Alert events ARE created and committed before this point (commit-before-email pattern).
- Events have `is_sent=false` and `sent_at=null` — they remain as a record of triggered conditions.
- This is the expected behaviour in local development environments.

---

### aiosmtplib Not Installed

**Scenario:** The `aiosmtplib` package is missing from the Python environment.

**Handling:**
- `send_alert_email()` catches the `ImportError` from the deferred `import aiosmtplib` inside the function body.
- Logs `logger.warning("aiosmtplib not installed — alert email skipped")` and returns.
- No exception propagates. Application continues normally.
- This is intentional: `aiosmtplib` is an optional dependency for non-email deployments.

---

### Dedup Race Condition (Concurrent Check Runs)

**Scenario:** Two Celery workers or two manual trigger calls run `check_and_send_alerts()` simultaneously for the same org and date.

**Handling:**
- `already_alerted()` check reduces the probability but is not atomic.
- The UNIQUE constraint `uq_alert_events_no_duplicate` (config_id, sku_platform_id, scored_at) is the authoritative dedup guard.
- `create_event()` catches `IntegrityError` from `db.flush()`, calls `await db.rollback()`, and returns `None`.
- The calling loop treats `None` return as "already alerted" and skips incrementing `events_created`.
- Result: one event created, one email sent — even under concurrent execution.

---

### Re-Run Same Day (Idempotency)

**Scenario:** Admin calls `POST /alerts/check` twice on the same day.

**Handling:**
- First run: `already_alerted()` returns False → events created → emails sent.
- Second run: `already_alerted()` returns True for each already-processed candidate → skipped.
- Response: `{ events_created: 0, emails_sent: 0, errors: [] }`.
- No duplicate events, no duplicate emails.

---

### threshold = NULL for OOS Configs

**Scenario:** An `oos` config has `threshold = null` (valid by design).

**Handling:**
- `_get_candidates()` dispatches to `get_oos_candidates()` — no threshold parameter is passed.
- `get_oos_candidates()` does not reference threshold; it queries `in_stock IS false` only.
- No null-pointer risk. The `threshold` field on `AlertConfig` is `Optional[Decimal]`.

---

### content_total = NULL in ContentScoreRead

**Scenario:** A `content_score_reads` row exists for the date but `content_total` is NULL (not yet computed).

**Handling:**
- `get_content_drop_candidates()` includes `AND content_total IS NOT NULL` in the WHERE clause.
- Rows with NULL scores are excluded from triggering `content_drop` alerts.
- No false positives from unscored entries.

---

### Config with sku_id = NULL (Org-wide Rule)

**Scenario:** Alert config has `sku_id = null` (applies to all SKUs for the org).

**Handling:**
- `_get_candidates()` passes `sku_id=None` to the repository query.
- Repository omits the `AND sku_platforms.sku_id = :sku_id` filter clause.
- All SKUs in the org matching the other criteria are returned.
- This is the intended "catch-all" behaviour.

---

### Cross-Tenant Event Isolation

**Scenario:** Org A's user queries `GET /alerts/events`. Org B has events in the database.

**Handling:**
- `list_events()` uses JOIN: `SELECT ... FROM alert_events JOIN alert_configs ON ... WHERE alert_configs.org_id = :org_id`.
- Org B's events have `config_id` pointing to Org B's configs.
- Org B's configs have `org_id = ORG_B_ID` ≠ ORG_A_ID.
- The WHERE clause filters them out. Org A never sees Org B's events.
- Covered by test: `test_delete_config_cross_tenant_returns_404` (config-level); event-level isolation covered by `test_list_events_empty_for_fresh_org` (no cross-org leakage in fresh DB state).

---

### org_name in Manual Trigger

**Scenario:** `POST /alerts/check` is called manually. The org name is needed for email rendering.

**Handling:**
- The router passes `org_name=str(current_user.org_id)` — the UUID string as a fallback.
- This is a known limitation of the manual trigger endpoint: the org's display name is not fetched from the DB.
- In the scheduled Celery job (not yet implemented), `org_name` would be resolved via a proper DB lookup.
- Impact: emails triggered manually show UUID as org name instead of the human-readable name.

---

## Performance Considerations

| Scenario | Notes |
|----------|-------|
| Large org with many SKUs | One DB query per config type (content_drop or oos) — not one per SKU |
| Many active configs | `get_active_configs()` returns all at once; N queries where N = number of configs (one per config for candidates) |
| N+1 risk in already_alerted | One SELECT per candidate — potential N+1 for orgs with many SKUs per config. Mitigated by `idx_alert_events_config` covering most cases. |
| Email batch size | One email per config per run — not one per SKU. Bounded by number of active configs, not number of triggered SKUs. |

---

## Security Considerations

| Item | Handling |
|------|---------|
| SMTP credentials | Read from environment variables only (`SMTP_HOST`, `SMTP_PASSWORD`). Never in source code. |
| email_recipients in email | Used in `msg["To"]` header only — never interpolated into SQL queries. No injection risk. |
| email_recipients in DB | Stored as JSON text. Read via `json.loads()`. No SQL involvement. |
| HTML email content | `sku_name`, `platform_name` from internal DB — not user-submitted text. Low XSS risk in email client context. |
| org_name in email | Passed as trusted string from service layer — not user-submitted input. |

---

## Testing Strategy

### Covered in test_alerts_api.py

| Test | Coverage |
|------|---------|
| `test_create_config_requires_auth` | Auth enforcement |
| `test_viewer_cannot_create_config` | RBAC enforcement |
| `test_create_content_drop_config_success` | Happy path create |
| `test_create_oos_config_no_threshold_ok` | OOS threshold-null valid |
| `test_create_content_drop_without_threshold_fails` | Validation rule |
| `test_list_configs_returns_own_org_only` | Tenant isolation (configs) |
| `test_update_config_toggles_active` | PATCH functionality |
| `test_delete_config_success` | DELETE + verify removed |
| `test_delete_config_cross_tenant_returns_404` | Cross-tenant config isolation |
| `test_list_events_requires_auth` | Auth enforcement |
| `test_list_events_empty_for_fresh_org` | Event listing baseline |
| `test_check_requires_admin_role` | RBAC for /check |
| `test_check_returns_zero_when_no_configs` | Empty org fast exit |
| `test_check_content_drop_creates_event` | content_drop trigger + email mock |
| `test_check_content_drop_skips_above_threshold` | No false positive |
| `test_check_oos_creates_event` | OOS trigger |
| `test_check_deduplication_no_double_event` | Idempotency |
| `test_check_inactive_config_skipped` | is_active filter |
| `test_render_html_contains_sku_name` | HTML template unit test |
| `test_render_html_oos_type` | OOS HTML rendering + null handling |

### Gaps (Not Yet Covered)

| Gap | Priority |
|-----|---------|
| Email send failure path (`send_alert_email` raises) → event stays `is_sent=false` | High |
| Cross-tenant event isolation (Org B events invisible to Org A via list_events) | High |
| `test_check_oos` email mock verification (awaited once) | Medium |
| PATCH 404 for non-existent config | Medium |
| DELETE 404 for non-existent config | Medium |
| `already_alerted()` direct unit test | Low |
