# PRD: Anti-Bot HTTP Upgrade

**Feature:** anti-bot-http-upgrade  
**Date:** 2026-04-19  
**Status:** Planning  

## Problem Statement

CAT collector pipeline's L1 scrapers use `httpx` for HTTP requests. `httpx` sends a Python/OpenSSL TLS fingerprint (JA3/JA4) that Akamai Bot Manager and Cloudflare identify instantly as non-browser traffic. Additionally, the L2 Playwright BrowserPool leaks automation via `Runtime.enable` CDP command, which all major anti-bot systems (Cloudflare, Akamai, DataDome) detect.

**Current failure modes:**
- WB L1: `challenge_page` / `ANTIBOT_BLOCK` — Cloudflare detects Python TLS fingerprint
- Ozon L1: 403 from Akamai — JA3/JA4 mismatch + HTTP/2 fingerprint
- L2 Playwright: detected as automation via CDP leak → `challenge_page`

## Solution

1. **Replace `httpx` with `curl_cffi`** for L1 scrapers (WB, Ozon) — impersonates Chrome TLS fingerprint at network protocol level
2. **Replace `playwright` with `patchright`** in BrowserPool — patches CDP `Runtime.enable` leak, drop-in API replacement

## Goals

- Increase L1 success rate for WB (`card.wb.ru`) and Ozon (`composer-api.bx`) from ~0% to measurable positive rate
- Increase L2 success rate by eliminating CDP automation detection
- Zero breaking changes to existing scraper API contracts
- Zero new external services required (no paid proxy APIs)

## Non-Goals

- Solving Lenta/Samocat auth issues (separate investigation needed)
- Adding residential proxy rotation (future feature)
- Replacing L3 OpenAI scraper
- Solving Camoufox/Firefox path (Akamai blocks Camoufox C++ patches — verified issue #555)

## Success Metrics

- L1 WB: at least 1 successful `collect_content` / `collect_price` per test run without L2 fallback
- L1 Ozon: reduced 403 rate in logs (measurable via `scraper_level` field in DB)
- L2: reduced `challenge_page` ANTIBOT_BLOCK occurrences in router logs
- No regression in existing tests

## Constraints

- `curl_cffi` requires Python 3.10+ — CAT uses Python 3.11 ✅
- `patchright` is Chromium-only — CAT already uses Chromium ✅
- Must not break `asyncio.run_coroutine_threadsafe` threading model in BrowserPool
- `collector/requirements.txt` changes must be reflected in Docker image rebuild
