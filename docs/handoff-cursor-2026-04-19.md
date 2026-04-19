# Handoff Note for Cursor — 2026-04-19

## What We're Testing

MVP scenario: 1 SKU "Фруктовое пюре Агуша Яблоко-банан-печенье 90г", 4 platforms:
- **Wildberries** (nm_id = артикул продавца)
- **Ozon** (product_id)
- **Лента** (slug/product path)
- **Самокат** (product path)

Goal: collector picks up SKU data (content + price), content score appears in dashboard.

---

## Network situation — CRITICAL

**VPN must be OFF** when you run this test.

- With VPN on → Selectel IP 185.76.8.193 → blocked by Qrator (Lenta), Cloudflare (WB), Akamai (Ozon)
- Without VPN → residential IP 178.178.244.47 → all platforms accessible normally

---

## Credentials — ALREADY IN DB

WB and Ozon Seller API tokens are encrypted and stored in `org_platform_credentials` table:

| platform | api_token_type | credential row id |
|----------|----------------|-------------------|
| Wildberries | `wb_seller` | f7fc1695-9e3c-4bc2-ab95-0f2d9a5d43a5 |
| Ozon | `ozon_seller` | e2b96e98-6949-48df-9ac8-5c238879ba6b |

Encryption key is in `.env` as `PLATFORM_SECRET_KEYS`. **DO NOT commit .env.**

The `collector-playwright` container reads this key and decrypts credentials at runtime.

Scraper chain for WB and Ozon:
- **L0** (Seller API — no anti-bot, uses stored token) → tried first
- **L2** (patchright browser, Chrome 131 UA) → fallback
- **L3** (OpenAI GPT-4o-mini accessibility tree) → last resort

Lenta and Samocat have no seller API; chain is L2 → L3.

---

## What Claude fixed this session

1. **`anti_bot.py`**: classify_page_state() now checks `title_l` for "http 403" — Lenta block page has "HTTP 403" in `<title>`, not body. Previously stored as collected_title. (commit bd72286)

2. **`browser_pool.py`**: Chrome UA aligned to 131 in both `fresh` and `default` context variants — patchright >=1.50 ships Chromium 1208 = Chrome 131. Mismatch was a bot signal. (commit bd72286)

3. **`celery_app.py`**: WB, Samocat, Lenta tasks now route to `playwright` queue (Ozon was already there). All 4 platforms handled by `collector-playwright` container which has BrowserPool available.

4. **`scraper_router.py`**: L2 adaptive retry — on hard block, evicts shared context and retries with fresh browser profile. `page_url` passed from `SKUPlatform.url` through to L2/L3.

5. **`docker-compose.yml`**: `PLATFORM_SECRET_KEYS` explicitly exposed to `collector-playwright` environment.

6. **`.env`**: `PLATFORM_SECRET_KEYS=<fernet-key>` added (NOT committed — .env is gitignored). Ask operator for the key value.

---

## How to Start and Test

### 1. Start Docker Compose

```bash
cd /path/to/CAT-clone
docker compose up -d
```

Wait for all services healthy (check with `docker compose ps`).

### 2. Verify collector-playwright has PLATFORM_SECRET_KEYS

```bash
docker compose exec collector-playwright env | grep PLATFORM_SECRET_KEYS
```

Should show the key. If empty — the .env file might not have it; add it manually.

### 3. Trigger collection for the Agusa SKU

Find the SKU platform IDs first:
```bash
docker compose exec postgres psql -U cat_user cat_db -c \
  "SELECT sp.id, p.name, sp.external_id FROM sku_platforms sp JOIN platforms p ON p.id=sp.platform_id JOIN skus s ON s.id=sp.sku_id WHERE s.name ILIKE '%агуш%';"
```

Then trigger each platform (replace UUID with actual). **Correct task names** use the `wb.` / `ozon.` / `lenta.` / `samocat.` prefix (not `cat.`):
```bash
# WB
docker compose exec collector-playwright celery -A app.celery_app.celery_app call \
  wb.collect_content --args='["<wb_sku_platform_id>"]'

# Ozon
docker compose exec collector-playwright celery -A app.celery_app.celery_app call \
  ozon.collect_content --args='["<ozon_sku_platform_id>"]'

# Lenta
docker compose exec collector-playwright celery -A app.celery_app.celery_app call \
  lenta.collect_content --args='["<lenta_sku_platform_id>"]'

# Samocat
docker compose exec collector-playwright celery -A app.celery_app.celery_app call \
  samocat.collect_content --args='["<samocat_sku_platform_id>"]'
```

Or dispatch all monitored SKUs at once:
`wb.collect_content_all`, `ozon.collect_content_all`, `samocat.collect_content_all`, `lenta.collect_content_all` (and `*_collect_prices_all` pairs).

### 4. Monitor progress

```bash
docker compose logs -f collector-playwright
```

Look for:
- `ScraperRouter: collected content for sku=... via ... (level=l0)` → L0 Seller API worked
- `ScraperRouter: collected content for sku=... via ... (level=l2)` → Playwright worked
- `ScraperRouter: level=l0 failed with ... — trying next level` → L0 blocked, fell back

### 5. Check results in dashboard

Open http://localhost in browser → Content tab.
Content score should appear for the SKU after collection completes.

---

## Known Gaps (won't block MVP test)

1. **E5 model not downloaded** — `description_score` and `composition_score` will be 0 in `content_total`.
   Only `image_score` (CLIP) will be computed. This is OK for the test.
   Fix later: `docker compose exec processor python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-base')"`

2. **`cat.compute_text_embedding` routing bug** — this task is defined in `services/api/` and sent to default `celery` queue, but no worker consumes that queue. CLIP embeddings work (go to `ml` queue → processor). Text scoring is deferred.

3. **Distribution plan** — no plan exists; distribution monitoring dashboard will show empty. Not needed for content/price test.

---

## Seller API credentials reference (DO NOT put raw tokens in code)

WB Bearer token and Ozon (client_id/api_key) are stored encrypted in DB.
Ask operator for raw values if re-encryption is needed.
The `PLATFORM_SECRET_KEYS` Fernet key was used to encrypt them.
**Do NOT re-insert them** — they're already in the DB.

---

## Cursor verification — 2026-04-19 (VPN off, per operator)

**Environment:** `docker compose ps` — stack up (api, nginx, frontend, postgres, redis, `collector-playwright`, etc.).  
**Worker refresh:** `docker compose up -d --force-recreate collector-playwright` so `PLATFORM_SECRET_KEYS` from `.env` is applied.  
**Trigger:** all eight orchestrators: `wb|ozon|samocat|lenta` × (`collect_*_content_all`, `collect_*_prices_all`).  
**SKU in DB:** one SKU `ad1eff66-e6be-4498-8214-29321e892ad6` («Фруктовое пюре Яблоко-банан-печенье 90г»), four `sku_platforms` rows (WB, Ozon, Лента, Самокат).

### Outcome summary

| Platform | Content | Price | Scraper levels observed | Notes |
|----------|---------|-------|-------------------------|--------|
| Wildberries | L0 `200` from Seller content API | L0 price `72800` | l0 | Logs: `ScraperRouter: collected ... (level=l0)`. **Data quality:** `content_scores.collected_title` for latest row is **not** the Agusha product (wrong card returned for `nm_id` / seller catalog). Needs catalog/token alignment review. |
| Ozon | L2 success | L2 **2090.00** RUB | l2 | Logs: `collect_ozon_content: done ... scraper_level=2`, `collect_ozon_price: done ... scraper_level=2`. Seller L0 returned `404` on some seller endpoints; fallback path worked. |
| Самокат | **FAIL** `ALL_LEVELS_FAILED` | **FAIL** `ALL_LEVELS_FAILED` | l2→l3 | Anti-bot / challenge on product URL; L3 `OpenAIAgentScraper` also `ANTIBOT_BLOCK`. |
| Лента | **FAIL** `ALL_LEVELS_FAILED` (this run) | **FAIL** `ALL_LEVELS_FAILED` (this run) | l1 `401` → l2/l3 | Reasons in logs: `empty_response`, `geo_or_auth_block`. **Older** `price_snapshots` rows (e.g. L3, ~999.99) still in DB from prior runs — not updated this time. |

### Pass/fail vs “key scenario” (content + price + visible in UI)

- **Full 4/4 success:** no — Samokat and Lenta failed this run; WB L0 “works” but **wrong product** in stored title.
- **Partial:** Ozon price + content pipeline **OK** (L2). WB price numeric from L0 **written**; content row **suspect**.
- **UI:** not re-checked in browser here; API/DB show mixed data — recommend opening **Content** after fixing WB nm/seller mapping and Lenta/Samokat egress.

### For Claude Code next steps

1. Fix **handoff task names** (use `app.celery_app.celery_app` and `wb.collect_*`, not `cat.collect_*`) — partially corrected above.  
2. Investigate **WB L0** returning wrong card for `844578103` (seller scope vs nm_id).  
3. **Lenta / Samokat:** reproduce `geo_or_auth_block` vs handoff note (residential IP without VPN); may need session cookies, geo init, or stable RU egress.  
4. Remove or redact raw secrets from this doc’s appendix before sharing externally.
