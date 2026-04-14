# CAT Infrastructure Requirements

## Minimum Requirements (MVP)

### Hardware

| Service | CPU | RAM | Disk |
|---------|-----|-----|------|
| nginx | 0.1 vCPU | 64 MB | — |
| api | 1 vCPU | 512 MB | — |
| frontend | 0.1 vCPU | 128 MB | — |
| collector (×2) | 1 vCPU | 1 GB | — |
| processor | 2 vCPU | 4 GB | — |
| beat | 0.1 vCPU | 256 MB | — |
| flower | 0.1 vCPU | 128 MB | — |
| postgres | 1 vCPU | 1 GB | 50 GB SSD |
| clickhouse | 2 vCPU | 4 GB | 100 GB SSD |
| redis | 0.5 vCPU | 512 MB | 10 GB |
| minio | 0.5 vCPU | 512 MB | 200 GB SSD |
| **Total (MVP)** | **8 vCPU** | **12 GB** | **360 GB SSD** |

> **Recommended MVP VPS:** 8 vCPU / 16 GB RAM / 500 GB NVMe SSD

---

## Recommended Requirements (Production v1.0)

### Scaled Configuration

| Component | Configuration | Reason |
|-----------|--------------|--------|
| api | 1 vCPU / 1 GB | FastAPI async, low requirements |
| collector | 2× (2 vCPU / 2 GB) | Parallel scraping with Playwright |
| processor | 1× (2 vCPU / 4 GB) | CLIP + ruBERT ML models |
| beat | 1× (0.2 vCPU / 256 MB) | **Exactly 1 replica** — duplicates tasks otherwise |
| postgres | 2 vCPU / 4 GB / 200 GB SSD | ACID database, JSONB |
| clickhouse | 4 vCPU / 8 GB / 500 GB SSD | Time-series, fast aggregations |
| redis | 1 vCPU / 1 GB | Celery broker + cache |
| minio | 2 vCPU / 2 GB / 1 TB SSD | Image storage |
| **Total** | **~16 vCPU** | **~24 GB RAM** | **~2 TB SSD** |

---

## Network Requirements

### Public Ports

| Port | Protocol | Service | Note |
|------|----------|---------|------|
| 80 | TCP | nginx | HTTP → redirect HTTPS |
| 443 | TCP | nginx | HTTPS (Let's Encrypt) |

### Internal / Dev Ports

| Port | Service | Purpose |
|------|---------|---------|
| 8000 | api | FastAPI HTTP |
| 3000 | frontend | React dev server |
| 5432 | postgres | DB (Docker internal only) |
| 8123 | clickhouse | HTTP interface |
| 9000 | clickhouse / minio | CH native / MinIO S3 API |
| 9001 | minio | MinIO Console |
| 6379 | redis | Redis |
| 5555 | flower | Celery monitor |
| 1025 / 8025 | mailhog | Email testing (dev only) |

> In production — all ports except 80/443 **must be firewalled**. DB access only via Docker internal network.

### Outbound Connection Requirements

| Destination | Protocol | Note |
|-------------|----------|------|
| 110+ marketplaces | HTTPS | Scraping (via proxy) |
| HuggingFace Hub | HTTPS | ML model download (one time) |
| SMTP server | SMTP/587 | Email alert delivery |
| Docker Hub / registry | HTTPS | Image builds |
| Let's Encrypt | HTTPS | SSL certificates |

### Proxy Pool for Scraping

For scraping 110+ platforms, a pool of rotating proxy IPs is strongly recommended. Configure in `.env`:

```bash
PROXY_LIST_URL=http://proxy-provider.example.com/api/list
# or static list:
PROXY_USER=proxyuser
PROXY_PASS=proxypass
```

---

## Docker Services

| Service | Image | Role |
|---------|-------|------|
| `nginx` | `nginx:1.25-alpine` | Reverse proxy, SSL, static files |
| `api` | Custom (Python 3.11) | FastAPI REST API |
| `collector` | Custom (Python 3.11 + Playwright) | Celery workers, scrapers |
| `processor` | Custom (Python 3.11 + HuggingFace) | ML pipeline |
| `beat` | Custom (same as collector) | Celery Beat scheduler |
| `flower` | Custom | Celery monitoring UI |
| `frontend` | Custom (Node 18 → nginx) | React SPA |
| `postgres` | `postgres:16-alpine` | Primary database |
| `clickhouse` | `clickhouse/clickhouse-server:23.8-alpine` | Analytics database |
| `redis` | `redis:7-alpine` | Cache + task broker |
| `minio` | `minio/minio:latest` | S3-compatible image storage |
| `mailhog` | `mailhog/mailhog:latest` | Email testing (dev) |

---

## Dependencies

### Required External Services

| Service | Type | Purpose |
|---------|------|---------|
| SMTP server | Email | Alert delivery (Mailgun, SendGrid, Postfix) |
| Proxy pool | HTTP/SOCKS5 | IP rotation for scraping |

### Optional Integrations

| Service | Type | Purpose |
|---------|------|---------|
| Prometheus + Grafana | Monitoring | Metrics and alerting |
| Telegram Bot | Notifications | DevOps alerts |
| External S3 bucket | Backup | Database backups |

### License Requirements

All key components are Open Source:

| Component | License |
|-----------|---------|
| FastAPI | MIT |
| React | MIT |
| PostgreSQL | PostgreSQL License |
| ClickHouse | Apache 2.0 |
| Redis | BSD 3-Clause |
| MinIO | AGPL-3.0 |
| CLIP (OpenAI) | MIT |
| ruBERT | Apache 2.0 |
| Playwright | Apache 2.0 |
| Scrapy | BSD |

---

## Persistent Volumes

| Volume | Service | Contents |
|--------|---------|----------|
| `postgres_data` | postgres | PostgreSQL tables |
| `clickhouse_data` | clickhouse | Analytics tables |
| `redis_data` | redis | Celery task persistence |
| `minio_data` | minio | SKU images (references + collected) |
| `huggingface_cache` | processor | CLIP + ruBERT model weights |

> **Critical:** `minio_data` and `postgres_data` must be mounted to persistent VPS disks. Loss of these volumes = loss of all data.
