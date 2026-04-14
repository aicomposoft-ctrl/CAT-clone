# Requirements Validation Report — Samocat Scraper

**Date:** 2026-03-31  
**Sprint:** 2  
**Validator:** requirements-validator skill (INVEST + SMART + Security)

---

## Summary

| Metric | Value |
|--------|-------|
| Stories analyzed | 6 |
| Average score | 84/100 |
| Blocked (score <50) | 0 |
| Status | **PASS — ready for implementation** |

---

## Results

| Story | Title | Score | INVEST | SMART | Security | Status |
|-------|-------|-------|--------|-------|----------|--------|
| US-1 | Content Collection | 90/100 | 6/6 ✓ | 5/5 ✓ | +5 bonus | READY |
| US-2 | Price Collection | 82/100 | 6/6 ✓ | 4/5 | +5 bonus | READY |
| US-3 | Stock Collection | 88/100 | 6/6 ✓ | 5/5 ✓ | +5 bonus | READY |
| US-4 | Reviews Collection | 82/100 | 6/6 ✓ | 4/5 | +5 bonus | READY |
| US-5 | Cross-Tenant Isolation | 75/100 | 4/6 | 5/5 ✓ | +5 bonus | READY |
| US-6 | Retry on Transient Errors | 88/100 | 6/6 ✓ | 5/5 ✓ | n/a | READY |

---

## Detailed Analysis

### US-1: Content Collection (90/100)

**INVEST:** 6/6 ✓  
**SMART:** 5/5 ✓ — specific fields listed (title, desc, composition, image_url), upsert behavior defined, NOT_FOUND handling specified.  
**Security:** SSRF allowlist `^https://cdn\.samokat\.ru/` specified for image downloads. Text sanitization mentioned. **+5 bonus**.

### US-2: Price Collection (82/100)

**INVEST:** 6/6 ✓  
**SMART:** 4/5 — fields specified (price, original_price, discount_pct, promo_label); missing: no timing/latency requirement stated.  
**Security:** Same infrastructure as US-1 — proxy env var implied. **+5 bonus**.

### US-3: Stock Collection (88/100)

**INVEST:** 6/6 ✓  
**SMART:** 5/5 ✓ — partial-row contract explicitly stated (content fields NOT overwritten), ON CONFLICT clause named.  
**Security:** Same infrastructure. **+5 bonus**.

### US-4: Reviews Collection (82/100)

**INVEST:** 6/6 ✓  
**SMART:** 4/5 — "up to 50 reviews" specified; dedup key `(sku_platform_id, external_review_id)` named; missing: no max review age / time window.  
**Security:** Same infrastructure. **+5 bonus**.

### US-5: Cross-Tenant Isolation (75/100)

**INVEST:** 4/6
| Criterion | Pass | Notes |
|-----------|------|-------|
| Independent | ✓ | Doesn't depend on other stories to be tested |
| Negotiable | ✗ | Non-negotiable by design (security rule) |
| Valuable | ✓ | Multi-tenant isolation is platform-critical |
| Estimable | ✗ | Not a standalone implementation story — it's a cross-cutting constraint |
| Small | ✗ | Spans 4 tasks (content, price, stock, reviews) |
| Testable | ✓ | Specific ACs per task with sku_platform_id assertions |

**SMART:** 5/5 ✓ — each sub-criterion is specific and measurable (sku_platform_id == sp_a_id assertion).  
**Security:** This IS the security story — tenant isolation is the security requirement. **+5 bonus**.  
**Note:** Score of 75 means READY; isolation constraints are well-specified even though the story straddles INVEST independence criteria.

### US-6: Retry on Transient Errors (88/100)

**INVEST:** 6/6 ✓  
**SMART:** 5/5 ✓ — specific HTTP codes (429, 503), retry count (3), backoff formula (2^attempt seconds), error codes defined.  
**Security:** n/a — no security-relevant surface.

---

## BDD Scenarios

```gherkin
# US-1
Scenario: Content collected from Samocat
  Given sku_platform with platform.name="Samocat" and external_id="12345"
  When collect_samocat_content runs
  Then content_scores is upserted with collected_title, collected_description,
       collected_composition, collected_image_url, scored_at=today()

Scenario: Product not found — silent skip
  Given Samocat returns HTTP 404 for product_id
  When collect_samocat_content runs
  Then no DB write occurs
  And INFO log "NOT_FOUND" is emitted

# US-3
Scenario: Stock collected without overwriting content
  Given content_scores row exists with collected_description="test"
  When collect_samocat_stock runs
  Then in_stock and warehouse_qty are updated
  And collected_description still equals "test" (partial-row contract)

# US-5
Scenario: Cross-tenant isolation for content task
  Given sp_a (org_A) and sp_b (org_B) share external product_id "12345"
  When collect_samocat_content(sp_a_id) runs
  Then content_scores upsert uses sku_platform_id=sp_a_id
  And no write occurs to rows with sku_platform_id=sp_b_id

# US-6
Scenario: Retry on 429 with exponential backoff
  Given Samocat returns HTTP 429 on first call
  When collect_samocat_content runs
  Then task retries with countdown=1s, then 2s, then 4s
  And after 3 retries raises ScraperError("RATE_LIMITED")

# Security
Scenario: SSRF attempt via external image URL
  Given Samocat returns image_url="https://evil.com/steal.jpg"
  When collect_samocat_content processes the response
  Then image download is BLOCKED (URL not matching ^https://cdn\.samokat\.ru/)
  And collected_image_url remains None
```

---

## Validation Decision

**PASS** — all 6 stories score ≥ 70/100, 0 blocked.

Key implementation constraints:
1. `rate_limit = 2.0` req/sec — enforced via `BaseScraper.rate_limit`
2. SSRF allowlist `^https://cdn\.samokat\.ru/` — validate before image download
3. `sanitize()` applied to all text fields (5000 char limit)
4. `PROXY_LIST_URL` from env only — no hardcoded proxies
5. Partial-row contract: stock task must not overwrite content fields
6. `max_retries=3`, `countdown=2**self.request.retries`
