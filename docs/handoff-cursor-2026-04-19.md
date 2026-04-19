# Handoff Note for Cursor — 2026-04-19 (rev 3)

## Status after 2 test runs

| Platform | Content | Price | Current chain | Notes |
|----------|---------|-------|---------------|-------|
| Wildberries | ⚠ L0 wrong card | ✅ L0 (but wrong product) | L0→L2→L3 | nm_id 844578103 is correct (it's in the WB URL). L0 failed because the seller token belongs to a different seller. L0 now falls through to L2 (fixed). |
| Ozon | ✅ L2 | ✅ L2 2090 RUB | L0→L2→L3 | L0 returned 404 (not seller's product), L2 worked fine. |
| Лента | ❌ FAIL | ❌ FAIL | L1→L2→L3 | L1 got 401 now maps to ANTIBOT_BLOCK (faster fallback). L2 blocked by Qrator. Yandex warm-up now enabled. |
| Самокат | ❌ FAIL | ❌ FAIL | L2→L3 | scraper_mode=playwright skips L1. L2 blocked. Yandex warm-up now enabled. |

## What changed since last test run (commits fa9f9b1 → 435b537)

### Code fixes

1. **WB price kopecks bug** — `/api/v2/list/goods/filter` returns kopecks, code wasn't dividing by 100.
   72800 kopecks → 728.00 RUB is correct for bulk Agusha pack.

2. **WB nm_id mismatch** — `_collect_content` now validates returned `nmID == requested nm_id`.
   If the seller's catalog doesn't contain the product, raises `NOT_FOUND` (logged).

3. **L0 NOT_FOUND fallback** — `NOT_FOUND` from L0 now falls through to L2 instead of propagating.
   WB and Ozon L0 correctly fall back to patchright L2 when the product is not in the seller's catalog.
   (The seller tokens were from the user's own WB/Ozon cabinet. The Agusha SKU belongs to a different seller.)

4. **Lenta/Samocat L1 401→ANTIBOT_BLOCK** — 401/403 now immediately mapped to `ANTIBOT_BLOCK` instead of retrying 3× as `API_UNAVAILABLE`.

5. **ScraperRouter L1 PARSE_ERROR fallback** — Samocat `external_id` is a URL slug (not numeric).
   `_parse_product_id` raises `PARSE_ERROR`. Previously propagated; now falls through to L2.

6. **Yandex search warm-up** — `PlaywrightScraper` now supports `yandex_warmup: true` in `platform_config`.
   When enabled: visits `yandex.ru` before the product page, then loads product with
   `Referer: https://yandex.ru/search/?text=<query>`.
   Anti-bot (Qrator, Cloudflare) treats Yandex referrer as organic traffic.
   **Enabled in DB** for all 4 platforms.

### DB changes (already applied, no migration needed)

- `platforms.platform_config` updated for Лента, Самокат, Wildberries, Ozon:
  `{"yandex_warmup": true}` added.

---

## How to test (updated)

### 0. Restart collector-playwright to pick up code changes

```bash
docker compose up -d --force-recreate collector-playwright
```

### 1. Trigger content collection

```bash
# Get sku_platform IDs
docker compose exec postgres psql -U cat_user cat_db -c \
  "SELECT sp.id, p.name, sp.external_id FROM sku_platforms sp JOIN platforms p ON p.id=sp.platform_id JOIN skus s ON s.id=sp.sku_id WHERE s.id='ad1eff66-e6be-4498-8214-29321e892ad6';"

# Trigger all (replace UUIDs)
docker compose exec collector-playwright celery -A app.celery_app.celery_app call wb.collect_content --args='["cb10c6e7-237d-4eee-9614-ad61d5081cf9"]'
docker compose exec collector-playwright celery -A app.celery_app.celery_app call ozon.collect_content --args='["a8741901-d635-457d-b82a-b84f77289fc7"]'
docker compose exec collector-playwright celery -A app.celery_app.celery_app call lenta.collect_content --args='["b6c45ea3-152a-4b77-afde-2db8dde27a20"]'
docker compose exec collector-playwright celery -A app.celery_app.celery_app call samocat.collect_content --args='["f538027a-9ac5-45a0-b879-9031ac962be1"]'
```

### 2. What to look for in logs

```
PlaywrightScraper: Yandex warm-up complete for Wildberries
ScraperRouter: level=l0 NOT_FOUND for Wildberries sku=844578103 — not in seller catalog, trying public scraping
ScraperRouter: collected content for sku=844578103 via Wildberries (level=l2)
```

### 3. Verify correct product in DB

```bash
docker compose exec postgres psql -U cat_user cat_db -c \
  "SELECT cs.collected_title, cs.scraper_level, cs.created_at FROM content_scores cs JOIN sku_platforms sp ON sp.id=cs.sku_platform_id WHERE sp.id='cb10c6e7-237d-4eee-9614-ad61d5081cf9' ORDER BY cs.created_at DESC LIMIT 3;"
```

Expected: title contains "Агуш" / "Яблоко" / "банан".

---

## Key architecture point — L0 Seller API

**L0 only works if the monitored SKU is sold by the token's seller account.**
CAT is a brand-monitoring tool, not a seller management tool. The user's WB/Ozon tokens
belong to their own seller cabinet which doesn't sell Agusha.

L0 is useful only if:
- The brand uses CAT to monitor their own products AND sells through their own WB/Ozon cabinet
- OR to get reference pricing of their own assortment

For monitoring competitor/brand products by other sellers → L1/L2/L3 only.

The tokens in DB are kept — they don't interfere (L0 NOT_FOUND now falls to L2 cleanly).

---

## Remaining blockers

### Лента — Qrator still likely to block L2

Even with Yandex referer, Qrator CDN does deep TLS/JS fingerprinting.
Options if Yandex warmup doesn't help:
1. **Residential proxy** — route collector-playwright through ISP IP (e.g. ProxyLine, Bright Data residential RU)
2. **Lenta mobile app API** — requires auth token from the app (reverse-engineer with mitmproxy)
3. **Accept partial coverage** — Lenta is one of 4 platforms; Ozon is already working

### Самокат — samokat.ru JS challenge

Same Qrator-class protection. Same options as Lenta.
Additionally: Samocat's mobile API (`api.samokat.ru/v2/items/{id}`) requires numeric product_id.
Current `external_id` is a URL slug. If numeric ID is found, update:
```sql
UPDATE sku_platforms SET external_id = '<numeric_id>'
WHERE id = 'f538027a-9ac5-45a0-b879-9031ac962be1';
```
The numeric ID can be found by opening samokat.ru/product/{slug} in devtools → Network → look for API call to `api.samokat.ru/v2/items/{NUMBER}`.

---

## Known gaps (not blocking MVP)

1. **E5 text scoring** — `description_score` + `composition_score` = 0 until model downloaded.
   Download: `docker compose exec processor python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-base')"`

2. **`cat.compute_text_embedding` routing bug** — task sent to `celery` queue, no worker consumes it.
   Processor handles `ml` queue. CLIP image scoring works. Text scoring deferred.

3. **Distribution plan** — empty dashboard. Not needed for content/price MVP test.

---

## SKU reference

| Field | Value |
|-------|-------|
| SKU ID | `ad1eff66-e6be-4498-8214-29321e892ad6` |
| SKU name | Фруктовое пюре Яблоко-банан-печенье 90г |
| WB sku_platform | `cb10c6e7-237d-4eee-9614-ad61d5081cf9` | external_id=844578103 |
| Ozon sku_platform | `a8741901-d635-457d-b82a-b84f77289fc7` | external_id=3504337170 |
| Лента sku_platform | `b6c45ea3-152a-4b77-afde-2db8dde27a20` | external_id=380973 |
| Самокат sku_platform | `f538027a-9ac5-45a0-b879-9031ac962be1` | external_id=fruktovoe-pyure-agusha... (slug) |
