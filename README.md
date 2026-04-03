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
| 2 | SKU CRUD + bulk upload | P0 | 1 | 8 | ✅ Done | ⚠️ P1·P2·P3 (no P4) |
| 3 | Reference upload (S3) | P0 | 1 | 5 | ✅ Done | ✅ P1·P2·P3·P4 |
| 4 | WB scraper | P0 | 2 | 13 | ✅ Done | ✅ P1·P2·P3·P4 |
| 5 | Ozon scraper | P0 | 2 | 13 | ✅ Done | ⚠️ P1·P2·P3 (no P4) |
| 6 | Самокат scraper | P0 | 2 | 8 | ✅ Done | ✅ P1·P2·P3·P4 |
| 7 | Лента scraper | P0 | 2 | 8 | ✅ Done | ✅ P1·P2·P3·P4 |
| 8 | Content scoring (image) | P0 | 3 | 13 | ✅ Done | ✅ P1·P2·P3·P4 |
| 9 | Content scoring (text) | P0 | 3 | 8 | ✅ Done | ⚠️ P1(4/5)·P2·P3·P4 |
| 10 | Stock plan upload | P0 | 3 | 5 | ✅ Done | ⚠️ P1(2/5)·P3·P4 (no P2) |
| 11 | Distribution dashboard | P0 | 4 | 13 | ✅ Done | ✅ P1·P2·P3·P4 |
| 12 | Excel Export (Content) | P0 | 4 | 8 | ✅ Done | ✅ P1·P2·P3·P4 |
| 13 | Excel Export (Stock) | P0 | 4 | 8 | ✅ Done | ✅ P1·P2·P3·P4 |
| 14 | Email alerts | P0 | 5 | 8 | ⚠️ Done (2 criticals) | ✅ P1·P2·P3·P4 |
| 15 | Price monitoring | P1 | 6 | 13 | 🔲 | 🔲 |
| 16 | Reviews NLP | P1 | 7 | 13 | 🔲 | 🔲 |
| 17 | Excel Export (Reviews) | P1 | 7 | 5 | 🔲 | 🔲 |
| 18 | Web Dashboard | P1 | 8 | 21 | 🔲 | 🔲 |
| 19 | API public endpoints | P1 | 9 | 13 | 🔲 | 🔲 |
| 20 | Multi-client support | P1 | 10 | 13 | 🔲 | 🔲 |

**Sprint 1:** Полностью завершён ✅ (Auth · SKU CRUD · Reference Upload S3)
**Sprint 2:** Полностью завершён ✅ (WB · Ozon · Самокат · Лента scrapers)
**Sprint 3:** Полностью завершён ✅ (Content scoring image · Content scoring text · Stock plan upload)
**Sprint 4:** Полностью завершён ✅ (Distribution dashboard · Excel Export Content · Excel Export Stock)
**Sprint 5:** Email alerts ⚠️ — Implemented, 2 critical issues pending fix

### SPARC Lifecycle Debt

| Feature | Что отсутствует | Приоритет |
|---------|----------------|-----------|
| SKU CRUD (#2) | `docs/features/sku-crud/review-report.md` (Phase 4) | Medium |
| Ozon scraper (#5) | `docs/features/ozon-scraper/review-report.md` (Phase 4) | Medium |
| Content scoring text (#9) | `docs/features/content-scoring-text/sparc/Architecture.md` (Phase 1) | Low |
| Stock plan upload (#10) | `sparc/PRD.md`, `sparc/Specification.md`, `sparc/Refinement.md`, `validation-report.md` (Phase 1+2) | Medium |
| Email alerts (#14) | 2 Critical bugs: savepoint rollback + SMTP startup validation | **High — fix before deploy** |

To implement next: Fix Email alerts criticals → then Price monitoring (Sprint 6)

## License

Proprietary — all rights reserved.
