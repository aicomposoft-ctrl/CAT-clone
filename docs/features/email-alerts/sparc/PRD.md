# PRD: Email Alerts

**Feature:** `email-alerts`
**Date:** 2026-04-02
**Status:** Phase 1 — Planning (retroactive documentation)

---

## Executive Summary

Automated email notification system that monitors FMCG brand SKUs across retail platforms and sends HTML alerts to configured recipients when content scores drop below a threshold (content_drop) or a SKU goes out of stock (oos). Alert configs are managed per-org by managers and admins via a REST API. A scheduled Celery job runs the checks daily; admins can also trigger checks manually.

---

## Problem Statement

Brand managers have no proactive visibility into two critical shelf-health events:

1. **Content degradation** — a retailer silently removes or corrupts product images and descriptions, causing `content_total` to fall below acceptable quality thresholds. Without an alert, the drop is only noticed on the next manual report review — which can be days or weeks later.
2. **Out-of-stock** — a SKU goes OOS on a platform while the brand's operations team is unaware. The brand loses sales and distribution credibility without knowing why.

Manual monitoring of 110+ platforms × 1000s of SKUs is not scalable. CAT already collects this data daily — the missing piece is the last-mile notification layer.

---

## User Stories

### US-01 — Create Alert Config

> As a **manager** or **admin**, I want to create an alert rule specifying type (content_drop or oos), optional SKU/platform scope, threshold (for content_drop), and email recipients, so that I can be notified automatically when conditions are met.

**Acceptance Criteria:**
- POST `/api/v1/alerts/configs` returns 201 with full config details
- `alert_type` must be `content_drop` or `oos`; any other value returns 422
- `threshold` is required for `content_drop` and must be in range 0–100; missing threshold returns 422
- `threshold` is optional (nullable) for `oos`
- `email_recipients` must contain at least 1 and at most 20 valid email addresses
- `sku_id = null` means the rule applies to all SKUs for the org
- `platform_id = null` means the rule applies to all platforms
- New configs are `is_active = true` by default
- Viewer role cannot create configs — returns 403
- Unauthenticated request returns 401

### US-02 — List Alert Configs

> As any authenticated user, I want to list all alert configs for my org, so that I can review what rules are active.

**Acceptance Criteria:**
- GET `/api/v1/alerts/configs` returns paginated list (default size 50, max 200)
- Response includes `total`, `page`, `size`, and `items` array
- Only configs belonging to the authenticated user's `org_id` are returned
- Configs from other organisations are never visible
- All roles (admin, manager, viewer) can list configs

### US-03 — Receive Email When Content Score Drops Below Threshold

> As a **manager**, I want to receive an HTML email when a SKU's `content_total` score falls below the configured threshold on a given day, so that I can take immediate corrective action.

**Acceptance Criteria:**
- Email is sent when `content_total < threshold` for the check date
- Email contains: org name, check date, number of affected SKUs, and a table with SKU name, article, platform name, and score value
- One email per alert config per check run (not one per SKU)
- If the same condition persists the next day, a new event is created and a new email is sent
- If the same condition is checked twice on the same day, only one event is created (dedup)
- If SMTP is not configured, the alert event is still recorded (`is_sent=false`) — no exception raised
- If the email send fails, the event remains persisted with `is_sent=false`

### US-04 — Receive Email When SKU Goes Out of Stock

> As a **manager**, I want to receive an HTML email when a SKU shows `in_stock=false` on a platform on a given day, so that I can address the availability gap.

**Acceptance Criteria:**
- Email is sent when `in_stock = false` in the latest `content_score_reads` for the check date
- `threshold` field is not required for oos configs (NULL is valid)
- Email table shows: SKU name, article, platform name; score column shows "—" for oos events
- Dedup constraint prevents duplicate events for the same SKU×Platform×Date
- All other email delivery guarantees same as US-03

### US-05 — View Alert Event History

> As any authenticated user, I want to see a paginated list of triggered alert events for my org, so that I can audit which alerts fired and whether emails were sent.

**Acceptance Criteria:**
- GET `/api/v1/alerts/events` returns paginated event history (default size 50, max 200)
- Filterable by `alert_type` and `is_sent`
- Each event shows: `id`, `config_id`, `sku_platform_id`, `scored_at`, `triggered_at`, `alert_type`, `value_before`, `value_after`, `is_sent`, `sent_at`
- Only events belonging to the authenticated org are returned (tenant isolation via JOIN through alert_configs)
- Unauthenticated request returns 401

### US-06 — Manual Trigger (Admin)

> As an **admin**, I want to manually trigger the alert check for my org, so that I can test alert configurations without waiting for the scheduled daily run.

**Acceptance Criteria:**
- POST `/api/v1/alerts/check` triggers the full check-and-send pipeline for the admin's org
- Returns `{ events_created: int, emails_sent: int, errors: list[str] }`
- Non-admin roles (manager, viewer) receive 403
- If no active configs exist, returns `{ events_created: 0, emails_sent: 0, errors: [] }`
- Dedup is honoured — re-running on the same day creates 0 new events for already-alerted combinations
- Unexpected internal errors return 500 with `detail: "INTERNAL_ERROR"`

### US-07 — Update and Delete Alert Config

> As a **manager** or **admin**, I want to update (threshold, recipients, active status) or delete an alert config, so that I can manage rules as business requirements change.

**Acceptance Criteria:**
- PATCH `/api/v1/alerts/configs/{id}` updates only the fields provided (partial update)
- Updatable fields: `threshold`, `email_recipients`, `is_active`
- Non-existent or cross-tenant config returns 404
- DELETE `/api/v1/alerts/configs/{id}` removes the config and cascades to its events
- Successful delete returns 204 No Content
- Viewer role cannot patch or delete — returns 403

---

## Non-Functional Requirements

| Category | Requirement |
|----------|------------|
| Reliability | Alert events are committed to DB before any email attempt — no event loss on SMTP failure |
| Idempotency | Re-running check on the same day for the same config × SKU × platform creates 0 duplicate events |
| SMTP Optional | SMTP not configured → log warning + continue; app never raises exception from missing SMTP |
| Graceful Degradation | `aiosmtplib` not installed → log warning + continue (no hard import at module level) |
| Multi-tenancy | All configs and events strictly scoped to `org_id`; events isolation via JOIN through configs |
| RBAC | admin + manager: full CRUD + check; viewer: read-only; unauthenticated: 401 |
| Email Format | HTML with inline styles; table of affected SKUs; no external CSS or JS |
| Throughput | Designed for 100s of SKUs per check run; one email per config (not per SKU) |

---

## Out of Scope (Future Sprints)

- `competitor_promo` alert type (price undercut by competitor — separate feature)
- `price_change` alert type — separate feature
- Webhook delivery (Slack, Teams) — separate feature
- Alert suppression windows ("do not disturb" hours) — separate feature
- Per-event email (one email per SKU, not per config) — batching is by design
- SMS or push notifications

---

## Success Metrics

- Manager receives email within 2–4 hours of content score dropping below threshold (via scheduled Celery job)
- Zero duplicate events for the same SKU×Platform×Day combination
- Alert events persist even when SMTP is unavailable (graceful degradation observable via `is_sent=false` in history)
- Admin can manually verify alert behaviour without waiting for the daily schedule
