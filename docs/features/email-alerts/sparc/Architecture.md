# Architecture: Email Alerts

**Feature:** `email-alerts`
**Date:** 2026-04-02

---

## Module Structure

```
services/api/app/alerts/
├── models.py       # SQLAlchemy ORM: AlertConfig, AlertEvent
├── schemas.py      # Pydantic: request/response schemas, AlertCheckResponse
├── repository.py   # DB queries — all org-scoped, event queries via JOIN
├── email.py        # Async HTML email sender (aiosmtplib, graceful degradation)
├── service.py      # Business logic: CRUD wrappers + check_and_send_alerts()
└── router.py       # FastAPI routes (6 endpoints)

infrastructure/postgres/migrations/
└── 0007_create_alert_tables.py  # Alembic migration: alert_configs + alert_events
```

---

## Dependency Graph

```
router.py
  └── service.py
        ├── repository.py
        │     ├── models.py (AlertConfig, AlertEvent)
        │     └── catalog/models.py (SKU, SKUPlatform, Platform)
        │     └── reports/models.py (ContentScoreRead)
        └── email.py (AlertEmailContext, send_alert_email)
```

---

## check_and_send_alerts() Flow

```
POST /alerts/check  OR  Celery beat job
         │
         ▼
check_and_send_alerts(db, org_id, org_name, check_date=today)
         │
         ├─ repository.get_active_configs(org_id)
         │   → SELECT alert_configs WHERE org_id = :org_id AND is_active = true
         │
         ├─ [early exit if no configs]
         │
         ├─ FOR EACH config:
         │   ├─ _get_candidates(db, config, check_date)
         │   │   ├─ if content_drop → repository.get_content_drop_candidates()
         │   │   │     SELECT sku_platform_id, content_total, sku_name, ...
         │   │   │     JOIN content_score_reads, sku_platforms, skus, platforms
         │   │   │     WHERE sku.org_id = :org_id
         │   │   │       AND scored_at = :check_date
         │   │   │       AND content_total < :threshold
         │   │   └─ if oos → repository.get_oos_candidates()
         │   │         SELECT sku_platform_id, sku_name, ...
         │   │         WHERE in_stock IS false
         │   │
         │   └─ FOR EACH candidate:
         │       ├─ repository.already_alerted(config_id, sp_id, check_date)
         │       │   → SELECT COUNT WHERE config_id + sku_platform_id + scored_at
         │       │
         │       └─ if not alerted:
         │           repository.create_event(...)
         │           → INSERT INTO alert_events; flush()
         │           → on IntegrityError (dedup race): rollback(); return None
         │
         ├─ await db.commit()  ← COMMIT ALL EVENTS BEFORE EMAILS
         │   (events are durable even if email fails)
         │
         └─ FOR EACH config WITH new events:
             ├─ build AlertEmailContext (rows from candidate dicts)
             ├─ await send_alert_email(ctx)
             │   ├─ SMTP_HOST empty → log warning; return (no exception)
             │   ├─ aiosmtplib not installed → log warning; return
             │   └─ SMTP error → log error; re-raise
             ├─ on success:
             │   repository.mark_events_sent([event_ids])
             │   await db.commit()
             │   emails_sent += 1
             └─ on exception:
                 errors.append(f"config {config.id}: {exc}")
                 (event remains is_sent=false — not lost)
```

---

## Tenant Isolation

### alert_configs

Direct `org_id` column. All CRUD queries include `WHERE org_id = :org_id` at the repository layer. Enforced in:
- `create_config()` — org_id passed explicitly from `current_user.org_id`
- `get_config()` — both `id` and `org_id` required
- `list_configs()` — WHERE org_id
- `update_config()` — get_config() pre-filters by org_id before update
- `delete_config()` — WHERE id AND org_id

### alert_events

No direct `org_id` column. Tenant isolation is enforced exclusively via JOIN through `alert_configs`:

```sql
SELECT alert_events.*
FROM alert_events
JOIN alert_configs ON alert_events.config_id = alert_configs.id
WHERE alert_configs.org_id = :org_id
```

This pattern is used in:
- `list_events()` — explicit JOIN + WHERE alert_configs.org_id
- `already_alerted()` — queries by `config_id` which is obtained from an already-scoped config object

**Risk note:** Any direct query against `alert_events` without this JOIN would be a tenant isolation breach. This is documented in model docstrings and repository module docstring.

---

## Email Architecture

### SMTP Configuration (environment variables)

| Variable | Purpose | Default |
|----------|---------|---------|
| `SMTP_HOST` | SMTP server hostname | — (empty = disabled) |
| `SMTP_PORT` | SMTP port | `587` |
| `SMTP_USER` | SMTP username | `""` (anonymous) |
| `SMTP_PASSWORD` | SMTP password | `""` |
| `SMTP_FROM_EMAIL` | Sender address | `alerts@cat.local` |
| `SMTP_USE_TLS` | Use STARTTLS | `"true"` |

### Graceful Degradation Tiers

```
Tier 1: SMTP_HOST not set
  → logger.warning(...); return  (no exception, no alert loss)

Tier 2: aiosmtplib not installed
  → logger.warning(...); return  (no exception, no alert loss)

Tier 3: SMTP connection/send error
  → logger.error(...); raise  (caller catches, appends to errors[])
  → event remains is_sent=false (not lost, retryable)
```

### Commit-Before-Email Pattern

Events are committed to the database before any email is attempted. This ensures:
- Events are never lost due to SMTP failures
- Dedup constraint prevents resending on retry
- `is_sent=false` events can be queried to identify pending/failed deliveries

### Email HTML Structure

Single HTML email per config per check run containing:
- Header: alert type label (Russian), org name, check date, count of affected SKUs
- Table: SKU name | Article | Platform | Score value (or "—" for OOS)
- Footer: "CAT — Commerce Analytics Tool" branding

---

## Database Indexes

| Index | Table | Columns | Purpose |
|-------|-------|---------|---------|
| `idx_alert_configs_org_id` | alert_configs | org_id | Fast org-scoped config listing |
| `idx_alert_configs_active` | alert_configs | org_id, is_active | Fast active-config lookup for check job |
| `idx_alert_events_config` | alert_events | config_id | Fast event lookup per config |
| `idx_alert_events_pending` | alert_events | is_sent, triggered_at | Find pending/failed deliveries |
| `uq_alert_events_no_duplicate` | alert_events | config_id, sku_platform_id, scored_at | Dedup constraint (UNIQUE) |

---

## RBAC Matrix

| Endpoint | admin | manager | viewer |
|----------|-------|---------|--------|
| POST /configs | ✓ | ✓ | 403 |
| GET /configs | ✓ | ✓ | ✓ |
| PATCH /configs/{id} | ✓ | ✓ | 403 |
| DELETE /configs/{id} | ✓ | ✓ | 403 |
| GET /events | ✓ | ✓ | ✓ |
| POST /check | ✓ | 403 | 403 |

---

## Celery Integration

The `check_and_send_alerts()` function is designed to be called from a Celery task with `db` session injected:

```python
# Intended Celery task pattern (not yet implemented in this sprint)
@celery_app.task
async def run_alert_check_for_org(org_id: str, org_name: str):
    async with AsyncSessionFactory() as db:
        await service.check_and_send_alerts(
            db=db, org_id=UUID(org_id), org_name=org_name
        )
```

The `check_date` parameter defaults to UTC today, enabling test overrides and historical backfill.

---

## File Locations

| File | Path |
|------|------|
| ORM models | `services/api/app/alerts/models.py` |
| Pydantic schemas | `services/api/app/alerts/schemas.py` |
| DB queries | `services/api/app/alerts/repository.py` |
| Email sender | `services/api/app/alerts/email.py` |
| Business logic | `services/api/app/alerts/service.py` |
| HTTP routes | `services/api/app/alerts/router.py` |
| Migration | `infrastructure/postgres/migrations/0007_create_alert_tables.py` |
| Tests | `services/api/tests/e2e/test_alerts_api.py` |
