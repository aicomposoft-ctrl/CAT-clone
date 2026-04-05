# CAT System Deployment Guide

## Environment Requirements

### Software
| Component | Version | Note |
|-----------|---------|------|
| Docker | 24.0+ | Required |
| Docker Compose | 2.20+ | Bundled with Docker Desktop |
| Git | 2.x | For cloning the repository |
| Bash | 5.x | Linux/macOS |

### Hardware Requirements

| Configuration | CPU | RAM | Disk |
|--------------|-----|-----|------|
| MVP (dev) | 4 vCPU | 8 GB | 50 GB SSD |
| Staging | 4 vCPU | 16 GB | 100 GB SSD |
| Production (v1.0) | 8 vCPU | 32 GB | 500 GB SSD |

> **Note:** ML models (CLIP + ruBERT) require an additional ~4 GB RAM for the processor service. On first launch, HuggingFace downloads model weights (~2-3 GB) — ensure internet access is available.

---

## Quick Start (Local Development)

```bash
# 1. Clone the repository
git clone https://github.com/your-org/cat-clone.git
cd cat-clone

# 2. Configure environment variables
cp .env.example .env
# Edit .env — minimum for dev:
#   POSTGRES_PASSWORD=devpassword
#   MINIO_ACCESS_KEY=minioadmin
#   MINIO_SECRET_KEY=minioadmin123
#   JWT_SECRET=$(openssl rand -hex 32)
#   CLICKHOUSE_PASSWORD=chpassword

# 3. Start all services
docker compose up -d

# 4. Run database migrations
docker compose run --rm api alembic upgrade head

# 5. Initialize ClickHouse schema
docker compose run --rm api python -m app.core.clickhouse_init

# 6. Verify health
curl http://localhost:8000/health
# Response: {"status": "ok", "checks": {...}}

# 7. Open the dashboard
open http://localhost:3000
```

---

## Full Production Deployment

### Step 1. Server Preparation

```bash
# Connect to VPS (AdminVPS/HOSTKEY or equivalent)
ssh user@your-vps-ip

# Install Docker (Ubuntu 22.04)
curl -fsSL https://get.docker.com | bash
usermod -aG docker $USER

# Create application directory
mkdir -p /opt/cat-clone && cd /opt/cat-clone
```

### Step 2. Clone and Configure

```bash
git clone git@github.com:your-org/cat-clone.git .
cp .env.example .env

# Fill in all variables in .env:
# - JWT_SECRET: openssl rand -hex 32
# - POSTGRES_PASSWORD: strong password
# - MINIO_ACCESS_KEY / MINIO_SECRET_KEY
# - SMTP_HOST / SMTP_PASSWORD (for email alerts)
# - CLICKHOUSE_PASSWORD
nano .env
```

### Step 3. SSL Certificates

```bash
# Obtain Let's Encrypt certificate
apt install certbot
certbot certonly --standalone -d your-domain.com

# Copy to nginx directory
cp /etc/letsencrypt/live/your-domain.com/fullchain.pem infrastructure/nginx/ssl/
cp /etc/letsencrypt/live/your-domain.com/privkey.pem infrastructure/nginx/ssl/
```

### Step 4. Build and Launch

```bash
# Build images
docker compose -f docker-compose.yml -f docker-compose.prod.yml build

# Start infrastructure services
docker compose up -d postgres redis minio clickhouse
sleep 30

# Apply migrations
docker compose run --rm api alembic upgrade head
docker compose run --rm api python -m app.core.clickhouse_init

# Start application
docker compose up -d api collector processor beat
docker compose up -d frontend nginx

# Verify
docker compose ps
curl -s https://your-domain.com/api/v1/health | jq
```

### Service Startup Order

```
postgres, redis, minio, clickhouse  → api, processor, beat  → collector  → frontend, nginx
```

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `JWT_SECRET` | Yes | JWT signing secret. `openssl rand -hex 32` |
| `POSTGRES_URL` | Yes | PostgreSQL connection string |
| `POSTGRES_PASSWORD` | Yes | Database user password |
| `REDIS_URL` | Yes | `redis://redis:6379/0` |
| `CLICKHOUSE_URL` | Yes | `http://clickhouse:8123` |
| `CLICKHOUSE_PASSWORD` | Yes | ClickHouse password |
| `MINIO_ENDPOINT` | Yes | `minio:9000` |
| `MINIO_ACCESS_KEY` | Yes | MinIO access key |
| `MINIO_SECRET_KEY` | Yes | MinIO secret key |
| `SMTP_HOST` | Yes | SMTP server for alerts |
| `SMTP_PASSWORD` | Yes | SMTP password |
| `ENV` | No | `development` / `production` |
| `DEBUG` | No | `false` (default) |

---

## Updating to a New Version

```bash
cd /opt/cat-clone

# Pull latest changes
git pull origin main

# Rebuild images
docker compose -f docker-compose.yml -f docker-compose.prod.yml build

# Apply migrations (if any)
docker compose run --rm api alembic upgrade head

# Restart services (zero-downtime for stateless services)
docker compose up -d --no-deps api collector processor beat frontend
```

---

## Rollback Procedure

```bash
# 1. Stop application
docker compose stop api collector processor beat frontend

# 2. Rollback DB migration (if applied)
docker compose run --rm api alembic downgrade -1

# 3. Switch to previous tag
git checkout <previous-tag>
docker compose -f docker-compose.yml -f docker-compose.prod.yml build

# 4. Restart
docker compose up -d
```

---

## Post-Deployment Verification

```bash
# All container statuses
docker compose ps

# API health check
curl -s http://localhost/api/v1/health | jq

# API logs
docker compose logs --tail=50 api

# Collector logs
docker compose logs --tail=50 collector

# Celery queue check
docker compose exec beat celery -A tasks inspect active
```
