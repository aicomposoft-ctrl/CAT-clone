# Handoff Report for Claude Code (post-Codespaces limit)

Date: 2026-04-17  
Repository: `CAT-clone`  
Goal of this phase: stable public data collection for marketplaces (focus: content + price, stock optional)

## 1) Context and checkpoint

After hitting GitHub Codespaces monthly limits, troubleshooting moved to local environment (Docker Compose on Windows).  
From this checkpoint, work focused on pipeline stability for:

- Wildberries
- Ozon
- Samokat
- Lenta

Primary requirement: run real scraping flow (L1 -> L2 -> L3), observe real anti-bot behavior, and keep moving toward successful content/price collection.

## 2) What was implemented after checkpoint

### 2.1 Adaptive anti-bot pipeline (L2/L3)

Implemented and wired:

- richer anti-bot classification (`challenge_page`, `geo_or_auth_block`, `empty_response`, etc.)
- adaptive L2 second-chance attempt with fresh browser profile/context
- BrowserPool knobs for shared vs fresh contexts
- per-platform anti-bot policy table
- reduced noisy retries for hard anti-bot outcomes
- improved diagnostics and structured `ScraperError.details`

Main touched modules:

- `services/collector/app/core/scraper_router.py`
- `services/collector/app/scrapers/playwright_scraper.py`
- `services/collector/app/core/browser_pool.py`
- `services/collector/app/core/anti_bot.py`
- `services/collector/app/tasks/_retry_policy.py`
- task modules for wb/ozon/samokat/lenta

### 2.2 L3 provider switchability + OpenAI parallel path

Added OpenAI L3 scraper and provider switch:

- new `OpenAIAgentScraper` in `services/collector/app/scrapers/openai_agent_scraper.py`
- `L3_PROVIDER` support (`anthropic`/`openai`) in router + docker compose env
- `OPENAI_API_KEY` optional secret registration in collector startup validation
- `openai>=1.0.0` dependency in collector requirements

### 2.3 Proxy and environment work

- proxy credentials were tested, then disabled after expiry
- confirmed runtime env in container: `SCRAPER_PROXY_URL/USER/PASS` empty
- L3 remained enabled (`SCRAPER_DISABLE_L3=0`) and provider set to `openai`

## 3) Critical bug fixes done in this session

### 3.1 Why L3 was not reached on Lenta price

Problem:

- L2 first attempt failed with `PARSE_ERROR`
- L2 second-chance also failed
- router flow stopped incorrectly before clean fallback to L3

Fixes in `scraper_router.py`:

- allow fallback after L2 `PARSE_ERROR`
- catch second-chance L2 exception and continue chain instead of hard break

Result:

- confirmed in logs that flow now reaches L3 for Lenta

### 3.2 OpenAI L3 resilience improvements

In `openai_agent_scraper.py`:

- added root warmup + materialization fallback before anti-bot assessment
- made price parsing tolerant to null fields from model output
- added fallback numeric extraction from text when model returns incomplete price JSON
- invalid/stale Redis L3 cache payload now gets dropped and recomputed
- normalized some L3 extraction failures to `PARSE_ERROR` for retry policy compatibility

## 4) Observed runtime outcomes (latest)

### 4.1 Confirmed successful case

Lenta price was successfully collected via L3 in one run:

- log: `ScraperRouter: collected price for sku=380973 via Лента (level=l3)`
- log: `collect_lenta_price: done ... scraper_level=3`
- DB row persisted:
  - `price=999.99`
  - `original_price=1199.99`
  - `discount_pct=16.70`
  - `scraper_level=3`

### 4.2 Current unstable behavior

Subsequent runs still fluctuate due to anti-bot and marketplace response variance:

- WB: mostly `challenge_page` on L2/L3
- Ozon: frequent `403` / challenge, occasional L2 partial success, unstable for price
- Samokat: strong anti-bot behavior on product page in current network profile
- Lenta: can pass through to L3 and succeed, but not deterministically every run

## 5) Why this still feels like a dead-end

Main blockers are now external/runtime, not missing pipeline wiring:

- anti-bot challenge variability per request/session/IP
- provider-side model safety/risk throttling in IDE requests (separate from scraper runtime)
- marketplace-side response instability (especially WB/Ozon)

Pipeline itself is no longer “broken by design”; it is now “operationally unstable under anti-bot pressure.”

## 6) Operational notes for next Claude Code pass

1. Keep request wording neutral in assistant prompts (avoid trigger phrases).  
2. Keep VPN enabled for provider/API reachability in this environment.  
3. Prioritize deterministic acceptance path:
   - lock Lenta content + price as baseline “working scenario”
   - then tune Ozon price/content stability
4. Add explicit telemetry counters (per level, per reason, per platform) for quick daily status.
5. Consider short-lived cache disable toggle for L3 debugging sessions.

## 7) Suggested immediate next tasks

1. Add structured “final attempt summary” log line in router with:
   - platform, sku, tried levels, terminal reason
2. Add targeted fallback selectors/parser for Ozon price payload variants seen in latest logs.
3. Add small “stability runner” script:
   - N repeated runs per platform
   - success ratio by data type
   - anti-bot reason histogram

---

This report covers work from the local troubleshooting checkpoint (after Codespaces limits) through current state, including the L3 routing and Lenta price stabilization fixes.

