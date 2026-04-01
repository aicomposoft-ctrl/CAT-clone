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

| # | Feature | Priority | Sprint | SP | Status |
|---|---------|----------|--------|----|--------|
| 1 | Auth (JWT + RBAC) | P0 | 1 | 5 | ✅ Done |
| 2 | SKU CRUD + bulk upload | P0 | 1 | 8 | ✅ Done |
| 3 | Reference upload (S3) | P0 | 1 | 5 | ✅ Done |
| 4 | WB scraper | P0 | 2 | 13 | ✅ Done |
| 5 | Ozon scraper | P0 | 2 | 13 | ✅ Done |
| 6 | Самокат scraper | P0 | 2 | 8 | ✅ Done |
| 7 | Лента scraper | P0 | 2 | 8 | ✅ Done |
| 8 | Content scoring (image) | P0 | 3 | 13 | ✅ Done |
| 9 | Content scoring (text) | P0 | 3 | 8 | ✅ Done |
| 10 | Stock plan upload | P0 | 3 | 5 | ✅ Done |
| 11 | Distribution dashboard | P0 | 4 | 13 | 🔄 In Progress |
| 12 | Excel Export (Content) | P0 | 4 | 8 | 🔲 |
| 13 | Excel Export (Stock) | P0 | 4 | 8 | 🔲 |
| 14 | Email alerts | P0 | 5 | 8 | 🔲 |
| 15 | Price monitoring | P1 | 6 | 13 | 🔲 |
| 16 | Reviews NLP | P1 | 7 | 13 | 🔲 |
| 17 | Excel Export (Reviews) | P1 | 7 | 5 | 🔲 |
| 18 | Web Dashboard | P1 | 8 | 21 | 🔲 |
| 19 | API public endpoints | P1 | 9 | 13 | 🔲 |
| 20 | Multi-client support | P1 | 10 | 13 | 🔲 |

**Sprint 1:** Полностью завершён ✅ (Auth · SKU CRUD · Reference Upload S3)
**Sprint 2:** Полностью завершён ✅ (WB · Ozon · Самокат · Лента scrapers)
**Sprint 3:** Полностью завершён ✅ (Content scoring image · Content scoring text · Stock plan upload)
**Sprint 4:** Distribution dashboard 🔄 · Excel Export 🔲 · Email alerts 🔲 — In Progress

To implement next: Distribution dashboard Phase 3 (frontend scaffold + implementation)

## License

Proprietary — all rights reserved.
