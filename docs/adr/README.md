# Architecture Decision Records (ADR)

Журнал ключевых архитектурных решений проекта CAT.

## Формат

Каждый ADR содержит: контекст → рассматриваемые варианты → решение → последствия.

## Индекс

| ADR | Решение | Статус |
|-----|---------|--------|
| [ADR-001](ADR-001-distributed-monolith.md) | Distributed Monolith вместо Microservices | ✅ Accepted |
| [ADR-002](ADR-002-postgresql-clickhouse-dual-db.md) | PostgreSQL + ClickHouse dual database | ✅ Accepted |
| [ADR-003](ADR-003-multitenant-org-id.md) | Multi-tenant isolation через org_id + RLS | ✅ Accepted |
| [ADR-004](ADR-004-celery-redis-task-queue.md) | Celery + Redis для асинхронных задач | ✅ Accepted |
| [ADR-005](ADR-005-minio-s3-image-storage.md) | MinIO для хранения изображений | ✅ Accepted |
| [ADR-006](ADR-006-ml-clip-e5-rubert.md) | ML Pipeline: CLIP + multilingual-e5 + ruBERT | ✅ Accepted |
| [ADR-007](ADR-007-playwright-scrapy-scraping.md) | Playwright + Scrapy для скрапинга | ✅ Accepted |
| [ADR-008](ADR-008-jwt-rbac-auth.md) | JWT + RBAC аутентификация | ✅ Accepted |
| [ADR-009](ADR-009-react-antdesign-frontend.md) | React + TypeScript + Ant Design | ✅ Accepted |
| [ADR-010](ADR-010-docker-compose-vps-deploy.md) | Docker Compose на VPS вместо Kubernetes | ✅ Accepted |

## Как добавить новый ADR

1. Скопируй шаблон: `ADR-NNN-short-name.md`
2. Заполни: контекст, варианты (таблица), решение, последствия
3. Обнови этот README
4. Коммит: `docs(adr): ADR-NNN short description`
