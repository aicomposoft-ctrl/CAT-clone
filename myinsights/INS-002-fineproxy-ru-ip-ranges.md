# INS-002: FineProxy — Russian IPs только в диапазоне 178.20.x.x

**Category:** scraping  
**Status:** Active  
**Hit Count:** 1  
**Date:** 2026-04-06

## Problem

FineProxy план `SuperVIP` с `type=https_ip` выдаёт список из 73 прокси. Большинство (193.202.x.x, 146.19.x.x) оказались US/EU датацентрами, хотя ожидались российские IP.

## Solution

Российские IP в пуле FineProxy находятся **только в диапазоне `178.20.x.x`**:
- `178.20.213.x` → RU Moscow (AS QualityNetwork)
- `178.20.214.x` → RU Kaliningrad (AS QualityNetwork)

```python
# Фильтрация только RU прокси из пула FineProxy
def filter_russian_proxies(proxy_list: list[str]) -> list[str]:
    return [p for p in proxy_list if p.startswith(("178.20.213.", "178.20.214."))]
```

Для получения полного списка с raw IP использовать `type=socks5_ip` (не `https_ip`), который возвращает IP:port без hostname-обёртки.

```
# type=https_ip → net-178-20-214-108.mcccx.com:8444 (домены)
# type=socks5_ip → 178.20.214.108:9999 (raw IPs — удобнее для геофильтрации)
```

**Важно:** даже с Russian IP WB возвращает 498 из-за wbaas (см. INS-001). Нужны residential RU прокси, не datacenter.

## Why It Works

FineProxy держит смешанный пул: US Seattle (193.202.x, 146.19.x) + RU Kaliningrad/Moscow (178.20.x). Тип прокси (`https_ip`, `socks5_ip`, `http_ip`) влияет только на протокол и порт — не на гео.

## Applies To

- `test_proxy.py` — скрипт тестирования прокси
- `services/collector/app/core/base_scraper.py` — proxy rotation
- Конфигурация FineProxy в `.env`: `PROXY_LIST_URL`
