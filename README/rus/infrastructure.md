# Требования к инфраструктуре CAT

## Минимальные требования (MVP)

### Аппаратное обеспечение

| Сервис | CPU | RAM | Диск |
|--------|-----|-----|------|
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
| **Итого (MVP)** | **8 vCPU** | **12 GB** | **360 GB SSD** |

> **Рекомендуемый VPS для MVP:** 8 vCPU / 16 GB RAM / 500 GB SSD NVMe
> (AdminVPS/HOSTKEY KVM VDS, ~5 000–7 000 руб./мес.)

---

## Рекомендуемые требования (Production v1.0)

### Конфигурация с масштабированием

| Компонент | Конфигурация | Обоснование |
|-----------|-------------|-------------|
| api | 1 vCPU / 1 GB RAM | FastAPI async, низкие требования |
| collector | 2× (2 vCPU / 2 GB) | Параллельный scraping с Playwright |
| processor | 1× (2 vCPU / 4 GB) | ML-модели CLIP + ruBERT |
| beat | 1× (0.2 vCPU / 256 MB) | **Строго 1 реплика** — иначе дублирование задач |
| postgres | 2 vCPU / 4 GB / 200 GB SSD | ACID-база, JSONB |
| clickhouse | 4 vCPU / 8 GB / 500 GB SSD | Временные ряды, быстрые агрегации |
| redis | 1 vCPU / 1 GB | Celery broker + кеш |
| minio | 2 vCPU / 2 GB / 1 TB SSD | Хранилище изображений |
| **Итого** | **~16 vCPU** | **~24 GB RAM** | **~2 TB SSD** |

---

## Сетевые требования

### Открытые порты (публичные)

| Порт | Протокол | Сервис | Примечание |
|------|----------|--------|------------|
| 80 | TCP | nginx | HTTP → redirect HTTPS |
| 443 | TCP | nginx | HTTPS (Let's Encrypt) |

### Открытые порты (внутренние / dev)

| Порт | Сервис | Для чего |
|------|--------|---------|
| 8000 | api | FastAPI HTTP |
| 3000 | frontend | React dev server |
| 5432 | postgres | БД (только внутри Docker сети) |
| 8123 | clickhouse | HTTP-интерфейс |
| 9000 | clickhouse / minio | Clickhouse native / MinIO S3 API |
| 9001 | minio | MinIO Console |
| 6379 | redis | Redis |
| 5555 | flower | Celery monitor |
| 1025 / 8025 | mailhog | Email testing (dev only) |

> В production — все порты кроме 80/443 **закрыты** на firewall. Доступ к БД только через Docker internal network.

### Требования к исходящим соединениям

| Назначение | Протокол | Примечание |
|-----------|----------|------------|
| 110+ маркетплейсов | HTTPS | Scraping (через proxy) |
| HuggingFace Hub | HTTPS | Загрузка ML-моделей (один раз) |
| SMTP-сервер | SMTP/587 | Отправка email-алертов |
| Docker Hub / registry | HTTPS | Сборка образов |
| Let's Encrypt | HTTPS | SSL-сертификаты |

### Прокси-сервера для скрапинга

Для работы скрапинга на 110+ платформах рекомендуется пул ротируемых proxy. Укажите в `.env`:

```bash
PROXY_LIST_URL=http://proxy-provider.example.ru/api/list
# или статический список:
PROXY_USER=proxyuser
PROXY_PASS=proxypass
```

---

## Docker-сервисы

| Сервис | Образ | Роль |
|--------|-------|------|
| `nginx` | `nginx:1.25-alpine` | Reverse proxy, SSL, static files |
| `api` | Кастомный (Python 3.11) | FastAPI REST API |
| `collector` | Кастомный (Python 3.11 + Playwright) | Celery workers, scrapers |
| `processor` | Кастомный (Python 3.11 + HuggingFace) | ML pipeline |
| `beat` | Кастомный (тот же, что collector) | Celery Beat scheduler |
| `flower` | Кастомный | Celery monitoring UI |
| `frontend` | Кастомный (Node 18 → nginx) | React SPA |
| `postgres` | `postgres:16-alpine` | Основная БД |
| `clickhouse` | `clickhouse/clickhouse-server:23.8-alpine` | Аналитическая БД |
| `redis` | `redis:7-alpine` | Кеш + брокер задач |
| `minio` | `minio/minio:latest` | S3-совместимое хранилище |
| `mailhog` | `mailhog/mailhog:latest` | Email тестирование (dev) |

---

## Зависимости

### Обязательные внешние сервисы

| Сервис | Тип | Назначение |
|--------|-----|------------|
| SMTP-сервер | Email | Отправка алертов (Mailgun, SendGrid, Postfix) |
| Proxy-пул | HTTP/SOCKS5 | Ротация IP для scraping |

### Опциональные интеграции

| Сервис | Тип | Назначение |
|--------|-----|------------|
| Prometheus + Grafana | Monitoring | Метрики и алертинг |
| Telegram Bot | Notifications | Оперативные алерты для DevOps |
| S3-бакет (внешний) | Backup | Резервное копирование БД |

### Лицензионные зависимости

Все ключевые компоненты — Open Source:

| Компонент | Лицензия |
|-----------|----------|
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

## Volumes (постоянные данные)

| Volume | Сервис | Содержимое |
|--------|--------|------------|
| `postgres_data` | postgres | Таблицы PostgreSQL |
| `clickhouse_data` | clickhouse | Аналитические таблицы |
| `redis_data` | redis | Celery-задачи (persistency) |
| `minio_data` | minio | Изображения SKU (эталоны + собранные) |
| `huggingface_cache` | processor | Веса ML-моделей CLIP + ruBERT |

> **Критично:** `minio_data` и `postgres_data` — обязательно подключить к постоянным дискам на VPS. Потеря этих томов = потеря всех данных.
