# Validation Report — Commerce Analytics Tool (CAT)

> **SPARC Phase 2: Validation** | Requirements Testability Analysis
> **Date:** 2026-03-21 | **Validator:** requirements-validator + brutal-honesty-review

---

## Summary

| Metric | Value |
|--------|-------|
| User Stories analyzed | 10 |
| Average score | 84/100 |
| BLOCKED (score <50) | 0 |
| Status | ✅ READY FOR DEVELOPMENT |

---

## Results Table

| Story | Title | Score | INVEST | SMART | Security | Status |
|-------|-------|-------|--------|-------|----------|--------|
| US-01 | Content Score Dashboard | 82/100 | 6/6 ✓ | 4/5 | N/A | READY |
| US-02 | Reference Upload | 85/100 | 6/6 ✓ | 5/5 ✓ | +5 | READY |
| US-03 | Content Alert | 91/100 | 6/6 ✓ | 5/5 ✓ | N/A | READY |
| US-04 | Distribution Plan vs Fact | 85/100 | 6/6 ✓ | 5/5 ✓ | N/A | READY |
| US-05 | Stock by Dark Store | 80/100 | 6/6 ✓ | 4/5 | N/A | READY |
| US-06 | Price & Promo Tracking | 75/100 | 5/6 ✓ | 4/5 | N/A | READY |
| US-07 | Excel Export (Content) | 88/100 | 6/6 ✓ | 5/5 ✓ | N/A | READY |
| US-08 | Excel Export (Stock) | 88/100 | 6/6 ✓ | 5/5 ✓ | N/A | READY |
| US-09 | Competitor Price Monitoring | 82/100 | 6/6 ✓ | 5/5 ✓ | N/A | READY |
| US-10 | Platform Configuration | 80/100 | 6/6 ✓ | 4/5 | +5 | READY |

---

## Detailed Analysis

### US-01: Content Score Dashboard (82/100)

#### INVEST Analysis
| Criterion | Pass | Notes |
|-----------|------|-------|
| Independent | ✓ | Depends only on collected data, not other stories |
| Negotiable | ✓ | Score composition can be adjusted |
| Valuable | ✓ | "so that I can prioritize which cards need correction" |
| Estimable | ✓ | ~13 story points |
| Small | ✓ | Single dashboard view |
| Testable | ✓ | Score 0-100%, color coding, sortability — all measurable |

#### SMART Analysis
| Criterion | Pass | Notes |
|-----------|------|-------|
| Specific | ✓ | Columns defined, score formula specified |
| Measurable | ✓ | 0-100%, color thresholds defined |
| Achievable | ✓ | Standard image/text comparison ML |
| Relevant | ✓ | Core use case for Trade Marketing Manager |
| Time-bound | ⚠️ | Dashboard freshness not specified — recommend "data ≤24h old" |

**Recommendation:** Add AC: "Data shown is from the last 24-hour collection cycle, timestamp visible."

---

### US-03: Content Alert (91/100 — Best Scored)

#### INVEST Analysis — All 6/6 ✓

#### SMART Analysis — All 5/5 ✓
- Threshold: configurable (specific) ✓
- Delivery: "within 2 hours" (time-bound) ✓
- Email content: SKU name, platform, score, link (specific) ✓

---

### US-06: Price & Promo Tracking (75/100)

#### INVEST Analysis
| Criterion | Pass | Notes |
|-----------|------|-------|
| Estimable | ⚠️ | "significant changes (configurable threshold)" is vague — needs default value |

#### SMART Analysis
| Criterion | Pass | Notes |
|-----------|------|-------|
| Specific | ⚠️ | "Significant changes" needs numeric default, e.g., ">5% price change" |
| Measurable | ✓ | "within 4 hours" defined |

**Recommendation:** Rewrite: "When a competitor price changes by ≥5% (configurable), notify within 4 hours."

---

### US-10: Platform Configuration (80/100)

#### Security Criteria (Admin feature) — +5 bonus
| Check | Pass | Notes |
|-------|------|-------|
| Authentication | ✓ | "authenticated as Admin" in Given |
| Authorization | ✓ | Admin role explicitly required |
| Input Validation | ⚠️ | Scraper name input not validated in AC |

---

## Cross-Cutting Concerns

### Security Architecture Assessment

| Area | Status | Notes |
|------|--------|-------|
| Auth: JWT + refresh tokens | ✅ | Specified in NFR section |
| Multi-tenant isolation | ✅ | Mentioned in security NFR |
| S3 private access | ✅ | Explicit |
| Password: bcrypt | ✅ | Explicit |
| HTTPS only | ✅ | Explicit |
| Rate limiting on auth | ⚠️ | Not specified — add to NFR |
| Webhook HMAC | N/A | No webhooks in MVP |
| Secret management | ⚠️ | No mention of startup secret validation |

**Action items:**
1. Add NFR: "Auth endpoints rate-limited to 10 requests/minute per IP"
2. Add NFR: "All required secrets validated at startup — missing = service refuses to start"

### Architecture Validation

| Constraint | Specified | Status |
|-----------|-----------|--------|
| Distributed Monolith (Monorepo) | ✅ | PRD section 10 |
| Docker + Docker Compose | ✅ | PRD section 10 |
| VPS (AdminVPS/HOSTKEY) | ✅ | PRD section 10 |
| MCP servers (optional) | ✅ | PRD section 10 |

### Data Model Completeness

Required entities identified:
- `tenants` — multi-client isolation
- `users` — auth, roles (Admin, Brand Manager, Trade Marketing, Agency)
- `skus` — brand, article, barcode, category, platforms
- `sku_references` — image URL, description, composition
- `platforms` — name, type, scraper, schedule
- `content_scores` — sku_id, platform_id, date, image_score, desc_score, comp_score
- `stock_data` — sku_id, platform_id, store_address, city, quantity, date
- `distribution_plans` — sku_id, network, plan_tt
- `reviews` — sku_id, platform_id, text, sentiment, date
- `price_history` — sku_id, platform_id, price, discount, date
- `alerts` — type, recipient, status, sent_at

All entities derivable from user stories — **complete**.

---

## Brutal Honesty Review (Linus Mode)

**What's solid:**
- User stories have real acceptance criteria with measurable outcomes
- Gherkin scenarios in Specification.md are concrete with actual data examples
- Architecture constraints are realistic and well-specified

**What needs attention:**

1. **US-06 vagueness** — "significant changes (configurable threshold)" with no default means the first sprint will bikeshed on this. Pick a number: 5%.

2. **Missing: scraper anti-detection NFR** — You're scraping 110+ platforms commercially. Every major marketplace actively blocks scrapers. No mention of proxy rotation, rate limiting, user-agent rotation, or CAPTCHA handling. This is not an edge case — it's the core technical risk of the entire product. **Add an NFR or architecture decision document for this.**

3. **Missing: data consistency NFR** — If a scraper fails mid-run (50% collected), what's the user experience? "Graceful degradation" is mentioned but not defined per platform. Define: "Partial data is shown with staleness indicator. Stale = data > 48h old."

4. **Content scoring algorithm** — "Image:Front match %" is listed but the algorithm is undefined. Is it perceptual hash? SSIM? Feature vector comparison? This ambiguity will cause sprint 3 to explode. Add to Architecture.md.

**Verdict: APPROVED with action items above.**

---

## Overall Verdict

```
✅ ALL 10 USER STORIES PASS (average 84/100)
No stories BLOCKED.

Action items before Sprint 1:
□ US-06: Add default threshold (5%) to price alert AC
□ NFR: Add rate limiting spec to auth endpoints
□ NFR: Add secret validation on startup spec
□ NFR: Add scraper anti-detection strategy (proxy, rate limiting)
□ NFR: Define partial data / staleness behavior
□ Architecture.md: Specify content scoring algorithm (image comparison method)
```
