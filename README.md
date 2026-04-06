# CAT — Commerce Analytics Tool

SaaS-платформа мониторинга онлайн-полки для FMCG-производителей. Ежедневно собирает данные о карточках товаров, ценах, остатках и отзывах на 110+ цифровых платформах.

## What it does

- **Content monitoring** — ML-scoring of product cards (CLIP + multilingual-e5)
- **Price tracking** — daily price snapshots across 110+ platforms
- **Stock distribution** — plan vs. actual distribution monitoring
- **Review analytics** — sentiment analysis via ruBERT
- **Excel reports** — client-format exports
- **Alerts** — anomaly detection with email/webhook notifications in 2-4 hours

## Quick Start

```bash
cp .env.example .env
# Edit .env — fill in all required secrets

docker compose up --build -d
docker compose exec api alembic upgrade head
```

Open http://localhost:3000

See [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) for full setup, testing, and deployment instructions.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Python 3.11 |
| Task Queue | Celery 5.x + Redis |
| Scraping | Playwright + Scrapy |
| Primary DB | PostgreSQL 16 |
| Analytics DB | ClickHouse |
| ML Images | CLIP (HuggingFace) |
| ML Text | multilingual-e5 + ruBERT |
| Frontend | React 18 + TypeScript + Ant Design 5 |
| Storage | MinIO (S3-compatible) |

## Architecture

Distributed Monolith on Docker Compose. Four services:
- `api` — FastAPI backend (auth, content, stock, reviews, prices, reports, alerts)
- `collector` — Celery workers + Playwright/Scrapy scrapers
- `processor` — ML pipeline (CLIP image scoring + ruBERT sentiment)
- `frontend` — React + TypeScript dashboard

See [docs/Architecture.md](docs/Architecture.md) for full system design.

## Documentation

| Doc | Purpose |
|-----|---------|
| [docs/PRD.md](docs/PRD.md) | Product requirements |
| [docs/Architecture.md](docs/Architecture.md) | System design, DB schema, ML pipeline |
| [docs/Specification.md](docs/Specification.md) | API contracts |
| [docs/test-scenarios.md](docs/test-scenarios.md) | BDD test scenarios |
| [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) | Developer handbook |
| [CLAUDE.md](CLAUDE.md) | Claude Code toolkit reference |

## Feature Roadmap

SPARC column: P1=docs · P2=validation · P3=impl · P4=review. ✅ all phases · ⚠️ debt · 🔲 not started

| # | Feature | Priority | Sprint | SP | Status | SPARC |
|---|---------|----------|--------|----|--------|-------|
| 1 | Auth (JWT + RBAC) | P0 | 1 | 5 | ✅ Done | ✅ P1·P2·P3·P4 |
| 2 | SKU CRUD + bulk upload | P0 | 1 | 8 | ✅ Done | ✅ P1·P2·P3·P4 |
| 3 | Reference upload (S3) | P0 | 1 | 5 | ✅ Done | ✅ P1·P2·P3·P4 |
| 4 | WB scraper | P0 | 2 | 13 | ✅ Done | ✅ P1·P2·P3·P4 |
| 5 | Ozon scraper | P0 | 2 | 13 | ✅ Done | ✅ P1·P2·P3·P4 |
| 6 | Самокат scraper | P0 | 2 | 8 | ✅ Done | ✅ P1·P2·P3·P4 |
| 7 | Лента scraper | P0 | 2 | 8 | ✅ Done | ✅ P1·P2·P3·P4 |
| 8 | Content scoring (image) | P0 | 3 | 13 | ✅ Done | ✅ P1·P2·P3·P4 |
| 9 | Content scoring (text) | P0 | 3 | 8 | ✅ Done | ✅ P1·P2·P3·P4 |
| 10 | Stock plan upload | P0 | 3 | 5 | ✅ Done | ✅ P1·P2·P3·P4 |
| 11 | Distribution dashboard | P0 | 4 | 13 | ✅ Done | ✅ P1·P2·P3·P4 |
| 12 | Excel Export (Content) | P0 | 4 | 8 | ✅ Done | ✅ P1·P2·P3·P4 |
| 13 | Excel Export (Stock) | P0 | 4 | 8 | ✅ Done | ✅ P1·P2·P3·P4 |
| 14 | Email alerts | P0 | 5 | 8 | ✅ Done | ✅ P1·P2·P3·P4 |
| 15 | Price monitoring | P1 | 6 | 13 | ✅ Done | ✅ P1·P2·P3·P4 |
| 16 | Reviews NLP | P1 | 7 | 13 | ✅ Done | ✅ P1·P2·P3·P4 |
| 17 | Excel Export (Reviews) | P1 | 7 | 5 | ✅ Done | ✅ P1·P2·P3·P4 |
| 18 | Web Dashboard | P1 | 8 | 21 | ✅ Done | ✅ P1·P2·P3·P4 |
| 19 | API public endpoints | P1 | 9 | 13 | ✅ Done | ✅ P1·P2·P3·P4 |
| 20 | Multi-client support | P1 | 10 | 13 | ✅ Done | ✅ P1·P2·P3·P4 |
| 21 | Alert Config UI | P1 | 11 | 8 | ✅ Done | ✅ P1·P2·P3·P4 |
| 22 | Platform Management | P1 | 11 | 5 | 🔲 Planned | 🔲 |
| 23 | ML Config (scoring weights) | P1 | 12 | 8 | 🔲 Planned | 🔲 |
| 24 | Scraper Config (rate/proxy) | P1 | 12 | 8 | 🔲 Planned | 🔲 |
| 25 | Content Excel Report v2 | P1 | 13 | 5 | 🔲 Planned | 🔲 |
| 26 | Reviews Excel Report v2 | P1 | 13 | 8 | 🔲 Planned | 🔲 |
| 27 | Store-level stock tracking | P1 | 14 | 13 | 🔲 Planned | 🔲 |
| 28 | Stock/Distribution Excel v2 | P1 | 14 | 13 | 🔲 Planned | 🔲 |
| 29 | Price change alert type | P1 | 15 | 8 | 🔲 Planned | 🔲 |
| 30 | Competitor promo alert | P2 | 15 | 8 | 🔲 Planned | 🔲 |
| 31 | Webhook notifications | P2 | 15 | 5 | 🔲 Planned | 🔲 |
| 32 | Competitor analytics dashboard | P1 | 16 | 13 | 🔲 Planned | 🔲 |
| 33 | NLP topic clustering | P2 | 16 | 13 | 🔲 Planned | 🔲 |
| 34 | Dynamic scraper scheduling | P2 | 17 | 8 | 🔲 Planned | 🔲 |
| 35 | Platform onboarding wizard | P2 | 17 | 13 | 🔲 Planned | 🔲 |

**Sprint 1:** Полностью завершён ✅ (Auth · SKU CRUD · Reference Upload S3)
**Sprint 2:** Полностью завершён ✅ (WB · Ozon · Самокат · Лента scrapers)
**Sprint 3:** Полностью завершён ✅ (Content scoring image · Content scoring text · Stock plan upload)
**Sprint 4:** Полностью завершён ✅ (Distribution dashboard · Excel Export Content · Excel Export Stock)
**Sprint 5:** Полностью завершён ✅ (Email alerts)
**Sprint 6:** Полностью завершён ✅ (Price monitoring)
**Sprint 7:** Полностью завершён ✅ (Reviews NLP · Excel Export Reviews)
**Sprint 8:** Полностью завершён ✅ (Web Dashboard · Prices/Reviews frontend pages)
**Sprint 9:** Полностью завершён ✅ (API public endpoints)
**Sprint 10:** Полностью завершён ✅ (Multi-client support)
**Sprint 11:** ✅ Alert Config UI · Platform Management
**Sprint 12:** ML Config · Scraper Config
**Sprint 13:** Content Excel v2 · Reviews Excel v2
**Sprint 14:** Store-level stock · Stock/Distribution Excel v2
**Sprint 15:** Price change alert · Competitor promo alert · Webhook notifications
**Sprint 16:** Competitor analytics dashboard · NLP topic clustering
**Sprint 17:** Dynamic scraper scheduling · Platform onboarding wizard

### SPARC Lifecycle Debt

✅ **MVP lifecycle debt resolved.** Features 1–20 fully planned, validated, implemented, and reviewed.

**🎉 MVP COMPLETE** — все 20 фич реализованы.

**🚀 Post-MVP Sprint 11–17** — 15 фич в очереди (features 21–35).

### Feature Descriptions (21–35)

| # | Slug | Описание |
|---|------|----------|
| 21 | `alert-config-ui` | CRUD интерфейс для управления конфигурациями алертов (тип, порог, SKU, платформа, email-получатели). API уже реализован — только фронтенд. |
| 22 | `platform-management` | Добавление/редактирование/отключение платформ через UI. CRUD API для Platform. Подключение `schedule_cron` к Celery Beat. |
| 23 | `ml-config` | Таблица `ml_config` per org: веса image/desc/comp (0.40/0.35/0.25 сейчас хардкод), мин. порог CLIP similarity. UI: слайдеры с проверкой суммы = 1. |
| 24 | `scraper-config` | Таблица `scraper_config` per platform per org: rate_limit, proxy_url, headers_override, is_active. UI: таблица настроек + кнопка "Запустить сейчас". |
| 25 | `excel-content-v2` | Content Report по образцу: лист Total (агрегат по платформам) + Score Card (собранное vs эталон рядом, presigned ссылки на изображения). |
| 26 | `excel-reviews-v2` | Reviews Report: Сводная (отзывы начало/конец, рейтинг, 1★–5★ разбивка) + Тотал по брендам + Тотал по брендам×категориям + Тексты отзывов. |
| 27 | `stock-store-level` | Добавить `city`, `store_address`, `store_id` в StockSnapshot. Обновить scrapers для сбора данных на уровне магазина. Миграция Alembic. |
| 28 | `excel-stock-v2` | Stock/Distribution Report (7 листов): План-Факт по сети · Все SKU по неделям · По городам · Доля в ассортименте · По адресам · ТОП города кросс-таблица · SKU на ТТ. |
| 29 | `alert-price-change` | Реализация типа алерта `price_change`: триггер при изменении цены более чем на N% за период. Threshold = процент изменения. |
| 30 | `alert-competitor-promo` | Тип алерта `competitor_promo`: детектирует промо-акции конкурентов (резкое снижение цены конкурента > threshold%). Требует brand_type = competitor. |
| 31 | `alerts-webhook` | Webhook-доставка алертов (POST на URL) как альтернатива email. Новое поле `webhook_url` в AlertConfig. Retry 3× с экспоненциальным backoff. |
| 32 | `competitor-analytics` | Dashboard сравнения собственного бренда vs конкурентов: контент-скоры, цены, рейтинги side-by-side. Фильтр по brand_type = client/competitor. |
| 33 | `nlp-topic-clustering` | Кластеризация текстов отзывов для извлечения топ-тем (позитив/негатив/нейтраль). KeyBERT или LDA поверх ruBERT embeddings. Нужно для Excel Reviews v2. |
| 34 | `scraper-scheduler` | Динамическое управление расписанием Celery Beat из БД. Читать `Platform.schedule_cron` вместо хардкода. UI: редактировать cron выражение с валидацией. |
| 35 | `platform-onboarding` | Wizard добавления новой платформы: название, тип, URL-шаблон, тест-запрос, маппинг полей ответа. Генерация конфига scraper без правки кода. |

## License

Proprietary — all rights reserved.
