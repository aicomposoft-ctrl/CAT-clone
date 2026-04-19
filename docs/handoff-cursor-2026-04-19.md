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

6. **`.env`**: `PLATFORM_SECRET_KEYS=YYJCDhOLxgfJ96W_bmCew1GrwwmDDfn_48KyYOv1N_8=` added (NOT committed — .env is gitignored).

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

Then trigger each platform (replace UUID with actual):
```bash
# WB
docker compose exec collector-playwright celery -A app.celery_app call \
  cat.collect_wb_content --args='["<wb_sku_platform_id>"]'

# Ozon (already routes to playwright queue — can also use collector-playwright)
docker compose exec collector-playwright celery -A app.celery_app call \
  cat.collect_ozon_content --args='["<ozon_sku_platform_id>"]'

# Lenta
docker compose exec collector-playwright celery -A app.celery_app call \
  cat.collect_lenta_content --args='["<lenta_sku_platform_id>"]'

# Samocat
docker compose exec collector-playwright celery -A app.celery_app call \
  cat.collect_samocat_content --args='["<samocat_sku_platform_id>"]'
```

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

WB Bearer token: `eyJhbGciOiJFUzI1NiIs...` (see .env history or ask user)
Ozon: client_id=3922854, api_key=02d41f8b-dd24-4a2e-b141-fc1bcf689d49

These are stored encrypted in DB. The `PLATFORM_SECRET_KEYS` Fernet key was used to encrypt them.
**Do NOT re-insert them** — they're already in the DB.
