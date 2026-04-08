# ADR-010: Docker Compose на VPS вместо Kubernetes

**Дата:** 2026-03-01  
**Статус:** Accepted  
**Авторы:** CAT Team

---

## Контекст

CAT деплоится на VPS (AdminVPS/HOSTKEY). На старте: 1 сервер, 10–50 клиентов, небольшая команда. Нужен простой, воспроизводимый деплой.

## Рассматриваемые варианты

| Вариант | Сложность | Требования к серверу | Self-hosted |
|---------|-----------|---------------------|-------------|
| **Docker Compose (выбран)** | Низкая | 1 VPS | ✅ |
| Kubernetes (k8s) | Высокая | 3+ узла или managed | ✅/❌ |
| Kamal (mrsk) | Низкая | 1 VPS | ✅ |
| Render/Railway | Низкая | Нет | ❌ |

## Решение

**Docker Compose** с единым `docker-compose.yml` для всех сервисов.

```
Сервисы: nginx, api, collector, processor, beat, flower,
         frontend, postgres, clickhouse, redis, minio, mailhog
```

- **Nginx** — reverse proxy + SSL termination (Let's Encrypt)
- **Beat** — строго 1 реплика (иначе дублирование Celery-задач)
- **Healthcheck** на каждом сервисе
- Данные: именованные Docker volumes для PostgreSQL, ClickHouse, MinIO

**Путь к масштабированию:** при росте нагрузки — `collector` и `processor` выносятся на отдельный сервер через Docker Compose override (`-f docker-compose.collector.yml`). Kubernetes рассматривается при >500 клиентов.

## Последствия

- **Положительные:** деплой = `git pull && docker compose up -d --build`; воспроизводимо локально; нет платы за managed Kubernetes
- **Отрицательные:** нет автоматического failover; zero-downtime deploy требует ручной настройки (blue-green через Nginx)
- **Бэкапы:** `pg_dump` в cron, бэкап MinIO volume → внешнее хранилище
