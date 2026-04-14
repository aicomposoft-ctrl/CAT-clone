# /deploy [env] — Deploy Checklist

## Usage
```
/deploy          # Default: production checklist
/deploy staging  # Staging deploy
/deploy local    # Local docker-compose up
```

## Local Deploy

```bash
# 1. Verify .env exists (never .env.example in production)
cp .env.example .env  # then fill in real values

# 2. Build and start all services
docker compose up --build -d

# 3. Run migrations
docker compose exec api alembic upgrade head

# 4. Verify all services healthy
docker compose ps

# 5. Check logs for startup errors
docker compose logs api collector processor
```

**Healthcheck endpoints:**
- API: `GET /health`
- Frontend: `http://localhost:3000`
- Flower (Celery): `http://localhost:5555`
- MinIO Console: `http://localhost:9001`
- MailHog: `http://localhost:8025`

## Staging Deploy

```bash
# 1. Push to staging branch
git push origin feature/<name>

# 2. SSH to VPS
ssh deploy@<staging-host>

# 3. Pull latest
cd /opt/cat && git pull origin feature/<name>

# 4. Rebuild changed services only
docker compose up --build -d api collector processor

# 5. Run migrations
docker compose exec api alembic upgrade head

# 6. Smoke test
curl -X POST /api/v1/auth/login -d '{"email":"test@cat.io","password":"..."}'
```

## Production Deploy Checklist

### Pre-deploy
- [ ] All tests passing: `docker compose exec api pytest`
- [ ] No secrets in code: `git diff HEAD~1 | grep -E "(SECRET|PASSWORD|KEY)" `
- [ ] Migrations tested on staging first
- [ ] `.env.prod` updated with any new required secrets
- [ ] `docker-compose.prod.yml` reviewed

### Deploy
```bash
# On VPS
cd /opt/cat
git pull origin main
docker compose -f docker-compose.prod.yml up --build -d
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
```

### Post-deploy
- [ ] All containers healthy: `docker compose ps`
- [ ] API health check responds: `curl https://<domain>/health`
- [ ] Celery workers active: check Flower dashboard
- [ ] No critical errors in logs: `docker compose logs --tail=50 api`
- [ ] Alert: notify team that deploy is complete

## Rollback

```bash
# Roll back to previous image
docker compose down
git checkout <previous-tag>
docker compose up --build -d
docker compose exec api alembic downgrade -1
```

## Services Reference

| Service | Port | Description |
|---------|------|-------------|
| nginx | 80, 443 | Reverse proxy + SSL |
| api | 8000 | FastAPI backend |
| frontend | 3000 | React dashboard |
| postgres | 5432 | Primary DB |
| clickhouse | 8123 | Analytics DB |
| redis | 6379 | Cache + queue |
| minio | 9000/9001 | Object storage |
| collector | — | Celery workers |
| processor | — | ML pipeline |
| beat | — | Celery scheduler (1 replica only!) |
| flower | 5555 | Celery monitor |
| mailhog | 1025/8025 | Email testing |
