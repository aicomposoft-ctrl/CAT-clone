#!/usr/bin/env python3
"""
Local scraper test — runs L1 HTTP scrapers for 4 platforms without Docker/DB/Redis.

Usage:
    cd /workspaces/CAT-clone/services/collector
    pip install httpx
    python ../../scripts/test_scrapers_local.py

Edit TEST_PRODUCTS below to use real product IDs from each platform.

How to get IDs:
  WB (nm_id):    open any WB card, e.g. wildberries.ru/catalog/114805666/detail.aspx
                 → nm_id = 114805666
  Ozon (item_id): open any Ozon product, e.g. ozon.ru/product/name-123456789/
                 → item_id = 123456789
  Lenta:         open lenta.com product page, find numeric article in URL or page source
  Samokat:       open samokat.ru product page, find numeric ID in URL
"""

import asyncio
import sys
import os
from dataclasses import asdict
from typing import Any

# Add collector app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "collector"))

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURE YOUR TEST PRODUCTS HERE
# ─────────────────────────────────────────────────────────────────────────────
TEST_PRODUCTS = {
    "Wildberries": "114805666",   # ← вставь свой nm_id с WB
    "Ozon":        "1234567890",  # ← вставь свой item_id с Ozon
    "Lenta":       "100012345",   # ← вставь свой ID с Lenta
    "Самокат":     "50001234",    # ← вставь свой ID с Самоката
}
# ─────────────────────────────────────────────────────────────────────────────


def _no_proxy_rotator():
    """Empty proxy rotator — direct connection, no proxy."""
    from app.core.proxy import ProxyRotator
    return ProxyRotator([])


def _print_header(platform: str, product_id: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {platform}  |  product_id={product_id}")
    print(f"{'='*60}")


def _print_result(label: str, data: Any) -> None:
    print(f"\n  [{label}]")
    if isinstance(data, list):
        for i, item in enumerate(data[:3]):
            print(f"    [{i}] {asdict(item) if hasattr(item, '__dataclass_fields__') else item}")
        if len(data) > 3:
            print(f"    ... and {len(data) - 3} more")
    elif hasattr(data, '__dataclass_fields__'):
        for k, v in asdict(data).items():
            val_str = str(v)[:120] + "…" if len(str(v)) > 120 else str(v)
            print(f"    {k}: {val_str}")
    else:
        print(f"    {data}")


def _print_error(label: str, exc: Exception) -> None:
    code = getattr(exc, "code", type(exc).__name__)
    msg = getattr(exc, "message", str(exc))[:200]
    print(f"\n  [{label}]  ❌ {code}: {msg}")


async def test_wildberries(product_id: str) -> None:
    _print_header("Wildberries", product_id)
    from app.scrapers.wildberries import WildberriesScraper
    scraper = WildberriesScraper(_no_proxy_rotator())
    for method, label in [
        (scraper.collect_content, "content"),
        (scraper.collect_price, "price"),
        (scraper.collect_stock, "stock"),
    ]:
        try:
            result = await method(product_id)
            _print_result(label, result)
        except Exception as exc:
            _print_error(label, exc)
    try:
        reviews = await scraper.collect_reviews(product_id, take=3)
        _print_result("reviews", reviews)
    except Exception as exc:
        _print_error("reviews", exc)


async def test_ozon(product_id: str) -> None:
    _print_header("Ozon", product_id)
    from app.scrapers.ozon import OzonScraper
    scraper = OzonScraper(_no_proxy_rotator())
    for method, label in [
        (scraper.collect_content, "content"),
        (scraper.collect_price, "price"),
        (scraper.collect_stock, "stock"),
    ]:
        try:
            result = await method(product_id)
            _print_result(label, result)
        except Exception as exc:
            _print_error(label, exc)
    try:
        reviews = await scraper.collect_reviews(product_id, take=3)
        _print_result("reviews", reviews)
    except Exception as exc:
        _print_error("reviews", exc)


async def test_lenta(product_id: str) -> None:
    _print_header("Lenta", product_id)
    print("  ℹ️  Lenta is configured as scraper_mode='playwright' — L1 httpx may be blocked by QRATOR")
    from app.scrapers.lenta import LentaScraper
    scraper = LentaScraper(_no_proxy_rotator())
    for method, label in [
        (scraper.collect_content, "content"),
        (scraper.collect_price, "price"),
        (scraper.collect_stock, "stock"),
    ]:
        try:
            result = await method(product_id)
            _print_result(label, result)
        except Exception as exc:
            _print_error(label, exc)
    try:
        reviews = await scraper.collect_reviews(product_id, take=3)
        _print_result("reviews", reviews)
    except Exception as exc:
        _print_error("reviews", exc)


async def test_samocat(product_id: str) -> None:
    _print_header("Самокат", product_id)
    print("  ℹ️  Самокат — full SPA, geo-gated. L1 endpoint unverified (api.samokat.ru/v2).")
    print("      If blocked → in prod fallback to L2 Playwright (needs delivery address session)")
    from app.scrapers.samocat import SamokatScraper
    scraper = SamokatScraper(_no_proxy_rotator())
    for method, label in [
        (scraper.collect_content, "content"),
        (scraper.collect_price, "price"),
        (scraper.collect_stock, "stock"),
    ]:
        try:
            result = await method(product_id)
            _print_result(label, result)
        except Exception as exc:
            _print_error(label, exc)
    try:
        reviews = await scraper.collect_reviews(product_id, take=3)
        _print_result("reviews", reviews)
    except Exception as exc:
        _print_error("reviews", exc)


async def main() -> None:
    print("\n🧪 CAT Scraper — local test (L1 httpx, no proxy, no Docker needed)")
    print("   Edit TEST_PRODUCTS at top of script to use your own product IDs\n")

    tasks = [
        test_wildberries(TEST_PRODUCTS["Wildberries"]),
        test_ozon(TEST_PRODUCTS["Ozon"]),
        test_lenta(TEST_PRODUCTS["Lenta"]),
        test_samocat(TEST_PRODUCTS["Самокат"]),
    ]

    # Run platforms in parallel (each has its own rate limiter)
    results = await asyncio.gather(*tasks, return_exceptions=True)

    print(f"\n{'='*60}")
    print("  DONE")
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            print(f"  Platform {i}: unexpected crash — {res}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
