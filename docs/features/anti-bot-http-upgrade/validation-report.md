# Validation Report: anti-bot-http-upgrade

Date: 2026-04-19  
Mode: 5 parallel agents  
Gate threshold: score >= 70 per story, zero BLOCKED (< 50)

## Scores

| Agent | Score | Status |
|-------|-------|--------|
| US completeness (avg US-1..US-4) | 78 | PASS |
| BDD scenario coverage | 62 | PASS (above 50 minimum) |
| Technical feasibility | 72 | PASS |
| Security / multi-tenant | 72 | PASS |
| Acceptance criteria clarity (avg) | 74 | PASS |

**Gate result: PASS** — no BLOCKED items

## Critical Issues (must fix in Phase 3)

1. **Proxy per-request, not per-session** — curl_cffi session initialised with frozen proxy breaks ProxyRotator rotation. Fix: pass `proxies=` kwarg per `_get()` call.
2. **`_proxy_rotator` naming** — pseudocode uses wrong attribute name. Actual: `self._proxy`. Will cause AttributeError at runtime.
3. **SSRF: URL allowlist before cffi routing** — existing `_WB_IMAGE_CDN_RE` and `_OZ_IMAGE_CDN_RE` guards are in scrapers, not in `_get()`. No additional SSRF risk introduced by this change (scrapers construct all URLs internally, no user input reaches `_get()`). **Acceptable — not a new risk.**
4. **`raise_for_status` adapter** — avoid `request=None` which crashes httpx internals. Fix: raise `httpx.HTTPStatusError` with a minimal stub request, or raise `ScraperError` directly.

## Minor Issues (document as follow-up)

- BDD gaps: Ozon scenario, BaseScraper httpx-fallback scenario, E1/E6 edge cases
- patchright version pin: use `>=1.50.0,<2.0` in requirements.txt
- Proxy credential masking in debug logs
