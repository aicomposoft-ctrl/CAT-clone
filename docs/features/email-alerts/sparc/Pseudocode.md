# Pseudocode: Email Alerts

**Feature:** `email-alerts`
**Date:** 2026-04-02

---

## check_and_send_alerts()

```python
async def check_and_send_alerts(
    db: AsyncSession,
    org_id: UUID,
    org_name: str,
    check_date: date | None = None,
) -> AlertCheckResponse:

    IF check_date is None:
        check_date = datetime.now(tz=UTC).date()

    configs = await repository.get_active_configs(db, org_id)
    # SELECT * FROM alert_configs
    # WHERE org_id = :org_id AND is_active = true

    IF not configs:
        RETURN AlertCheckResponse(events_created=0, emails_sent=0, errors=[])

    events_created = 0
    emails_sent = 0
    errors = []
    new_events_by_config: dict[UUID, list[tuple[AlertEvent, dict]]] = {}

    # --- Phase 1: Create events (no email yet) ---
    FOR config IN configs:
        new_events_by_config[config.id] = []
        candidates = await _get_candidates(db, config, check_date)

        FOR candidate IN candidates:
            sp_id = candidate["sku_platform_id"]

            already = await repository.already_alerted(db, config.id, sp_id, check_date)
            IF already:
                CONTINUE  # dedup: skip

            value_after = candidate.get("content_total")  # None for OOS

            event = await repository.create_event(
                db=db,
                config_id=config.id,
                sku_platform_id=sp_id,
                scored_at=check_date,
                alert_type=config.alert_type,
                value_before=None,    # reserved for future trend comparison
                value_after=value_after,
            )
            # create_event returns None on IntegrityError (dedup race)
            IF event is not None:
                events_created += 1
                new_events_by_config[config.id].append((event, candidate))

    # COMMIT all events — durable before any email attempt
    await db.commit()

    # --- Phase 2: Send emails (best-effort) ---
    FOR config IN configs:
        event_pairs = new_events_by_config.get(config.id, [])
        IF not event_pairs:
            CONTINUE  # nothing new for this config

        rows = [
            {
                "sku_name":      c.get("sku_name", ""),
                "sku_article":   c.get("sku_article"),
                "platform_name": c.get("platform_name", ""),
                "value_after":   c.get("content_total"),
            }
            FOR (_, c) IN event_pairs
        ]

        ctx = AlertEmailContext(
            alert_type=config.alert_type,
            org_name=org_name,
            check_date=check_date,
            recipients=config.get_recipients(),
            rows=rows,
        )

        TRY:
            await send_alert_email(ctx)
            sent_ids = [e.id FOR (e, _) IN event_pairs]
            await repository.mark_events_sent(db, sent_ids)
            await db.commit()
            emails_sent += 1
        EXCEPT Exception AS exc:
            logger.error("Failed to send alert email for config %s: %s", config.id, exc)
            errors.append(f"config {config.id}: {exc}")
            # event remains is_sent=false — NOT lost

    RETURN AlertCheckResponse(
        events_created=events_created,
        emails_sent=emails_sent,
        errors=errors,
    )
```

---

## _get_candidates()

```python
async def _get_candidates(
    db: AsyncSession,
    config: AlertConfig,
    check_date: date,
) -> list[dict]:

    IF config.alert_type == "content_drop":
        RETURN await repository.get_content_drop_candidates(
            db=db,
            org_id=config.org_id,
            check_date=check_date,
            threshold=config.threshold,
            sku_id=config.sku_id,           # None = all SKUs
            platform_id=config.platform_id, # None = all platforms
        )

    IF config.alert_type == "oos":
        RETURN await repository.get_oos_candidates(
            db=db,
            org_id=config.org_id,
            check_date=check_date,
            sku_id=config.sku_id,
            platform_id=config.platform_id,
        )

    logger.warning("Unknown alert_type %r — skipping config %s", config.alert_type, config.id)
    RETURN []
```

---

## get_content_drop_candidates()

```python
async def get_content_drop_candidates(
    db: AsyncSession,
    org_id: UUID,
    check_date: date,
    threshold: Decimal,
    sku_id: UUID | None,
    platform_id: UUID | None,
) -> list[dict]:

    stmt = (
        SELECT
            ContentScoreRead.sku_platform_id,
            ContentScoreRead.content_total,
            SKU.name      AS sku_name,
            SKU.article   AS sku_article,
            Platform.name AS platform_name
        FROM content_score_reads
        JOIN sku_platforms  ON sku_platforms.id  = content_score_reads.sku_platform_id
        JOIN skus           ON skus.id           = sku_platforms.sku_id
        JOIN platforms      ON platforms.id      = sku_platforms.platform_id
        WHERE skus.org_id           = :org_id
          AND scored_at             = :check_date
          AND content_total         < :threshold
          AND content_total IS NOT NULL
    )

    IF sku_id is not None:
        stmt += AND sku_platforms.sku_id = :sku_id

    IF platform_id is not None:
        stmt += AND sku_platforms.platform_id = :platform_id

    RETURN [dict(row) FOR row IN results]
```

---

## get_oos_candidates()

```python
async def get_oos_candidates(
    db: AsyncSession,
    org_id: UUID,
    check_date: date,
    sku_id: UUID | None,
    platform_id: UUID | None,
) -> list[dict]:

    stmt = (
        SELECT
            ContentScoreRead.sku_platform_id,
            SKU.name      AS sku_name,
            SKU.article   AS sku_article,
            Platform.name AS platform_name
        FROM content_score_reads
        JOIN sku_platforms  ON sku_platforms.id  = content_score_reads.sku_platform_id
        JOIN skus           ON skus.id           = sku_platforms.sku_id
        JOIN platforms      ON platforms.id      = sku_platforms.platform_id
        WHERE skus.org_id   = :org_id
          AND scored_at     = :check_date
          AND in_stock IS false
    )

    IF sku_id is not None:
        stmt += AND sku_platforms.sku_id = :sku_id

    IF platform_id is not None:
        stmt += AND sku_platforms.platform_id = :platform_id

    RETURN [dict(row) FOR row IN results]
    # Note: no content_total in result — value_after will be NULL for OOS events
```

---

## already_alerted()

```python
async def already_alerted(
    db: AsyncSession,
    config_id: UUID,
    sku_platform_id: UUID,
    scored_at: date,
) -> bool:

    count = SELECT COUNT(*)
            FROM alert_events
            WHERE config_id       = :config_id
              AND sku_platform_id = :sku_platform_id
              AND scored_at       = :scored_at

    RETURN count > 0

# Note: the UNIQUE constraint (config_id, sku_platform_id, scored_at) provides
# a second layer of dedup protection at the DB level if two concurrent check
# runs race past this check.
```

---

## create_event()

```python
async def create_event(
    db: AsyncSession,
    config_id: UUID,
    sku_platform_id: UUID,
    scored_at: date,
    alert_type: str,
    value_before: Decimal | None,
    value_after: Decimal | None,
) -> AlertEvent | None:

    event = AlertEvent(
        config_id=config_id,
        sku_platform_id=sku_platform_id,
        scored_at=scored_at,
        alert_type=alert_type,
        value_before=value_before,
        value_after=value_after,
        is_sent=False,
    )
    db.add(event)

    TRY:
        await db.flush()  # sends INSERT, does not commit
        RETURN event
    EXCEPT IntegrityError:
        await db.rollback()  # rollback the savepoint
        RETURN None  # dedup constraint fired — not an error
```

---

## send_alert_email()

```python
async def send_alert_email(ctx: AlertEmailContext) -> None:

    smtp_host = os.environ.get("SMTP_HOST", "")
    IF not smtp_host:
        logger.warning("SMTP_HOST not configured — alert email not sent")
        RETURN  # graceful: no exception raised

    TRY:
        import aiosmtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
    EXCEPT ImportError:
        logger.warning("aiosmtplib not installed — alert email skipped")
        RETURN  # graceful: no exception raised

    smtp_port     = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user     = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    from_email    = os.environ.get("SMTP_FROM_EMAIL", "alerts@cat.local")
    use_tls       = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"

    html_body = _render_html(ctx)  # builds HTML table from ctx.rows
    subject   = _build_subject(ctx)  # "[CAT] {type}: N SKU(s) — {date}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = from_email
    msg["To"]      = ", ".join(ctx.recipients)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    await aiosmtplib.send(
        msg,
        hostname=smtp_host,
        port=smtp_port,
        username=smtp_user or None,
        password=smtp_password or None,
        start_tls=use_tls,
    )
    # On SMTP error: exception propagates to caller (check_and_send_alerts)
    # which logs it and appends to errors[] — event stays is_sent=false
```

---

## AlertConfig CRUD (service.py wrappers)

```python
# create_alert_config
async def create_alert_config(db, org_id, data: AlertConfigCreate) -> AlertConfigResponse:
    config = await repository.create_config(
        db, org_id=org_id,
        alert_type=data.alert_type,
        email_recipients=[str(e) for e in data.email_recipients],
        sku_id=data.sku_id, platform_id=data.platform_id,
        threshold=data.threshold, is_active=data.is_active,
    )
    await db.commit()
    RETURN AlertConfigResponse.from_orm_model(config)

# update_alert_config
async def update_alert_config(db, org_id, config_id, data: AlertConfigUpdate) -> AlertConfigResponse | None:
    config = await repository.get_config(db, config_id, org_id)
    IF config is None:
        RETURN None  # router converts to 404

    recipients = [str(e) for e in data.email_recipients] IF data.email_recipients ELSE None
    updated = await repository.update_config(
        db, config=config,
        threshold=data.threshold,
        email_recipients=recipients,
        is_active=data.is_active,
    )
    await db.commit()
    RETURN AlertConfigResponse.from_orm_model(updated)

# delete_alert_config
async def delete_alert_config(db, org_id, config_id) -> bool:
    deleted = await repository.delete_config(db, config_id, org_id)
    await db.commit()
    RETURN deleted  # False → router converts to 404
```
