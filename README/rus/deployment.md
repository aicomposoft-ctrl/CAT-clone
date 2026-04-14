# Развертывание системы CAT

## Требования к окружению

### Программное обеспечение
| Компонент | Версия | Примечание |
|-----------|--------|------------|
| Docker | 24.0+ | Обязательно |
| Docker Compose | 2.20+ | Встроен в Docker Desktop |
| Git | 2.x | Для клонирования репозитория |
| Bash | 5.x | Linux/macOS |

### Аппаратные требования

| Конфигурация | CPU | RAM | Диск |
|-------------|-----|-----|------|
| MVP (dev) | 4 vCPU | 8 GB | 50 GB SSD |
| Staging | 4 vCPU | 16 GB | 100 GB SSD |
| Production (v1.0) | 8 vCPU | 32 GB | 500 GB SSD |

> **Примечание:** ML-модели (CLIP + ruBERT) требуют дополнительно ~4 GB RAM для процессора. При первом запуске HuggingFace скачивает веса (~2-3 GB) — убедитесь в доступе к интернету.

---

## Быстрый старт (локальная разработка)

```bash
# 1. Клонирование репозитория
git clone https://github.com/your-org/cat-clone.git
cd cat-clone

# 2. Настройка переменных окружения
cp .env.example .env
# Отредактируйте .env — минимум для dev:
#   POSTGRES_PASSWORD=devpassword
#   MINIO_ACCESS_KEY=minioadmin
#   MINIO_SECRET_KEY=minioadmin123
#   JWT_SECRET=$(openssl rand -hex 32)
#   CLICKHOUSE_PASSWORD=chpassword

# 3. Запуск всех сервисов
docker compose up -d

# 4. Применение миграций БД
docker compose run --rm api alembic upgrade head

# 5. Инициализация ClickHouse схемы
docker compose run --rm api python -m app.core.clickhouse_init

# 6. Проверка работоспособности
curl http://localhost:8000/health
# Ответ: {"status": "ok", "checks": {...}}

# 7. Открыть дашборд
open http://localhost:3000
```

---

## Полное развертывание (Production)

### Шаг 1. Подготовка сервера

```bash
# Подключитесь к VPS (AdminVPS/HOSTKEY или аналог)
ssh user@your-vps-ip

# Установите Docker (Ubuntu 22.04)
curl -fsSL https://get.docker.com | bash
usermod -aG docker $USER

# Создайте директорию приложения
mkdir -p /opt/cat-clone && cd /opt/cat-clone
```

### Шаг 2. Клонирование и конфигурация

```bash
git clone git@github.com:your-org/cat-clone.git .
cp .env.example .env

# Заполните все переменные в .env:
# - JWT_SECRET: openssl rand -hex 32
# - POSTGRES_PASSWORD: strong password
# - MINIO_ACCESS_KEY / MINIO_SECRET_KEY
# - SMTP_HOST / SMTP_PASSWORD (для email-алертов)
# - CLICKHOUSE_PASSWORD
nano .env
```

### Шаг 3. SSL-сертификаты

```bash
# Получите сертификат Let's Encrypt
apt install certbot
certbot certonly --standalone -d your-domain.ru

# Скопируйте в директорию nginx
cp /etc/letsencrypt/live/your-domain.ru/fullchain.pem infrastructure/nginx/ssl/
cp /etc/letsencrypt/live/your-domain.ru/privkey.pem infrastructure/nginx/ssl/
```

### Шаг 4. Сборка и запуск

```bash
# Сборка образов
docker compose -f docker-compose.yml -f docker-compose.prod.yml build

# Запуск инфраструктурных сервисов
docker compose up -d postgres redis minio clickhouse
sleep 30

# Применение миграций
docker compose run --rm api alembic upgrade head
docker compose run --rm api python -m app.core.clickhouse_init

# Запуск приложения
docker compose up -d api collector processor beat
docker compose up -d frontend nginx

# Проверка
docker compose ps
curl -s https://your-domain.ru/api/v1/health | jq
```

### Порядок запуска сервисов

```
postgres, redis, minio, clickhouse  → api, processor, beat  → collector  → frontend, nginx
```

---

## Конфигурация переменных окружения

| Переменная | Обязательна | Описание |
|-----------|-------------|----------|
| `JWT_SECRET` | Да | Секрет для подписи JWT. `openssl rand -hex 32` |
| `POSTGRES_URL` | Да | Строка подключения PostgreSQL |
| `POSTGRES_PASSWORD` | Да | Пароль пользователя БД |
| `REDIS_URL` | Да | `redis://redis:6379/0` |
| `CLICKHOUSE_URL` | Да | `http://clickhouse:8123` |
| `CLICKHOUSE_PASSWORD` | Да | Пароль ClickHouse |
| `MINIO_ENDPOINT` | Да | `minio:9000` |
| `MINIO_ACCESS_KEY` | Да | Ключ доступа MinIO |
| `MINIO_SECRET_KEY` | Да | Секретный ключ MinIO |
| `SMTP_HOST` | Да | SMTP-сервер для алертов |
| `SMTP_PASSWORD` | Да | Пароль SMTP |
| `ENV` | Нет | `development` / `production` |
| `DEBUG` | Нет | `false` (по умолчанию) |

---

## Обновление до новой версии

```bash
cd /opt/cat-clone

# Получить последние изменения
git pull origin main

# Пересобрать образы
docker compose -f docker-compose.yml -f docker-compose.prod.yml build

# Накатить миграции (если есть)
docker compose run --rm api alembic upgrade head

# Перезапустить сервисы (без downtime для stateless сервисов)
docker compose up -d --no-deps api collector processor beat frontend
```

---

## Процедура отката

```bash
# 1. Остановить приложение
docker compose stop api collector processor beat frontend

# 2. Откатить миграцию БД (если была)
docker compose run --rm api alembic downgrade -1

# 3. Переключиться на предыдущий тег
git checkout <previous-tag>
docker compose -f docker-compose.yml -f docker-compose.prod.yml build

# 4. Перезапустить
docker compose up -d
```

---

## Проверка после развертывания

```bash
# Статус всех контейнеров
docker compose ps

# Проверка API
curl -s http://localhost/api/v1/health | jq

# Логи API
docker compose logs --tail=50 api

# Логи сборщика
docker compose logs --tail=50 collector

# Проверка очереди Celery
docker compose exec beat celery -A tasks inspect active
```
