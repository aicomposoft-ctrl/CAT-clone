# Руководство администратора CAT

## Управление пользователями

### Роли и права доступа

| Роль | Возможности |
|------|-------------|
| `admin` | Полный доступ: управление пользователями, биллинг, конфигурация платформ, просмотр всех данных |
| `manager` | CRUD SKU, просмотр всех данных, экспорт отчётов, настройка алертов, загрузка планов |
| `viewer` | Только чтение: просмотр данных, экспорт отчётов |

### Создание пользователя

```bash
# Через API (требует admin JWT)
curl -X POST https://your-domain.ru/api/v1/auth/users \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "manager@brand.ru",
    "password": "SecurePassword123",
    "role": "manager",
    "org_id": "<organization-uuid>"
  }'
```

### Блокировка аккаунта

Аккаунт автоматически блокируется на 15 минут после 5 неудачных попыток входа. Разблокировка через API:

```bash
curl -X POST https://your-domain.ru/api/v1/auth/unlock \
  -H "Authorization: Bearer <admin-token>" \
  -d '{"email": "user@brand.ru"}'
```

---

## Конфигурация системы

### Управление платформами (scrapers)

Администратор может добавлять и настраивать платформы через API:

```bash
# Добавить новую платформу
curl -X POST https://your-domain.ru/api/v1/platforms \
  -H "Authorization: Bearer <admin-token>" \
  -d '{
    "name": "Яндекс Маркет",
    "type": "marketplace",
    "scraper_module": "yandex_market",
    "schedule_cron": "0 2 * * *",
    "is_active": true
  }'
```

### Расписание сбора данных

По умолчанию сбор данных запускается Celery Beat по расписанию:

| Задача | Расписание | Описание |
|--------|-----------|----------|
| Контент + отзывы | Каждый день в 02:00 | Полный цикл сбора |
| Цены | Каждые 4 часа | Мониторинг изменений цен |
| Алерты | Каждый час | Проверка и отправка алертов |

Изменить расписание можно через переменные окружения Celery Beat или напрямую в `services/collector/app/celery_app.py`.

### Настройка алертов

```bash
# Создать конфигурацию алерта
curl -X POST https://your-domain.ru/api/v1/alerts/config \
  -H "Authorization: Bearer <admin-token>" \
  -d '{
    "org_id": "<uuid>",
    "alert_type": "content_drop",
    "threshold": 70.0,
    "email_recipients": ["alerts@brand.ru", "manager@brand.ru"],
    "is_active": true
  }'
```

Типы алертов:
- `content_drop` — падение content score ниже порога
- `price_change` — изменение цены выше порога
- `competitor_promo` — промо конкурента
- `oos` — out-of-stock (нет в наличии)

---

## Мониторинг и логирование

### Дашборд Celery (Flower)

Flower доступен на порту 5555 (только внутри сети):

```bash
# Для локального доступа через туннель
ssh -L 5555:localhost:5555 user@your-vps-ip
# Открыть: http://localhost:5555
```

Flower показывает:
- Активные задачи scraping
- Историю выполнения задач
- Состояние воркеров

### Healthcheck API

```bash
# Статус всех подсистем
curl -s https://your-domain.ru/api/v1/health | jq

# Пример ответа:
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

### Просмотр логов

```bash
# Логи API (FastAPI)
docker compose logs --follow api

# Логи сборщика (scraping workers)
docker compose logs --follow collector

# Логи ML-процессора
docker compose logs --follow processor

# Логи планировщика (Beat)
docker compose logs --follow beat

# Все логи за последние 100 строк
docker compose logs --tail=100
```

### Метрики (Prometheus + Grafana)

Prometheus доступен на порту 9090, Grafana — на порту 3001.

Ключевые метрики для мониторинга:

| Метрика | Порог алерта | Канал |
|---------|-------------|-------|
| API p99 latency | > 1000ms | Telegram |
| API error rate | > 2% | Telegram + Email |
| Scraper success rate | < 80% | Telegram + Email |
| Celery queue depth | > 500 задач | Telegram |
| PostgreSQL disk | > 80% | Email |
| ClickHouse disk | > 80% | Email |
| Redis memory | > 90% | Telegram |

---

## Резервное копирование

### PostgreSQL

```bash
# Создать резервную копию
docker compose exec postgres pg_dump -U cat_user cat_db > backup_$(date +%Y%m%d).sql

# Автоматический backup через cron (добавить в crontab на VPS)
# 0 3 * * * docker compose -f /opt/cat-clone/docker-compose.yml exec -T postgres pg_dump -U cat_user cat_db > /opt/backups/cat_$(date +%Y%m%d).sql

# Восстановление из backup
cat backup_20250320.sql | docker compose exec -T postgres psql -U cat_user cat_db
```

### MinIO (изображения)

```bash
# Синхронизация на внешний S3-совместимый хранилище
docker compose exec minio mc mirror /data s3://backup-bucket/cat-images/
```

### ClickHouse

```bash
# Backup аналитических данных
docker compose exec clickhouse clickhouse-backup create
```

---

## Устранение неполадок

### Проблема: API не отвечает

```bash
# Проверить статус
docker compose ps api

# Посмотреть логи
docker compose logs --tail=100 api

# Перезапустить
docker compose restart api
```

### Проблема: Scraper завис

```bash
# Проверить активные задачи
docker compose exec collector celery -A tasks inspect active

# Отозвать зависшую задачу
docker compose exec collector celery -A tasks control revoke <task-id> --terminate

# Перезапустить воркеры
docker compose restart collector
```

### Проблема: ML-модели не загружаются

```bash
# Проверить наличие моделей в кеше
docker compose exec processor ls /root/.cache/huggingface/

# Принудительно скачать модели
docker compose exec processor python -c "
from transformers import CLIPModel, AutoTokenizer
CLIPModel.from_pretrained('openai/clip-vit-base-patch32')
AutoTokenizer.from_pretrained('cointegrated/rubert-tiny-sentiment-balanced')
"
```

### Проблема: Нет email-алертов

```bash
# Тест SMTP-подключения
docker compose exec api python -c "
import smtplib
s = smtplib.SMTP('$SMTP_HOST', 587)
s.starttls()
s.login('$SMTP_USER', '$SMTP_PASSWORD')
print('SMTP OK')
"

# В dev-режиме письма перехватывает MailHog
# http://localhost:8025
```
