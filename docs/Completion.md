# Completion — Commerce Analytics Tool (CAT)

> **SPARC Phase 7: Completion** | Deployment, CI/CD, Monitoring, Handoff

---

## 1. Deployment Plan

### Pre-Deployment Checklist

- [ ] All unit tests passing (pytest coverage ≥ 85%)
- [ ] Integration tests passing against staging DB
- [ ] BDD scenarios verified
- [ ] Security audit complete (no secrets in code, RLS working)
- [ ] Database migrations tested (alembic upgrade head)
- [ ] .env files configured for production
- [ ] SSL certificates provisioned
- [ ] MinIO buckets created with proper ACL
- [ ] Redis persistent volume configured
- [ ] ClickHouse schema applied
- [ ] Celery Beat schedule verified
- [ ] Email SMTP credentials tested
- [ ] Docker images built and pushed to registry
- [ ] Rollback plan tested on staging

### Deployment Sequence

```bash
# 1. Server preparation
ssh user@vps.cat.example.ru
mkdir -p /opt/cat-clone && cd /opt/cat-clone

# 2. Clone and configure
git clone git@github.com:org/cat-clone.git .
cp .env.example .env
# Edit .env with production values

# 3. Build images
docker compose -f docker-compose.yml -f docker-compose.prod.yml build

# 4. Start infrastructure services first
docker compose up -d postgres redis minio clickhouse
sleep 30  # Wait for DBs to initialize

# 5. Run migrations
docker compose run --rm api alembic upgrade head

# 6. Apply ClickHouse schema
docker compose run --rm api python -m app.core.clickhouse_init

# 7. Start application services
docker compose up -d api collector processor beat

# 8. Start frontend and proxy last
docker compose up -d frontend nginx

# 9. Verify health
curl -s http://localhost/api/v1/health | jq
docker compose ps
docker compose logs --tail=50 api
```

### Rollback Procedure

```bash
# Quick rollback to previous version
docker compose down api collector processor beat frontend

# Rollback DB migration if needed
docker compose run --rm api alembic downgrade -1

# Start previous version
docker pull registry.example.ru/cat-clone:previous-tag
sed -i 's/image: cat-clone:latest/image: cat-clone:previous-tag/' docker-compose.prod.yml
docker compose up -d
```

---

## 2. Docker Compose Production Config

```yaml
# docker-compose.prod.yml (production overrides)
version: '3.9'

services:
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./infrastructure/nginx/prod.conf:/etc/nginx/nginx.conf:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
      - nginx_logs:/var/log/nginx
    depends_on:
      - api
      - frontend
    restart: unless-stopped

  api:
    image: ${REGISTRY}/cat-api:${VERSION:-latest}
    environment:
      - ENV=production
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - CLICKHOUSE_URL=${CLICKHOUSE_URL}
      - S3_ENDPOINT=${S3_ENDPOINT}
      - JWT_SECRET=${JWT_SECRET}
    restart: unless-stopped
    deploy:
      replicas: 1
      resources:
        limits:
          cpus: '1.0'
          memory: 1G

  collector:
    image: ${REGISTRY}/cat-collector:${VERSION:-latest}
    restart: unless-stopped
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '1.0'
          memory: 2G

  processor:
    image: ${REGISTRY}/cat-processor:${VERSION:-latest}
    restart: unless-stopped
    volumes:
      - ml_models:/app/models  # Persist downloaded model weights
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G  # ML models need memory

  postgres:
    image: postgres:16-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=${POSTGRES_DB}
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    restart: unless-stopped

  clickhouse:
    image: clickhouse/clickhouse-server:latest
    volumes:
      - clickhouse_data:/var/lib/clickhouse
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    restart: unless-stopped

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      - MINIO_ROOT_USER=${MINIO_ROOT_USER}
      - MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD}
    volumes:
      - minio_data:/data
    restart: unless-stopped

volumes:
  postgres_data:
  clickhouse_data:
  redis_data:
  minio_data:
  ml_models:
  nginx_logs:
```

---

## 3. CI/CD Pipeline (GitHub Actions)

```yaml
# .github/workflows/deploy.yml
name: Build and Deploy

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env: { POSTGRES_DB: test_cat, POSTGRES_PASSWORD: test }
      redis:
        image: redis:7
    steps:
      - uses: actions/checkout@v4
      - name: Run tests
        run: |
          pip install -r services/api/requirements.txt
          pytest services/api/tests/ --cov --cov-report=xml
      - name: Coverage check
        run: coverage report --fail-under=85

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build and push images
        run: |
          docker build -t $REGISTRY/cat-api:$GITHUB_SHA ./services/api
          docker build -t $REGISTRY/cat-collector:$GITHUB_SHA ./services/collector
          docker build -t $REGISTRY/cat-processor:$GITHUB_SHA ./services/processor
          docker build -t $REGISTRY/cat-frontend:$GITHUB_SHA ./services/frontend
          docker push $REGISTRY/cat-api:$GITHUB_SHA
          docker push $REGISTRY/cat-collector:$GITHUB_SHA
          # etc.

  deploy:
    needs: build
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - name: Deploy to VPS
        run: |
          ssh $VPS_USER@$VPS_HOST "cd /opt/cat-clone && \
            VERSION=$GITHUB_SHA docker compose -f docker-compose.yml -f docker-compose.prod.yml pull && \
            VERSION=$GITHUB_SHA docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d && \
            docker compose run --rm api alembic upgrade head"
```

---

## 4. Monitoring & Alerting

### Key Metrics

| Metric | Threshold | Alert Channel |
|--------|-----------|---------------|
| API response time p99 | > 1000ms | Telegram bot |
| API error rate | > 2% | Telegram + Email |
| Scraper success rate | < 80% | Telegram + Email |
| Content scoring lag | > 6h | Email |
| Celery queue depth | > 500 tasks | Telegram |
| PostgreSQL disk usage | > 80% | Email |
| ClickHouse disk usage | > 80% | Email |
| Redis memory | > 90% | Telegram |
| MinIO storage | > 85% | Email |
| Container down | Any | Telegram (immediate) |

### Monitoring Stack

```yaml
# Lightweight monitoring via docker-compose
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./infrastructure/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:latest
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
    volumes:
      - grafana_data:/var/lib/grafana
    ports:
      - "3001:3000"

  flower:
    image: mher/flower:latest
    command: celery --broker=${REDIS_URL} flower --port=5555
    # Internal only, not exposed to internet
```

### Application-Level Healthcheck

```python
# GET /api/v1/health
@app.get("/api/v1/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {
            "postgres": await check_postgres(),
            "redis": await check_redis(),
            "clickhouse": await check_clickhouse(),
            "minio": await check_minio(),
            "celery": await check_celery()
        }
    }
```

---

## 5. Logging Strategy

```python
# Structured logging (JSON format for log aggregation)
import structlog

logger = structlog.get_logger()

# Usage in scraper
logger.info("scrape_completed",
    platform="wildberries",
    sku_count=1247,
    duration_seconds=2743,
    failed_count=3,
    proxy_rotations=12
)

# Log levels:
# DEBUG: individual scrape requests
# INFO: cycle completions, scoring results, alerts sent
# WARNING: partial failures, schema changes detected
# ERROR: scraper failures, ML errors
# CRITICAL: DB down, queue blocked

# Log retention: 30 days local, 90 days in aggregated storage
```

---

## 6. Handoff Checklists

### For Development Team

- [ ] Repository access: GitHub org permissions granted
- [ ] Development environment: Docker Compose + make dev runs cleanly
- [ ] Database migrations: alembic revision history understood
- [ ] Scraper modules: base class + 3 example scrapers reviewed
- [ ] ML models: CLIP + ruBERT downloaded to models/ directory
- [ ] Test suite: pytest all green locally
- [ ] Code review guidelines: PR template configured
- [ ] API docs: http://localhost:8000/docs (auto-generated FastAPI)

### For QA Team

- [ ] Staging environment access provided
- [ ] Test data: seed script available (`make seed-data`)
- [ ] Test accounts: admin@test.cat, manager@test.cat
- [ ] BDD scenarios: Gherkin files in `tests/bdd/`
- [ ] Report templates: compare against Excel files in repo
- [ ] Bug reporting: GitHub Issues with template

### For Operations Team

- [ ] VPS access: SSH keys for production server
- [ ] Docker registry: credentials and image naming convention
- [ ] Runbooks: `docs/ops/runbooks/` (restart procedures, common issues)
- [ ] Monitoring: Grafana dashboard URL + credentials
- [ ] Alerting: Telegram bot token configured
- [ ] Backup: daily postgres_data dump to S3 (cron configured)
- [ ] Escalation: emergency contacts list

---

## 7. Environment Variables Reference

```bash
# .env.example — copy to .env and fill in values

# Application
ENV=development                          # development | production
DEBUG=false
SECRET_KEY=                              # Generate: openssl rand -hex 32
JWT_SECRET=                              # Generate: openssl rand -hex 32
JWT_EXPIRE_MINUTES=60

# Database
DATABASE_URL=postgresql://cat:pass@postgres:5432/cat
POSTGRES_DB=cat
POSTGRES_USER=cat
POSTGRES_PASSWORD=

# ClickHouse
CLICKHOUSE_URL=http://clickhouse:8123
CLICKHOUSE_DB=cat_analytics

# Redis
REDIS_URL=redis://redis:6379/0

# MinIO S3
S3_ENDPOINT=http://minio:9000
S3_ACCESS_KEY=
S3_SECRET_KEY=
S3_BUCKET_REFERENCES=cat-references
S3_BUCKET_COLLECTED=cat-collected

# Email
SMTP_HOST=smtp.mailgun.org
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
EMAIL_FROM=alerts@cat.example.ru

# Celery
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# Registry (CI/CD)
REGISTRY=registry.example.ru/cat
VERSION=latest
```
