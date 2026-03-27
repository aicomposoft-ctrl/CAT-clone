# PRD — Wildberries Scraper (WB Scraper)

**Feature:** Wildberries Scraper
**Priority:** P0 | **Sprint:** 2 | **Story Points:** 8
**Status:** Planning

---

## 1. Problem Statement

Wildberries is Russia's largest marketplace (110M+ daily visitors). FMCG brands on CAT need daily data from WB to monitor content quality, prices, stock availability, and reviews for their SKUs. Without a WB scraper, the entire pipeline is inoperative for the most important platform.

WB uses JavaScript-heavy rendering for product cards, aggressive bot-protection (rate limiting, CAPTCHA triggers, IP bans), and a non-public API with frequently-changing endpoints. A naive HTTP scraper will be blocked within minutes.

**Impact:** Without WB data, content scoring, price monitoring, stock distribution, and review analysis all have no input data. P0 blocker for Sprint 2 analytics features.

---

## 2. Target Data

Per SKU × WB platform combination (`sku_platform` record where `platform.name = "Wildberries"`):

| Data Type | Fields | Frequency |
|-----------|--------|-----------|
| Content | title, description, composition, main image URL | Daily 02:00 |
| Price | price, original_price, discount_pct, promo_label | Every 4h |
| Stock | in_stock (bool), warehouse stock count | Daily 02:00 |
| Reviews | review_text, rating (1-5), review_date, external_review_id | Daily 02:00 |

`external_id` on `sku_platforms` = WB article number (nm_id), e.g. `"12345678"`.

---

## 3. Core Requirements

### Must Have (Sprint 2)
- Scrape content data (title, description, composition, main image URL) for a WB SKU by nm_id
- Scrape current price and original price by nm_id
- Scrape in_stock flag and warehouse availability by nm_id
- Scrape last 50 reviews for a WB SKU by nm_id
- Respect WB rate limits: ≤ 1 req/sec per IP
- Proxy rotation support (PROXY_LIST_URL env var)
- Celery task integration: each data type is a separate task
- Store results in PostgreSQL (content_scores, price_snapshots, reviews tables)
- Retry on 429/503 with exponential backoff (max 3 retries)
- Use Playwright for JS-rendered pages (product card)
- Use WB's card API for structured data where available

### Should Have
- Image download to MinIO (collected_image_url stored as S3 key)
- User-agent rotation
- Detect and handle "item deleted/out of assortment" gracefully

### Won't Have (this sprint)
- Scraping competitor SKUs (different workflow)
- Scraping WB search rankings
- Scraping seller info

---

## 4. Success Metrics

| Metric | Target |
|--------|--------|
| Success rate per daily run | ≥ 95% of SKUs collect without error |
| Price collection latency | < 30 s per SKU |
| Content collection latency | < 60 s per SKU (Playwright render) |
| Review collection latency | < 20 s per SKU (last 50) |
| Zero IP bans per week | Rate limiting + proxy rotation |

---

## 5. WB API Endpoints Used

| Data | Method | URL Pattern |
|------|--------|-------------|
| Product card | Playwright | `https://www.wildberries.ru/catalog/{nm_id}/detail.aspx` |
| Card API (structured) | HTTP GET | `https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=-1257786&nm={nm_id}` |
| Price history | HTTP GET | `https://wbx-content-v2.wbstatic.net/sellers/{nm_id}.json` (fallback) |
| Reviews | HTTP GET | `https://feedbacks2.wb.ru/feedbacks/v1/{nm_id}?take=50&skip=0&order=dateDesc` |
| Image CDN | HTTP GET | `https://basket-XX.wbbasket.ru/vol{vol}/part{part}/{nm_id}/images/big/1.jpg` |

---

## 6. Constraints

- Playwright runs in collector service (Docker: `mcr.microsoft.com/playwright/python`)
- Rate limit: `rate_limit = 1.0` req/sec (inherited from `BaseScraper`)
- Proxy: `PROXY_LIST_URL` env var; round-robin rotation
- WB blocks datacenter IPs — residential or mobile proxies required in production
- `nm_id` sourced from `sku_platforms.external_id` (must be set before scraping)
- Scraped data is untrusted: sanitise all text (strip HTML, limit lengths)
