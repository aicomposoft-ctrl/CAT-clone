"""
Async email sender for the alerts domain.

Uses aiosmtplib for non-blocking SMTP.  If SMTP is not configured
(SMTP_HOST missing or empty) the function logs the email body instead
of raising — this keeps the app functional in dev without a mail server.

HTML email format: a simple table listing the triggered SKUs.
"""

import logging
import os
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AlertEmailContext:
    """All information needed to render one alert email."""

    alert_type: str
    org_name: str
    check_date: date
    recipients: list[str]
    rows: list[dict]  # each: {sku_name, sku_article, platform_name, value_after}


def _render_html(ctx: AlertEmailContext) -> str:
    type_label = {
        "content_drop": "Падение контент-скора",
        "oos": "Нет в наличии (Out of Stock)",
    }.get(ctx.alert_type, ctx.alert_type)

    rows_html = ""
    for r in ctx.rows:
        article = r.get("sku_article") or "—"
        value = r.get("value_after")
        score_cell = f"{value:.1f}" if value is not None else "—"
        rows_html += (
            f"<tr>"
            f"<td style='padding:4px 8px;border:1px solid #ddd'>{r['sku_name']}</td>"
            f"<td style='padding:4px 8px;border:1px solid #ddd'>{article}</td>"
            f"<td style='padding:4px 8px;border:1px solid #ddd'>{r['platform_name']}</td>"
            f"<td style='padding:4px 8px;border:1px solid #ddd;text-align:right'>{score_cell}</td>"
            f"</tr>"
        )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;font-size:14px;color:#333">
  <h2 style="color:#d9534f">[CAT] {type_label}</h2>
  <p>Организация: <strong>{ctx.org_name}</strong><br>
     Дата: <strong>{ctx.check_date}</strong><br>
     Затронутых позиций: <strong>{len(ctx.rows)}</strong></p>
  <table style="border-collapse:collapse;width:100%;max-width:700px">
    <thead>
      <tr style="background:#4472C4;color:#fff">
        <th style="padding:6px 8px;text-align:left">Название SKU</th>
        <th style="padding:6px 8px;text-align:left">Артикул</th>
        <th style="padding:6px 8px;text-align:left">Платформа</th>
        <th style="padding:6px 8px;text-align:right">Значение</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
  <p style="margin-top:16px;font-size:12px;color:#999">
    CAT — Commerce Analytics Tool &bull; Это автоматическое уведомление.
  </p>
</body>
</html>"""


def _build_subject(ctx: AlertEmailContext) -> str:
    label = {
        "content_drop": "Content drop",
        "oos": "Out of Stock",
    }.get(ctx.alert_type, ctx.alert_type)
    return f"[CAT] {label}: {len(ctx.rows)} SKU(s) — {ctx.check_date}"


async def send_alert_email(ctx: AlertEmailContext) -> None:
    """
    Send HTML alert email to all recipients in *ctx*.

    Behaviour:
      - SMTP_HOST not configured → log warning, return (no error raised).
      - aiosmtplib not installed → log warning, return.
      - SMTP error → log error, re-raise so the caller can mark the event unsent.
    """
    smtp_host = os.environ.get("SMTP_HOST", "")
    if not smtp_host:
        logger.warning(
            "SMTP_HOST not configured — alert email not sent (recipients: %s)",
            ctx.recipients,
        )
        return

    try:
        import aiosmtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
    except ImportError:
        logger.warning("aiosmtplib not installed — alert email skipped")
        return

    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    from_email = os.environ.get("SMTP_FROM_EMAIL", "alerts@cat.local")
    use_tls = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"

    html_body = _render_html(ctx)
    subject = _build_subject(ctx)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = ", ".join(ctx.recipients)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    await aiosmtplib.send(
        msg,
        hostname=smtp_host,
        port=smtp_port,
        username=smtp_user or None,
        password=smtp_password or None,
        start_tls=use_tls,
    )
    logger.info(
        "Alert email sent: type=%s recipients=%s rows=%d",
        ctx.alert_type,
        ctx.recipients,
        len(ctx.rows),
    )
