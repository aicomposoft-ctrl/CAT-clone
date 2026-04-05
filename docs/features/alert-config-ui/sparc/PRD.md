# Product Requirements Document — Alert Config UI

**Feature:** alert-config-ui  
**Version:** 1.0  
**Date:** 2026-04-05  
**Status:** Approved

---

## 1. Executive Summary

### 1.1 Purpose

Реализовать в веб-интерфейсе CAT полный CRUD для управления конфигурациями алертов.
Backend API (POST/GET/PATCH/DELETE `/api/v1/alerts/configs`) уже реализован и протестирован.
Задача — исключительно фронтенд: добавить в страницу Alerts вкладки и UI для создания,
редактирования и удаления конфигураций.

### 1.2 Scope

**In Scope:**
- Вкладка "Конфигурации" на странице Alerts рядом с существующей вкладкой "События"
- Таблица конфигураций с пагинацией (список)
- Модальное окно создания конфигурации
- Модальное окно редактирования (threshold, emails, is_active)
- Удаление конфигурации с подтверждением
- Кнопка "Запустить проверку" (POST `/alerts/check`) для admin

**Out of Scope:**
- Новые типы алертов (price_change, competitor_promo) — отдельная фича #29, #30
- Изменения в backend API
- Уведомления по webhook — отдельная фича #31
- Настройка ML-порогов — отдельная фича #23

### 1.3 Definitions

| Term | Definition |
|------|------------|
| AlertConfig | Запись в БД, описывающая условие срабатывания алерта |
| AlertEvent | Событие, сгенерированное при срабатывании AlertConfig |
| threshold | Значение 0–100; ниже этого значения content_total → алерт |
| content_drop | Тип алерта: падение ML-оценки контента ниже порога |
| oos | Тип алерта: отсутствие товара в наличии (out of stock) |

---

## 2. Problem Statement

**Проблема:** Администраторы и менеджеры не могут управлять конфигурациями алертов через UI.
Сейчас единственный способ — прямые API-вызовы через curl/Postman, что неприемлемо для
нетехнических пользователей.

**Текущее состояние страницы Alerts:**
- Отображает только события (AlertEvent) — read-only
- Нет кнопки "Создать конфигурацию"
- Нет списка существующих конфигураций
- API client в `api/alerts.ts` содержит только `list()` и `acknowledge()` — нет configsCreate/Update/Delete

**Impact:** Пользователи не могут самостоятельно настраивать мониторинг — вся конфигурация
зависит от разработчика. Это блокирует онбординг новых клиентов.

---

## 3. Target Users

### Admin (первичная персона)

| Attribute | Description |
|-----------|-------------|
| **Role** | admin |
| **Goals** | Создавать, редактировать, удалять конфигурации алертов; тестировать |
| **Pain Points** | Сейчас нет UI — только API |
| **Technical Proficiency** | Medium |
| **Usage Frequency** | Редко (настройка при онбординге клиента) |

### Manager (вторичная персона)

| Attribute | Description |
|-----------|-------------|
| **Role** | manager |
| **Goals** | Корректировать пороги существующих конфигураций |
| **Pain Points** | Не может изменить порог без помощи разработчика |
| **Technical Proficiency** | Low–Medium |

### Viewer (anti-persona)
Просматривает события, не управляет конфигурациями. UI конфигураций скрыт или read-only.

---

## 4. Requirements

### 4.1 Functional Requirements

#### US-001: Просмотр списка конфигураций

| Field | Value |
|-------|-------|
| As a | admin/manager |
| I want | видеть все конфигурации алертов моей организации |
| So that | понимать, что мониторится |
| Priority | Must |

**Acceptance Criteria:**
- Таблица показывает: тип, SKU (или "Все"), платформа (или "Все"), порог, email-получатели, статус is_active
- Пагинация 50 записей/страница
- Пустой список: "Нет конфигураций — нажмите +, чтобы создать первую"

#### US-002: Создание конфигурации

| Field | Value |
|-------|-------|
| As a | admin/manager |
| I want | создать новую конфигурацию алерта |
| So that | система начала мониторить выбранное условие |
| Priority | Must |

**Acceptance Criteria:**
- Кнопка "+ Добавить" видна только роли admin/manager
- Форма: alert_type (dropdown), SKU (search select, опциональный), Platform (select, опциональный), threshold (slider 0–100, обязателен для content_drop, скрыт для oos), email_recipients (tags input, min 1)
- При выборе oos — поле threshold скрывается и убирается из валидации
- Валидация на клиенте перед отправкой
- После успешного создания: таблица обновляется, модал закрывается, toast "Конфигурация создана"
- При ошибке API: показать сообщение об ошибке inline

#### US-003: Редактирование конфигурации

| Field | Value |
|-------|-------|
| As a | admin/manager |
| I want | изменить порог, email-получателей или статус активности |
| So that | скорректировать параметры мониторинга без пересоздания |
| Priority | Must |

**Acceptance Criteria:**
- Кнопка "Изменить" в строке таблицы (скрыта для viewer)
- Редактируемые поля: threshold, email_recipients, is_active (toggle)
- Нередактируемые поля: alert_type, sku_id, platform_id (отображаются как read-only)
- После успешного PATCH: toast "Изменения сохранены"

#### US-004: Удаление конфигурации

| Field | Value |
|-------|-------|
| As a | admin/manager |
| I want | удалить конфигурацию алерта |
| So that | убрать устаревший или ошибочный мониторинг |
| Priority | Must |

**Acceptance Criteria:**
- Кнопка "Удалить" в строке (скрыта для viewer)
- Confirmation modal: "Вы уверены? Все связанные события останутся в истории."
- После DELETE 204: строка исчезает из таблицы, toast "Конфигурация удалена"

#### US-005: Ручной запуск проверки

| Field | Value |
|-------|-------|
| As a | admin |
| I want | запустить проверку алертов немедленно |
| So that | убедиться, что конфигурация работает |
| Priority | Should |

**Acceptance Criteria:**
- Кнопка "Запустить проверку" видна только роли admin
- Кнопка неактивна 60 секунд после нажатия (rate limit 5 req/min)
- После успешного ответа: показать результат "Создано N событий, отправлено M писем"
- При ошибке 429: "Слишком много запросов, подождите минуту"

### 4.2 Non-Functional Requirements

| Metric | Requirement |
|--------|-------------|
| Отклик таблицы | < 500ms при 50 записях |
| Открытие модала | < 100ms (данные для select грузятся заранее) |
| Inline validation | Без задержки (только клиентская) |

---

## 5. User Journey

### Journey: Создание первого алерта

```
1. Admin переходит на страницу Alerts
   → Видит вкладки "События" (активна) и "Конфигурации"

2. Admin нажимает вкладку "Конфигурации"
   → Таблица пустая. Кнопка "+ Добавить" видна.

3. Admin нажимает "+ Добавить"
   → Открывается Modal "Новая конфигурация"

4. Admin выбирает alert_type = "content_drop"
   → Появляется поле Threshold (slider)

5. Admin выставляет threshold = 70, вводит email test@brand.ru
   → Форма валидна

6. Admin нажимает "Создать"
   → POST /api/v1/alerts/configs → 201
   → Modal закрывается
   → Toast "Конфигурация создана"
   → В таблице появилась новая строка
```

---

## 6. UI/UX Requirements

### 6.1 Структура страницы

```
Alerts Page
├── Tabs
│   ├── [События]      ← существующая вкладка (без изменений)
│   └── [Конфигурации] ← новая вкладка
│
└── Вкладка "Конфигурации":
    ├── Toolbar
    │   ├── Button "+ Добавить"  (admin/manager only)
    │   └── Button "Запустить проверку"  (admin only)
    └── Table
        ├── Тип | Охват | Порог | Получатели | Активен | Действия
        └── Pagination (50/page)
```

### 6.2 Форма создания/редактирования

```
Modal "Новая конфигурация" / "Редактировать конфигурацию"
├── alert_type: Select ["Падение контента", "Нет в наличии"]
│              (disabled при редактировании)
├── sku_id: Select с поиском (placeholder "Все SKU")
│           (disabled при редактировании)
├── platform_id: Select (placeholder "Все платформы")
│               (disabled при редактировании)
├── threshold: Slider 0–100 + Input [visible only for content_drop]
├── email_recipients: Tags Input (EmailStr validation per tag)
├── is_active: Switch "Активен"
└── Buttons: [Отмена] [Создать / Сохранить]
```

### 6.3 Таблица конфигураций (колонки)

| Колонка | Содержимое |
|---------|-----------|
| Тип | Tag с иконкой (orange=content_drop, red=oos) |
| Охват | "SKU: {name} / Все" + "Площадка: {name} / Все" |
| Порог | "≥ 70" для content_drop, "–" для oos |
| Получатели | первые 2 email + "+N ещё" |
| Активен | Switch (кликабельный для admin/manager) |
| Действия | [Изм.] [Удал.] (скрыты для viewer) |

---

## 7. Release Strategy

### MVP (Phase 1 — текущая фича)
- ✅ CRUD для content_drop и oos
- ✅ Ручной запуск проверки (admin)
- ✅ RBAC: admin/manager — CRUD; viewer — read-only

### v1.1 (фича #29)
- price_change тип алерта

### v1.2 (фича #30, #31)
- competitor_promo тип
- Webhook доставка

---

## 8. Dependencies

| Dependency | Статус |
|------------|--------|
| GET /api/v1/alerts/configs | ✅ Реализован |
| POST /api/v1/alerts/configs | ✅ Реализован |
| PATCH /api/v1/alerts/configs/{id} | ✅ Реализован |
| DELETE /api/v1/alerts/configs/{id} | ✅ Реализован |
| POST /api/v1/alerts/check | ✅ Реализован |
| GET /api/v1/skus (для select SKU) | ✅ Реализован |
| GET /api/v1/platforms (для select) | ✅ Реализован |

**Нет backend-зависимостей.** Все API готовы.
