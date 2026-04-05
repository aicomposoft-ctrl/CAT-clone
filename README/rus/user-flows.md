# Пользовательские сценарии CAT

## User Flow: Регистрация и первый вход

```mermaid
sequenceDiagram
    actor Admin as Администратор
    actor User as Trade Marketing Manager
    participant API as CAT API
    participant Email as Email

    Admin->>API: POST /auth/users {email, role: manager}
    API->>Email: Отправить приглашение с временным паролем
    Email-->>User: Письмо с ссылкой и паролем
    User->>API: POST /auth/login {email, temp_password}
    API-->>User: JWT access_token + refresh_token
    User->>API: POST /auth/change-password
    API-->>User: 200 OK — пароль изменён
    User->>API: GET /content/scores (первый запрос данных)
```

**Шаги:**
1. Администратор создаёт аккаунт через Settings → Users
2. Пользователь получает email с временным паролем
3. Первый вход → смена пароля → доступ к дашборду

---

## User Flow: Добавление SKU и загрузка эталона

```mermaid
sequenceDiagram
    actor BM as Brand Manager
    participant UI as CAT Dashboard
    participant API as CAT API
    participant S3 as MinIO S3

    BM->>UI: Settings → SKU Management → Add SKU
    UI->>API: POST /skus {brand, article, name, barcode, platforms}
    API-->>UI: SKU created {id, status: active}
    BM->>UI: Загрузить эталонное изображение (drag & drop)
    UI->>API: POST /skus/{id}/reference {image_file}
    API->>S3: Сохранить изображение (private bucket)
    S3-->>API: S3 URL
    API->>API: Вычислить CLIP embedding, кешировать в Redis
    API-->>UI: Reference uploaded ✅
    BM->>UI: Вставить эталонное описание и состав
    UI->>API: PUT /skus/{id} {reference_description, reference_composition}
    API-->>UI: Updated ✅
    UI-->>BM: "Следующий пересчёт: сегодня ночью в 02:00"
```

**Что происходит «под капотом»:**
- CLIP-embedding эталонного изображения кешируется немедленно
- multilingual-e5 embedding текста кешируется немедленно
- Content score будет пересчитан в ближайший ночной цикл (02:00)

---

## User Flow: Ежедневный мониторинг контента

```mermaid
sequenceDiagram
    actor TM as Trade Marketing Manager
    participant UI as CAT Dashboard
    participant API as CAT API
    participant Email as Email

    Note over API: 02:00 — автоматический сбор данных
    API->>API: Celery Beat → collect_content_all_skus()
    API->>API: Processor → рассчитать content scores
    API->>API: Alerter → проверить пороги алертов
    API->>Email: Отправить алерты (если score < threshold)
    Email-->>TM: "⚠️ Content score упал: SKU 3927 на WB — 42%"

    TM->>UI: Открыть раздел Content
    UI->>API: GET /content/scores?sort=content_total&order=asc
    API-->>UI: Список SKU, отсортированный по score
    TM->>UI: Кликнуть на SKU с низким score
    UI->>API: GET /content/scores/{sku_id}/history
    API-->>UI: Детальное сравнение + история 30 дней
    TM->>TM: Принять решение о корректировке карточки
```

---

## User Flow: Экспорт Content Report для клиента

```mermaid
sequenceDiagram
    actor AM as Agency Manager
    participant UI as CAT Dashboard
    participant API as CAT API
    participant Excel as Excel File

    AM->>UI: Reports → Content Report
    UI-->>AM: Форма: выбрать период, бренды
    AM->>UI: Выбрать "10–17 марта 2025", бренд "ИндиЛайт"
    UI->>API: GET /reports/content?date_from=2025-03-10&date_to=2025-03-17
    API->>API: openpyxl → сформировать Excel по шаблону клиента
    API-->>UI: Streaming response (.xlsx)
    UI-->>AM: Content_Report_2025-03-17.xlsx (download)
    AM->>AM: Отправить отчёт клиенту
```

---

## User Flow: Проверка дистрибуции план/факт

```mermaid
sequenceDiagram
    actor TM as Trade Marketing Manager
    participant UI as CAT Dashboard
    participant API as CAT API

    TM->>UI: Stock → Upload Plan
    UI->>API: POST /stock/plan (CSV/Excel файл)
    API->>API: Распарсить, сохранить план по SKU × сети
    API-->>UI: "План загружен для 45 SKU по 3 сетям"

    Note over API: Ночной сбор данных
    API->>API: collect_stock_all_skus() → обновить факт ТТ

    TM->>UI: Stock → Distribution → По сети
    UI->>API: GET /stock/distribution?network=Ритейлер
    API-->>UI: Таблица план/факт с % дистрибуции
    TM->>UI: Клик по SKU с Дистрибуция < 80%
    UI->>API: GET /stock/by-city?sku_id=...
    API-->>UI: Разбивка по городам, 4 недели
    TM->>TM: Эскалировать в логистику по конкретным городам
```

---

## Admin Flow: Настройка системы (первоначальная)

```mermaid
sequenceDiagram
    actor Admin as System Admin
    participant Server as VPS Server
    participant Docker as Docker Compose
    participant API as CAT API

    Admin->>Server: ssh user@vps && git clone
    Admin->>Server: cp .env.example .env && nano .env
    Admin->>Docker: docker compose up -d postgres redis minio clickhouse
    Admin->>Docker: docker compose run --rm api alembic upgrade head
    Admin->>Docker: docker compose up -d api collector processor beat frontend nginx
    Admin->>API: curl /api/v1/health → {status: ok}

    Admin->>API: POST /auth/users {email: admin@org.ru, role: admin}
    Admin->>API: POST /platforms (добавить WB, Ozon, Samokat, Lenta)
    Admin->>API: POST /auth/users (создать аккаунты для менеджеров)
    Note over Admin: Система готова к работе
```

---

## Admin Flow: Управление пользователями организации

```mermaid
sequenceDiagram
    actor Admin as Admin
    participant UI as CAT Dashboard
    participant API as CAT API

    Admin->>UI: Settings → Users → Add User
    UI->>API: POST /auth/users {email, role: manager, org_id}
    API-->>UI: User created, invite sent
    
    Note over Admin: Пользователь больше не работает в компании
    Admin->>UI: Settings → Users → Deactivate User
    UI->>API: PUT /auth/users/{id} {is_active: false}
    API->>API: Invalidate all refresh tokens for user
    API-->>UI: User deactivated ✅
```

---

## Admin Flow: Мониторинг состояния системы

```mermaid
sequenceDiagram
    actor Admin as Admin / DevOps
    participant Flower as Flower UI
    participant Grafana as Grafana
    participant API as CAT API
    participant Telegram as Telegram Bot

    Note over API: 02:00 — плановый сбор данных
    API->>Flower: Задачи запущены (collect × 1247 SKU)
    
    Note over API: 04:15 — обнаружена проблема: WB scraper 30% ошибок
    API->>Telegram: ⚠️ "WB scraper success rate: 70% (порог 80%)"
    Admin->>Flower: Проверить failed tasks для WB
    Admin->>API: Перезапустить зависшие задачи
    
    Admin->>Grafana: Открыть дашборд метрик
    Grafana-->>Admin: API latency, DB connections, Redis memory
    
    Admin->>API: GET /api/v1/health → all checks: ok
    Admin->>Admin: Инцидент закрыт, занести в журнал
```
