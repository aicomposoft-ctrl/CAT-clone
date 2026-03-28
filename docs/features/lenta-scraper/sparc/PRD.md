# PRD: Lenta Scraper

## Overview

Collect product content, prices, stock availability, and customer reviews from
Lenta's online grocery store (lenta.com) for FMCG brands monitored in CAT.

Lenta is Russia's second-largest food retail chain (~1000 hypermarkets and
supermarkets). Their online store exposes a public REST JSON API used by the
lenta.com website and mobile apps. A single product endpoint returns content,
price, and stock fields — the same efficient single-endpoint pattern used by
the Samocat scraper.

## Problem

FMCG brands listed on Lenta online cannot automatically monitor whether their
product cards degrade (wrong description, missing images), prices drift from
standards, stock goes out-of-range, or reviews accumulate negative sentiment.
Manual monitoring of 1 000+ SKUs across lenta.com is not scalable.

## Goals

1. Automated daily collection of content, price, stock, and reviews for all
   Lenta SKUs registered in CAT.
2. Data stored in the existing `content_scores`, `price_snapshots`, and
   `reviews` tables — no schema changes required.
3. Consistent architecture with the WB, Ozon, and Samocat scrapers: same
   `BaseScraper` contract, same Celery task pattern, same partial-row upsert.

## Non-Goals

- Real-time price monitoring (handled by the every-4h price orchestrator).
- Scraping Lenta brick-and-mortar store data (online store only).
- Checkout, cart, or authentication flows.

## Target Users

Internal: CAT's Celery worker pool (no end-user UI).
Downstream: ML scoring pipeline and Excel report generators.

## Success Metrics

| Metric | Target |
|--------|--------|
| Daily collection success rate | ≥ 95 % of active Lenta SKUs |
| p95 task latency | ≤ 10 s per SKU |
| Test coverage | ≥ 85 % (unit, no real HTTP) |
| Zero new DB tables | Schema unchanged |

## Constraints

- Rate limit: **1.0 req/sec** (conservative for a traditional retailer API;
  no published SLA, stricter than Samocat's darkstore 2.0).
- Image CDN allowlist: only `https://lenta.com/images/` paths (SSRF guard).
- `product_id` (article): numeric string, same validation as Samocat.
- Proxy rotation mandatory (see `BaseScraper`).
- No API key required — public endpoint, mobile app UA.

## Delivery

Sprint 2 — same sprint as WB/Ozon/Samocat scrapers.
