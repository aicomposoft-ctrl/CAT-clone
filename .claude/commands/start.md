# /start — Full Project Bootstrap

## Purpose
Bootstrap the CAT project: read documentation, scaffold services, bring up Docker stack.

## Steps

### 1. Read project context
```
Read: CLAUDE.md
Read: docs/PRD.md
Read: docs/Architecture.md
```

### 2. Verify prerequisites
- [ ] Docker + Docker Compose installed
- [ ] `.env` file exists (copy from `.env.example` if not)
- [ ] Secrets populated in `.env`

### 3. Start the stack
```bash
docker compose up -d
```

### 4. Run migrations
```bash
docker compose exec api alembic upgrade head
```

### 5. Verify services
```bash
docker compose ps
docker compose logs api --tail=20
```

### 6. Open endpoints
- API docs: http://localhost:8000/docs
- Frontend: http://localhost:3000
- Flower (Celery): http://localhost:5555
- Mailhog: http://localhost:8025
- MinIO console: http://localhost:9001

### 7. Show sprint status
Run `/next` to see current sprint progress and top 3 actions.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| API fails to start | Check `.env` — all REQUIRED_SECRETS present? |
| Migrations fail | `docker compose logs postgres` — DB up? |
| Collector crashes | Check proxy env vars (`PROXY_USER`, `PROXY_PASS`) |
| CLIP model error | Pre-download: `docker compose run processor python -c "from transformers import CLIPModel; CLIPModel.from_pretrained('openai/clip-vit-base-patch32')"` |
