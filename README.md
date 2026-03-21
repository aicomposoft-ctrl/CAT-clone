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

## License

Proprietary — all rights reserved.
