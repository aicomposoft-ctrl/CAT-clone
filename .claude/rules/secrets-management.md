# Secrets Management — CAT

## Rule 1: Never in Code

Secrets NEVER appear in:
- Source code (`.py`, `.ts`, `.js`, `.tsx`)
- `docker-compose.yml` (use `env_file` or Docker secrets)
- Git-tracked files of any kind
- Log output (mask secrets in exception handlers)
- Error messages returned to clients

## Rule 2: Startup Validation

All required secrets validated at service startup:

```python
# services/api/app/core/config.py
import os, sys, logging

REQUIRED_SECRETS = [
    "JWT_SECRET",
    "POSTGRES_URL",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
    "MINIO_ENDPOINT",
    "SMTP_HOST",
    "SMTP_PASSWORD",
    "SMTP_FROM_EMAIL",
]

def validate_secrets():
    missing = [s for s in REQUIRED_SECRETS if not os.environ.get(s)]
    if missing:
        logging.critical(f"Missing required secrets: {missing}")
        sys.exit(1)
```

Call `validate_secrets()` in `app/main.py` on startup, before any DB connections.

## Rule 3: Environment Files

```
.env.example   ← committed (template with placeholders, NO real values)
.env           ← NOT committed (gitignore entry mandatory)
.env.prod      ← NOT committed (production secrets)
.env.test      ← NOT committed (test secrets)
```

`.env.example` format:
```bash
JWT_SECRET=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
POSTGRES_URL=postgresql://cat_user:<password>@postgres:5432/cat_db
MINIO_ACCESS_KEY=<minio-access-key>
MINIO_SECRET_KEY=<minio-secret-key>
MINIO_ENDPOINT=minio:9000
SMTP_HOST=<smtp-host>
SMTP_PASSWORD=<smtp-password>
SMTP_FROM_EMAIL=noreply@yourdomain.com
```

## Rule 4: No Fallback Defaults

```python
# WRONG — fallback default for security-critical secret
JWT_SECRET = os.environ.get("JWT_SECRET", "fallback-default-secret")

# CORRECT — fail if missing
JWT_SECRET = os.environ["JWT_SECRET"]  # raises KeyError if missing
```

Exception: Non-security config may have defaults (timeouts, limits, feature flags).

## Rule 5: External Service Credentials

| Service | Env Var | Notes |
|---------|---------|-------|
| PostgreSQL | `POSTGRES_URL` | Full connection string |
| ClickHouse | `CLICKHOUSE_URL` | Full connection string |
| Redis | `REDIS_URL` | Full connection string |
| MinIO | `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` | S3-compatible |
| SMTP | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | Email alerts |
| Proxy | `PROXY_LIST_URL` or `PROXY_USER`, `PROXY_PASS` | Scraper proxies |

## Rule 6: Docker Production

In production, use Docker secrets or a secrets manager:

```yaml
# docker-compose.prod.yml
secrets:
  jwt_secret:
    external: true
  postgres_url:
    external: true

services:
  api:
    secrets:
      - jwt_secret
      - postgres_url
    environment:
      JWT_SECRET_FILE: /run/secrets/jwt_secret
```

## Rotation Policy

- JWT_SECRET: rotate every 90 days (coordinate with active sessions)
- Proxy credentials: rotate monthly or on compromise
- MinIO keys: rotate every 180 days
- SMTP password: rotate annually or on compromise
