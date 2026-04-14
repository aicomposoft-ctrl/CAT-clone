# INS-001: WB wbaas требует Playwright даже с Russian IP

**Category:** scraping  
**Status:** Active  
**Hit Count:** 1  
**Date:** 2026-04-06

## Problem

Wildberries возвращает HTTP 498 на все запросы через curl/httpx, даже при использовании российских datacenter IP (Kaliningrad 178.20.214.x, Moscow 178.20.213.x). Ожидалось, что Russian IP обойдёт гео-блок.

## Solution

WB использует собственную anti-bot систему **wbaas** (WB Anti-Abuse System), которая требует выполнения JavaScript-challenge в браузере. Это не гео-блок — это challenge-based защита.

Единственное рабочее решение: **Playwright** с headless Chromium.

```python
# WRONG — не работает даже с Russian proxy
async with httpx.AsyncClient(proxy="https://178.20.214.108:8444") as client:
    r = await client.get("https://www.wildberries.ru/")  # → 498

# CORRECT — Playwright решает JS-challenge
async with async_playwright() as p:
    browser = await p.chromium.launch()
    context = await browser.new_context(proxy={"server": "https://178.20.214.108:8444"})
    page = await context.new_page()
    await page.goto("https://www.wildberries.ru/")  # → 200
```

Исключение: `card.wb.ru` и `basket-NN.wbbasket.ru` (CDN API) — менее строгие, могут работать без Playwright при наличии валидных cookies.

## Why It Works

wbaas отдаёт страницу с JS-кодом (hCaptcha-like challenge). Curl не выполняет JS → получает 498 с заголовком `x-wbaas-token: get`. Playwright выполняет challenge → получает access token → 200.

## Applies To

- `services/collector/` — все WB-скраперы
- `BaseScraper`: для WB обязательно `use_playwright = True`
- Тестирование через curl из Codespace/CI — нерелевантно для WB
