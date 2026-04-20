# Handoff Note for Cursor — 2026-04-20 (rev 4)

## Status after 3 test runs + deep investigation

| Platform | Content | Price | Chain | Notes |
|----------|---------|-------|-------|-------|
| Wildberries | ❌ ALL FAIL | ❌ ALL FAIL | L0→L2→L3 | WB deployed **wbaas fingerprint challenge** on ALL endpoints. Blocked at all levels. See WB section below. |
| Ozon | ✅ L2 | ✅ L2 2090 RUB | L0→L2→L3 | L0 NOT_FOUND (own seller), L2 working with patchright. |
| Лента | ❌ FAIL | ❌ FAIL | L1→L2→L3 | L1 gets 401 → ANTIBOT_BLOCK (fast). L2 blocked by Qrator. Google warm-up enabled. |
| Самокат | ❌ FAIL | ❌ FAIL | L2→L3 | L2 blocked by Qrator. Google warm-up enabled. |

---

## Critical Finding: WB wbaas Anti-Bot System

### Root Cause (investigated 2026-04-20)

WB deployed **wbaas** — a comprehensive fingerprinting anti-bot system — across ALL WB domains and APIs. This blocks every scraping level:

**WB L1 (curl_cffi):**
- `card.wb.ru/cards/v2/detail` → HTTP 404 + `x-pow: status=invalid;challenge=7,8,1,...`
- The `x-pow` challenge requires solving a **Proof of Work** using browser fingerprinting data
- `curl_cffi` TLS impersonation bypasses TLS checks but cannot solve fingerprint-based PoW
- `card.wildberries.ru` doesn't resolve from Docker container

**WB L2/L3 (patchright browser):**
- `www.wildberries.ru` → HTTP 498 + wbaas challenge page ("Почти готово... Проверяем браузер")
- Browser loads `challenge_fingerprint_v1.0.23.js` + `challenge_solver_v1.0.4.js`
- `POST /__wbaas/challenges/antibot/api/v1/create-token` called 4 times → all fail with 498
- Headless Chromium (even patchright) fails the fingerprinting: canvas/WebGL/audio detectable

**The wbaas challenge flow:**
```
Client → GET www.wildberries.ru/... → 498 "Почти готово"
Browser → loads challenge_fingerprint_v1.0.23.js (126KB, fingerprints browser)
Browser → loads challenge_solver_v1.0.4.js (44KB, solves PoW)
Browser → POST /api/v1/create-token {fingerprint, solution} → 498 (headless detected)
                                                              → 200 + x_wbaas_token cookie (real browser)
```

### WB Workaround Options

**Option 1 (fastest): Residential proxy (ProxyLine/Bright Data)**
- Different IP reputation may help
- But fingerprinting still detects headless — partial fix at best
- Cost: ~$0.01-0.05/GB residential

**Option 2: `playwright-stealth` equivalent for Python**
- Canvas fingerprint spoofing (randomize canvas noise)
- WebGL vendor/renderer spoofing
- Audio context fingerprint normalization
- Navigator.plugins polyfill
- See: https://github.com/Kaliiiiiiiiii-Vinyzu/patchright (check latest stealth features)

**Option 3: Remote browser via Browserless/Bright Data's Browser API**
- Real browser hosted on real IPs
- Most reliable but expensive (~$200/mo)

**Option 4: Find WB mobile API endpoint**
- WB Android app uses separate endpoints (`mobile-api.wildberries.ru`) — DNS doesn't resolve from Docker
- If resolved: would need app-specific auth tokens
- Not currently viable from VPS

**Option 5: Accept WB partial coverage**
- WB is 1/4 platforms. Ozon/Lenta/Samocat progress more important
- WB data gap documented in dashboard

### What NOT to do
- Don't try to implement wbaas PoW solver in Python: the challenge requires fingerprint data computed in JS (canvas hash, WebGL, audio) — not just SHA256 brute force
- Don't waste time on different curl_cffi parameters: the core issue is fingerprinting, not TLS

---

## What changed since rev 3 (previous handoff)

All rev 3 fixes are still in place:
1. WB nm_id mismatch detection (L0)
2. WB price kopecks bug fix (L0)
3. L0 NOT_FOUND → L2 fallback
4. Lenta/Samocat 401 → ANTIBOT_BLOCK (fast fallback)
5. L1 PARSE_ERROR → L2 fallback (Samocat slug)
6. Google search warm-up (working — confirmed "search warm-up complete engine=google")

**New in rev 4:**
- `wildberries.py` updated with accurate wbaas status documentation in docstring and `_CARD_APIS` comment
- No code changes that affect behavior (WB is blocked regardless)

---

## How to test (updated for rev 4)

### 0. Restart collector-playwright
```bash
docker compose up -d --force-recreate collector-playwright
```

### 1. Run Ozon content (this should still work at L2)
```bash
docker compose exec collector-playwright celery -A app.celery_app.celery_app call \
  ozon.collect_content --args='["a8741901-d635-457d-b82a-b84f77289fc7"]'
```

Expected log:
```
PlaywrightScraper: search warm-up complete for Ozon engine=google
ScraperRouter: collected content for sku=3504337170 via Ozon (level=l2)
```

### 2. Run WB (will fail, but verify correct failure path)
```bash
docker compose exec collector-playwright celery -A app.celery_app.celery_app call \
  wb.collect_content --args='["cb10c6e7-237d-4eee-9614-ad61d5081cf9"]'
```

Expected log:
```
ScraperRouter: level=l0 NOT_FOUND for Wildberries sku=844578103 — not in seller catalog
PlaywrightScraper: search warm-up complete for Wildberries engine=google  
PlaywrightScraper: anti-bot page detected at wildberries.ru/... (challenge_page)
ScraperRouter: ALL_LEVELS_FAILED for Wildberries
```

### 3. Verify DB state for Ozon
```bash
docker compose exec postgres psql -U cat_user cat_db -c \
  "SELECT cs.collected_title, cs.scraper_level, cs.created_at 
   FROM content_scores cs JOIN sku_platforms sp ON sp.id=cs.sku_platform_id 
   WHERE sp.id='a8741901-d635-457d-b82a-b84f77289fc7' 
   ORDER BY cs.created_at DESC LIMIT 3;"
```

---

## Remaining blockers

### WB — wbaas fingerprint challenge (see Critical Finding above)
Priority: Medium (Ozon works; WB data gap acceptable for MVP)
Action: Need residential proxy + stealth patches to proceed

### Лента — Qrator CDN block
Even with Google warm-up, Qrator does deep JS fingerprinting.
Same options as WB wbaas — residential proxy is the most realistic fix.
Alternative: Lenta mobile API (requires auth token from app)

### Самокат — Qrator + numeric product ID
Same Qrator protection as Лента.
Additionally: `external_id` is a URL slug. The numeric product_id can be found in:
`Network → XHR → api.samokat.ru/v2/items/{NUMBER}` when browsing the product page.
Once found:
```sql
UPDATE sku_platforms SET external_id = '<numeric_id>'
WHERE id = 'f538027a-9ac5-45a0-b879-9031ac962be1';
```

---

## Known gaps (not blocking MVP)

1. **E5 text scoring** — `description_score` + `composition_score` = 0 until model downloaded.
   Download: `docker compose exec processor python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-base')"`

2. **`cat.compute_text_embedding` routing** — task sent to `celery` queue, no worker consumes it.
   Fix: route to `ml` queue. Text scoring deferred.

3. **WB data gap** — WB scraping blocked until wbaas bypass implemented.

4. **Distribution plan** — empty dashboard. Not needed for content/price MVP.

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

---

## Architecture note: wbaas vs x-pow

The `x-pow` header on `card.wb.ru` and `server: wbaas` on all WB endpoints reveal that WB's
anti-bot is a single unified system (`wbaas`). The x-pow header is wbaas's API-level challenge
mechanism — it carries a serialized challenge that the browser normally solves via `challenge_solver_v1.0.4.js`
running in a sandboxed iframe. The solver:
1. Posts an empty `create-token` request
2. Receives challenge + fingerprint script path
3. Runs `challenge_fingerprint_v1.0.23.js` to collect browser fingerprints
4. POSTs `{challenge, solution}` to `create-token`
5. Gets `x_wbaas_token` cookie on success

Without the browser fingerprint, the x-pow challenge cannot be solved in pure Python.
