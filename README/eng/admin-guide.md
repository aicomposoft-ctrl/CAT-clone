# CAT Administrator Guide

## User Management

### Roles and Permissions

| Role | Capabilities |
|------|-------------|
| `admin` | Full access: user management, billing, platform configuration, all data |
| `manager` | CRUD SKUs, view all data, export reports, configure alerts, upload plans |
| `viewer` | Read-only: view data, export reports |

### Creating a User

```bash
# Via API (requires admin JWT)
curl -X POST https://your-domain.com/api/v1/auth/users \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "manager@brand.com",
    "password": "SecurePassword123",
    "role": "manager",
    "org_id": "<organization-uuid>"
  }'
```

### Account Lockout

Accounts are automatically locked for 15 minutes after 5 failed login attempts. Unlock via API:

```bash
curl -X POST https://your-domain.com/api/v1/auth/unlock \
  -H "Authorization: Bearer <admin-token>" \
  -d '{"email": "user@brand.com"}'
```

---

## System Configuration

### Platform (Scraper) Management

Administrators can add and configure platforms via API:

```bash
# Add a new platform
curl -X POST https://your-domain.com/api/v1/platforms \
  -H "Authorization: Bearer <admin-token>" \
  -d '{
    "name": "Amazon",
    "type": "marketplace",
    "scraper_module": "amazon",
    "schedule_cron": "0 2 * * *",
    "is_active": true
  }'
```

### Data Collection Schedule

By default, data collection is triggered by Celery Beat on the following schedule:

| Task | Schedule | Description |
|------|----------|-------------|
| Content + reviews | Daily at 02:00 | Full collection cycle |
| Prices | Every 4 hours | Price change monitoring |
| Alerts | Every hour | Check and dispatch alerts |

The schedule can be changed via Celery Beat environment variables or directly in `services/collector/app/celery_app.py`.

### Alert Configuration

```bash
# Create an alert configuration
curl -X POST https://your-domain.com/api/v1/alerts/config \
  -H "Authorization: Bearer <admin-token>" \
  -d '{
    "org_id": "<uuid>",
    "alert_type": "content_drop",
    "threshold": 70.0,
    "email_recipients": ["alerts@brand.com", "manager@brand.com"],
    "is_active": true
  }'
```

Alert types:
- `content_drop` — content score falls below threshold
- `price_change` — price change exceeds threshold
- `competitor_promo` — competitor promotion detected
- `oos` — out-of-stock

---

## Monitoring and Logging

### Celery Dashboard (Flower)

Flower is available on port 5555 (internal network only):

```bash
# Access locally via SSH tunnel
ssh -L 5555:localhost:5555 user@your-vps-ip
# Open: http://localhost:5555
```

Flower shows:
- Active scraping tasks
- Task execution history
- Worker health status

### Healthcheck API

```bash
# Status of all subsystems
curl -s https://your-domain.com/api/v1/health | jq

# Example response:
{
  "status": "ok",
  "checks": {
    "postgres": "ok",
    "redis": "ok",
    "clickhouse": "ok",
    "minio": "ok",
    "celery": "ok"
  }
}
```

### Viewing Logs

```bash
# API logs (FastAPI)
docker compose logs --follow api

# Collector logs (scraping workers)
docker compose logs --follow collector

# ML processor logs
docker compose logs --follow processor

# Scheduler logs (Beat)
docker compose logs --follow beat

# All services, last 100 lines
docker compose logs --tail=100
```

### Metrics (Prometheus + Grafana)

Prometheus is available on port 9090, Grafana on port 3001.

Key metrics to monitor:

| Metric | Alert Threshold | Channel |
|--------|----------------|---------|
| API p99 latency | > 1000ms | Telegram |
| API error rate | > 2% | Telegram + Email |
| Scraper success rate | < 80% | Telegram + Email |
| Celery queue depth | > 500 tasks | Telegram |
| PostgreSQL disk | > 80% | Email |
| ClickHouse disk | > 80% | Email |
| Redis memory | > 90% | Telegram |

---

## Backup Procedures

### PostgreSQL

```bash
# Create a backup
docker compose exec postgres pg_dump -U cat_user cat_db > backup_$(date +%Y%m%d).sql

# Automated backup via cron (add to VPS crontab)
# 0 3 * * * docker compose -f /opt/cat-clone/docker-compose.yml exec -T postgres pg_dump -U cat_user cat_db > /opt/backups/cat_$(date +%Y%m%d).sql

# Restore from backup
cat backup_20250320.sql | docker compose exec -T postgres psql -U cat_user cat_db
```

### MinIO (Reference Images)

```bash
# Sync to external S3-compatible storage
docker compose exec minio mc mirror /data s3://backup-bucket/cat-images/
```

### ClickHouse

```bash
# Backup analytics data
docker compose exec clickhouse clickhouse-backup create
```

---

## Troubleshooting

### Issue: API not responding

```bash
# Check status
docker compose ps api

# View logs
docker compose logs --tail=100 api

# Restart
docker compose restart api
```

### Issue: Scraper stuck

```bash
# Check active tasks
docker compose exec collector celery -A tasks inspect active

# Revoke a stuck task
docker compose exec collector celery -A tasks control revoke <task-id> --terminate

# Restart workers
docker compose restart collector
```

### Issue: ML models not loading

```bash
# Check model cache
docker compose exec processor ls /root/.cache/huggingface/

# Force download models
docker compose exec processor python -c "
from transformers import CLIPModel, AutoTokenizer
CLIPModel.from_pretrained('openai/clip-vit-base-patch32')
AutoTokenizer.from_pretrained('cointegrated/rubert-tiny-sentiment-balanced')
"
```

### Issue: Email alerts not sending

```bash
# Test SMTP connection
docker compose exec api python -c "
import smtplib
s = smtplib.SMTP('$SMTP_HOST', 587)
s.starttls()
s.login('$SMTP_USER', '$SMTP_PASSWORD')
print('SMTP OK')
"

# In dev mode, emails are captured by MailHog
# http://localhost:8025
```
