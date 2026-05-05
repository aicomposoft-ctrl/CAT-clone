"""
Скрипт для поиска product_id товара на Пятёрочке и Магните.

Использование (запуск с хоста, Python 3.11+):
    pip install httpx
    python scripts/find_product_ids.py "агуша яблоко банан печенье"

Или из контейнера collector:
    docker compose exec collector-playwright python /app/scripts/find_product_ids.py "агуша яблоко"
"""

from __future__ import annotations

import sys
import httpx


def search_pyaterochka(query: str) -> None:
    """Поиск товара на 5ka.ru через публичный API поиска."""
    url = "https://5ka.ru/api/v2/search/"
    params = {
        "records_per_page": 5,
        "page_num": 1,
        "search_text": query,
        "stores": "",
        "categories": "",
        "is_new": "",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://5ka.ru/",
    }

    print("\n=== Пятёрочка (5ka.ru) ===")
    try:
        resp = httpx.get(url, params=params, headers=headers, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results") or []
        if not results:
            print(f"  Ничего не найдено по запросу: {query!r}")
            return
        for item in results:
            plu = item.get("plu") or item.get("id")
            name = item.get("name", "—")
            price = (item.get("special_price") or item.get("regular_price") or {}).get("price", "—")
            print(f"  PLU={plu}  цена={price}₽  название={name}")
        print(f"\n  → external_id для sku_platforms = PLU (число выше)")
    except Exception as exc:
        print(f"  ОШИБКА: {exc}")


def search_magnit(query: str) -> None:
    """Поиск товара на magnit.ru через публичный API каталога."""
    url = "https://magnit.ru/api/v1/product/"
    params = {"term": query, "limit": 5}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://magnit.ru/",
    }

    print("\n=== Магнит (magnit.ru) ===")
    try:
        resp = httpx.get(url, params=params, headers=headers, timeout=15.0)
        if resp.status_code == 404:
            # Попробовать альтернативный endpoint поиска
            alt_url = "https://magnit.ru/api/v1/catalog/search/"
            resp = httpx.get(alt_url, params=params, headers=headers, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()
        items = data if isinstance(data, list) else (
            data.get("products") or data.get("results") or data.get("items") or []
        )
        if not items:
            print(f"  Ничего не найдено по запросу: {query!r}")
            print("  Подсказка: зайдите на magnit.ru, найдите товар вручную,")
            print("  откройте страницу товара и посмотрите числовой id в URL или DevTools.")
            return
        for item in items:
            product_id = item.get("id") or item.get("productId")
            name = item.get("name") or item.get("title", "—")
            price = item.get("price") or item.get("currentPrice", "—")
            print(f"  ID={product_id}  цена={price}₽  название={name}")
        print(f"\n  → external_id для sku_platforms = ID (число выше)")
    except Exception as exc:
        print(f"  ОШИБКА: {exc}")
        print("  Подсказка: зайдите на magnit.ru вручную и найдите id товара в DevTools.")


def main() -> None:
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "агуша яблоко банан"
    print(f"Поиск: {query!r}")
    search_pyaterochka(query)
    search_magnit(query)
    print()


if __name__ == "__main__":
    main()
