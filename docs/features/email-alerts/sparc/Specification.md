# Specification: Email Alerts

**Feature:** `email-alerts`
**Date:** 2026-04-02

---

## API Endpoints

### POST /api/v1/alerts/configs

Create a new alert configuration.

**Roles:** admin, manager (viewer → 403)

**Request Body:**

```json
{
  "alert_type": "content_drop",
  "sku_id": "uuid | null",
  "platform_id": "uuid | null",
  "threshold": 70.00,
  "email_recipients": ["notify@example.com"],
  "is_active": true
}
```

**Field Validation:**

| Field | Type | Required | Rules |
|-------|------|----------|-------|
| `alert_type` | str | YES | Must be `content_drop` or `oos` |
| `sku_id` | UUID \| null | NO | null = all SKUs for this org |
| `platform_id` | UUID \| null | NO | null = all platforms |
| `threshold` | Decimal \| null | CONDITIONAL | Required for `content_drop`, range 0–100; ignored/optional for `oos` |
| `email_recipients` | list[EmailStr] | YES | min 1, max 20 valid email addresses |
| `is_active` | bool | NO | Default: `true` |

**Cross-field validation:** if `alert_type == "content_drop"` and `threshold is None` → 422 Unprocessable Entity.

**Response 201:**

```json
{
  "id": "uuid",
  "org_id": "uuid",
  "sku_id": "uuid | null",
  "platform_id": "uuid | null",
  "alert_type": "content_drop",
  "threshold": "70.00",
  "email_recipients": ["notify@example.com"],
  "is_active": true,
  "created_at": "2026-04-02T10:00:00+00:00"
}
```

**Error Responses:**

| Code | Condition |
|------|-----------|
| 401 | No or invalid JWT |
| 403 | Role is `viewer` |
| 422 | Invalid `alert_type`, missing `threshold` for `content_drop`, no recipients, invalid email format |

---

### GET /api/v1/alerts/configs

List all alert configs for the authenticated org.

**Roles:** admin, manager, viewer (all authenticated)

**Query Parameters:**

| Param | Type | Default | Max |
|-------|------|---------|-----|
| `page` | int | 1 | — |
| `size` | int | 50 | 200 |

**Response 200:**

```json
{
  "items": [AlertConfigResponse],
  "total": 3,
  "page": 1,
  "size": 50
}
```

**Error Responses:**

| Code | Condition |
|------|-----------|
| 401 | No or invalid JWT |

---

### PATCH /api/v1/alerts/configs/{config_id}

Partially update an alert config. Only the provided fields are changed.

**Roles:** admin, manager

**Request Body (all fields optional):**

```json
{
  "threshold": 60.00,
  "email_recipients": ["new@example.com"],
  "is_active": false
}
```

**Updatable fields:** `threshold`, `email_recipients`, `is_active`. `alert_type`, `sku_id`, `platform_id` are immutable after creation.

**Response 200:** Updated `AlertConfigResponse`

**Error Responses:**

| Code | Condition |
|------|-----------|
| 401 | No or invalid JWT |
| 403 | Role is `viewer` |
| 404 | Config not found, or belongs to a different org |
| 422 | Invalid email format, threshold out of range |

---

### DELETE /api/v1/alerts/configs/{config_id}

Delete an alert config. Cascades to all associated `alert_events`.

**Roles:** admin, manager

**Response 204:** No Content

**Error Responses:**

| Code | Condition |
|------|-----------|
| 401 | No or invalid JWT |
| 403 | Role is `viewer` |
| 404 | Config not found, or belongs to a different org |

---

### GET /api/v1/alerts/events

List alert events for the authenticated org.

**Roles:** admin, manager, viewer (all authenticated)

**Query Parameters:**

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `alert_type` | str | null | Filter: `content_drop` or `oos` |
| `is_sent` | bool | null | Filter: true (sent), false (pending) |
| `page` | int | 1 | — |
| `size` | int | 50 | Max 200 |

**Response 200:**

```json
{
  "items": [AlertEventResponse],
  "total": 12,
  "page": 1,
  "size": 50
}
```

**AlertEventResponse:**

```json
{
  "id": "uuid",
  "config_id": "uuid",
  "sku_platform_id": "uuid",
  "scored_at": "2026-04-01",
  "triggered_at": "2026-04-02T06:00:00+00:00",
  "alert_type": "content_drop",
  "value_before": null,
  "value_after": "45.00",
  "is_sent": true,
  "sent_at": "2026-04-02T06:00:05+00:00"
}
```

**Error Responses:**

| Code | Condition |
|------|-----------|
| 401 | No or invalid JWT |

---

### POST /api/v1/alerts/check

Manually run the alert check pipeline for the authenticated admin's org.

**Roles:** admin only (manager, viewer → 403)

**Request:** No body required.

**Response 200:**

```json
{
  "events_created": 5,
  "emails_sent": 2,
  "errors": []
}
```

`errors` contains non-fatal error strings (e.g., SMTP failure messages per config). The response is always 200 even if some emails failed — individual failures are reported in `errors`.

**Error Responses:**

| Code | Condition |
|------|-----------|
| 401 | No or invalid JWT |
| 403 | Role is not `admin` |
| 500 | Unexpected unhandled exception during check |

---

## Data Models

### AlertConfig

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | UUID | NO | `gen_random_uuid()` | PK |
| `org_id` | UUID | NO | — | FK → organizations.id CASCADE |
| `sku_id` | UUID | YES | NULL | FK → skus.id CASCADE; NULL = all SKUs |
| `platform_id` | UUID | YES | NULL | FK → platforms.id RESTRICT; NULL = all platforms |
| `alert_type` | VARCHAR(50) | NO | — | CHECK: `content_drop` or `oos` |
| `threshold` | NUMERIC(10,2) | YES | NULL | Required for `content_drop`; NULL valid for `oos` |
| `email_recipients` | TEXT | NO | — | JSON-encoded list, e.g. `'["a@x.com"]'` |
| `is_active` | BOOLEAN | NO | true | Soft-disable without deleting |
| `created_at` | TIMESTAMPTZ | NO | `now()` | — |

**Indexes:** `idx_alert_configs_org_id` (org_id), `idx_alert_configs_active` (org_id, is_active)

**Constraints:** `ck_alert_configs_type` CHECK(`alert_type IN ('content_drop', 'oos')`)

**Note on `email_recipients`:** Stored as JSON text (not an array column) for cross-DB compatibility (PostgreSQL and SQLite for tests). Decoded via `json.loads()` in `AlertConfig.get_recipients()`.

---

### AlertEvent

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | UUID | NO | `gen_random_uuid()` | PK |
| `config_id` | UUID | NO | — | FK → alert_configs.id CASCADE |
| `sku_platform_id` | UUID | NO | — | FK → sku_platforms.id CASCADE |
| `scored_at` | DATE | NO | — | The date of the score/stock fact that triggered this event |
| `triggered_at` | TIMESTAMPTZ | NO | `now()` | When the event was created |
| `alert_type` | VARCHAR(50) | NO | — | Copied from config for denormalisation |
| `value_before` | NUMERIC(10,2) | YES | NULL | Currently always NULL (reserved for future trend comparison) |
| `value_after` | NUMERIC(10,2) | YES | NULL | `content_total` for `content_drop`; NULL for `oos` |
| `is_sent` | BOOLEAN | NO | false | Updated to true after successful email send |
| `sent_at` | TIMESTAMPTZ | YES | NULL | Set when `is_sent` transitions to true |

**Dedup Constraint:** `UNIQUE (config_id, sku_platform_id, scored_at)` — named `uq_alert_events_no_duplicate`. Prevents duplicate events for the same alert rule × SKU×Platform × date.

**Indexes:** `idx_alert_events_config` (config_id), `idx_alert_events_pending` (is_sent, triggered_at)

**Tenant Isolation Note:** `alert_events` has no direct `org_id` column. All queries against this table MUST join through `alert_configs.org_id`. Never query `alert_events` directly without this JOIN.

---

## Alert Type Enum

```python
ALERT_TYPES = frozenset({"content_drop", "oos"})
```

| Value | Trigger Condition | Threshold |
|-------|------------------|-----------|
| `content_drop` | `content_total < threshold` on `check_date` | Required, 0–100 |
| `oos` | `in_stock = false` on `check_date` | Not required (NULL valid) |

---

## Validation Rules Summary

| Rule | Error Code |
|------|-----------|
| `alert_type` not in `{content_drop, oos}` | 422 |
| `alert_type == content_drop` and `threshold is None` | 422 |
| `threshold < 0` or `threshold > 100` | 422 |
| `email_recipients` empty list | 422 |
| `email_recipients` length > 20 | 422 |
| Any email in `email_recipients` not valid email format | 422 |
| Config not found or cross-tenant | 404 |
| Viewer accessing write endpoints | 403 |
| Non-admin accessing POST /check | 403 |
