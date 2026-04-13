#!/usr/bin/env python3
"""
Local scraper smoke-test — 4 platforms, 1 product each, no Docker/DB/Redis required.

Strategy per platform:
  Wildberries  → L1 httpx  (card.wb.ru public API)
  Ozon         → L1 httpx  (ozon.ru composer-api.bx)
  Lenta        → L1 httpx  (lenta.com/api/v1, tries both legacy + new domains)
  Самокат      → L2 Playwright (geo-init Moscow → intercept API calls)

Setup:
    cd /workspaces/CAT-clone/services/collector
    pip install httpx==0.27.0 requests cryptography
    pip install playwright && playwright install chromium   # for Самокат only

Run:
    PYTHONPATH=/workspaces/CAT-clone/services/collector \\
    python /workspaces/CAT-clone/scripts/test_scrapers_local.py

How to find product IDs / URLs:
  Wildberries:  wildberries.ru/catalog/114805666/detail.aspx  → nm_id = 114805666
  Ozon:         ozon.ru/product/name-123456789/               → item_id = 123456789
  Lenta:        lenta.com/catalog/cat/product-name-100012345  → id = 100012345
  Самокат:      samokat.ru/product/name-12345/                → full URL needed for L2
"""

import asyncio
import sys
import os
import time
from dataclasses import asdict
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "collector"))

# ─────────────────────────────────────────────────────────────────────────────
#  EDIT THESE — вставь свои ID и URL
# ─────────────────────────────────────────────────────────────────────────────

WB_NM_ID      = "114805666"          # nm_id из URL карточки WB
OZON_ITEM_ID  = "1234567890"         # item_id из URL карточки Ozon
LENTA_ID      = "100012345"          # ID из URL страницы продукта Лента
SAMOCAT_URL   = "https://samokat.ru/product/chaj-lipton-yellow-label-25p-50g-12345/"
                                     # Полный URL карточки на Самокате

# ─────────────────────────────────────────────────────────────────────────────


def _no_proxy():
    from app.core.proxy import ProxyRotator
    return ProxyRotator([])          # без прокси — прямое подключение


def _sep(platform: str, product_id: str) -> None:
    print(f"\n{'━'*60}")
    print(f"  {platform}  ·  {product_id}")
    print(f"{'━'*60}")


def _ok(label: str, data: Any) -> None:
    print(f"\n  ✅ [{label}]")
    if isinstance(data, list):
        for i, item in enumerate(data[:2]):
            d = asdict(item) if hasattr(item, "__dataclass_fields__") else item
            print(f"     [{i}] {_short(d)}")
        if len(data) > 2:
            print(f"     … ещё {len(data)-2}")
    elif hasattr(data, "__dataclass_fields__"):
        for k, v in asdict(data).items():
            print(f"     {k}: {_short(v)}")
    else:
        print(f"     {_short(data)}")


def _err(label: str, exc: Exception) -> None:
    code = getattr(exc, "code", type(exc).__name__)
    msg  = getattr(exc, "message", str(exc))[:160]
    print(f"\n  ❌ [{label}]  {code}: {msg}")


def _short(v: Any) -> str:
    s = str(v)
    return s[:100] + "…" if len(s) > 100 else s


# ─────────────────────────────────────────────────────────────────────────────
#  Wildberries — L1 httpx
# ─────────────────────────────────────────────────────────────────────────────

async def test_wb() -> None:
    _sep("Wildberries", WB_NM_ID)
    from app.scrapers.wildberries import WildberriesScraper
    sc = WildberriesScraper(_no_proxy())
    for fn, lbl in [
        (sc.collect_content, "content"),
        (sc.collect_price,   "price"),
        (sc.collect_stock,   "stock"),
    ]:
        try:
            _ok(lbl, await fn(WB_NM_ID))
        except Exception as e:
            _err(lbl, e)
    try:
        _ok("reviews (3)", await sc.collect_reviews(WB_NM_ID, take=3))
    except Exception as e:
        _err("reviews", e)


# ─────────────────────────────────────────────────────────────────────────────
#  Ozon — L1 httpx
# ─────────────────────────────────────────────────────────────────────────────

async def test_ozon() -> None:
    _sep("Ozon", OZON_ITEM_ID)
    from app.scrapers.ozon import OzonScraper
    sc = OzonScraper(_no_proxy())
    for fn, lbl in [
        (sc.collect_content, "content"),
        (sc.collect_price,   "price"),
        (sc.collect_stock,   "stock"),
    ]:
        try:
            _ok(lbl, await fn(OZON_ITEM_ID))
        except Exception as e:
            _err(lbl, e)
    try:
        _ok("reviews (3)", await sc.collect_reviews(OZON_ITEM_ID, take=3))
    except Exception as e:
        _err("reviews", e)


# ─────────────────────────────────────────────────────────────────────────────
#  Lenta — L1 httpx  (QRATOR, мобильный UA)
# ─────────────────────────────────────────────────────────────────────────────

async def test_lenta() -> None:
    _sep("Lenta", LENTA_ID)
    print("  ℹ️  L1 httpx с LentaApp User-Agent. Если QRATOR блокирует → увидишь API_UNAVAILABLE")
    print("      → В проде автоматически пойдёт в L2 Playwright")
    from app.scrapers.lenta import LentaScraper
    sc = LentaScraper(_no_proxy())
    for fn, lbl in [
        (sc.collect_content, "content"),
        (sc.collect_price,   "price"),
        (sc.collect_stock,   "stock"),
    ]:
        try:
            _ok(lbl, await fn(LENTA_ID))
        except Exception as e:
            _err(lbl, e)
    try:
        _ok("reviews (3)", await sc.collect_reviews(LENTA_ID, take=3))
    except Exception as e:
        _err("reviews", e)


# ─────────────────────────────────────────────────────────────────────────────
#  Самокат — L2 Playwright  (geo-init Москва → перехват API → данные)
# ─────────────────────────────────────────────────────────────────────────────

async def test_samocat() -> None:
    _sep("Самокат (Playwright)", SAMOCAT_URL)
    print("  ℹ️  Гео-инициализация: Москва, Тверская (55.7558, 37.6173)")
    print("      → Открываем samokat.ru, ждём выбора зоны, затем переходим на карточку")

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("\n  ⚠️  playwright не установлен. Запусти:")
        print("      pip install playwright && playwright install chromium")
        return

    from app.core.base_scraper import DataType, ScraperError
    from app.core.sanitize import sanitize
    from decimal import Decimal

    MOSCOW_GEO = {"latitude": 55.7558, "longitude": 37.6173, "accuracy": 10}
    GEO_INIT_URL = "https://samokat.ru"
    GEO_WAIT_S = 3.0

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="ru-RU",
            geolocation=MOSCOW_GEO,
            permissions=["geolocation"],
            extra_http_headers={"Accept-Language": "ru-RU,ru;q=0.9"},
        )
        page = await context.new_page()

        # Step 1: geo-init — открываем главную Самоката с геолокацией Москвы
        intercepted: list[dict] = []

        async def _on_resp(response):
            try:
                ct = response.headers.get("content-type", "")
                if response.status == 200 and "application/json" in ct:
                    body = await response.json()
                    intercepted.append({"url": response.url, "body": body})
            except Exception:
                pass

        page.on("response", _on_resp)

        print(f"\n  → Гео-инит: {GEO_INIT_URL}")
        try:
            await page.goto(GEO_INIT_URL, wait_until="networkidle", timeout=30_000)
            print(f"  → Ждём {GEO_WAIT_S}s чтобы JS определил зону доставки…")
            await asyncio.sleep(GEO_WAIT_S)
            intercepted.clear()  # очищаем — нам нужны только данные с карточки
            print(f"  → Зона установлена. URL страницы: {page.url}")
        except Exception as exc:
            print(f"  ⚠️  Гео-инит: {exc} — продолжаем")

        # Step 2: переходим на карточку товара
        print(f"\n  → Карточка: {SAMOCAT_URL}")
        try:
            await page.goto(SAMOCAT_URL, wait_until="networkidle", timeout=30_000)
        except Exception as exc:
            print(f"  ❌ Загрузка карточки: {exc}")
            await context.close()
            await browser.close()
            return

        title = (await page.title()).strip()
        print(f"  → Заголовок страницы: {title!r}")

        # Step 3: Распарсить перехваченные XHR-ответы
        print(f"\n  → Перехвачено XHR-ответов: {len(intercepted)}")

        content_found = price_found = stock_found = False
        for r in intercepted:
            body = r.get("body", {})
            url_hint = r["url"][:80]

            # Ищем данные о товаре
            if not content_found:
                name = _deep_find(body, ("name", "title", "productName"))
                if name:
                    print(f"\n  ✅ [content from XHR: {url_hint}]")
                    print(f"     name: {str(name)[:100]}")
                    desc = _deep_find(body, ("description", "desc", "shortDescription"))
                    if desc:
                        print(f"     description: {str(desc)[:100]}")
                    comp = _deep_find(body, ("composition", "ingredients", "consist"))
                    if comp:
                        print(f"     composition: {str(comp)[:100]}")
                    img = _deep_find(body, ("imageUrl", "image", "photo", "mainPhoto"))
                    if img:
                        print(f"     image_url: {str(img)[:80]}")
                    content_found = True

            if not price_found:
                price = _deep_find(body, ("price", "salePriceU", "finalPrice", "currentPrice"))
                if price is not None:
                    print(f"\n  ✅ [price from XHR: {url_hint}]")
                    p = Decimal(str(price))
                    if p > 100000:
                        p = p / 100  # kopeks → rubles
                    print(f"     price: {p:.2f} ₽")
                    orig = _deep_find(body, ("originalPrice", "oldPrice", "basePrice", "priceU"))
                    if orig:
                        op_ = Decimal(str(orig))
                        if op_ > 100000:
                            op_ = op_ / 100
                        print(f"     original_price: {op_:.2f} ₽")
                    price_found = True

            if not stock_found:
                qty = _deep_find(body, ("qty", "quantity", "stock", "totalQty", "remains"))
                in_stock = _deep_find(body, ("inStock", "in_stock", "available", "isAvailable"))
                if qty is not None or in_stock is not None:
                    print(f"\n  ✅ [stock from XHR: {url_hint}]")
                    print(f"     in_stock: {bool(in_stock)}")
                    print(f"     qty: {qty}")
                    stock_found = True

        if not (content_found or price_found or stock_found):
            # Fallback: попробуем DOM
            print("\n  ⚠️  XHR-данные не распознаны — пробуем DOM...")
            try:
                # Ищем цену в DOM
                for sel in ("span[data-test='price']", ".price", "[class*='price']",
                            "[class*='Price']", "span[class*='cost']"):
                    el = await page.query_selector(sel)
                    if el:
                        text = await el.text_content()
                        if text and any(c.isdigit() for c in text):
                            print(f"  ✅ [price DOM {sel}]: {text.strip()}")
                            break

                # Ищем название
                for sel in ("h1", "[class*='title']", "[class*='Title']", "[class*='name']"):
                    el = await page.query_selector(sel)
                    if el:
                        text = await el.text_content()
                        if text and len(text.strip()) > 3:
                            print(f"  ✅ [title DOM {sel}]: {text.strip()[:80]}")
                            break
            except Exception as exc:
                print(f"  ❌ DOM fallback: {exc}")

            print("\n  📸 Сохраняем скриншот для диагностики: /tmp/samocat_debug.png")
            try:
                await page.screenshot(path="/tmp/samocat_debug.png", full_page=True)
                print("     Открой файл чтобы увидеть что показал Самокат")
            except Exception:
                pass

        await context.close()
        await browser.close()


def _deep_find(obj: Any, keys: tuple, depth: int = 0) -> Any:
    """Рекурсивный поиск первого совпадающего ключа в JSON-структуре."""
    if depth > 5:
        return None
    if isinstance(obj, dict):
        for k in keys:
            if k in obj and obj[k] is not None:
                return obj[k]
        for v in obj.values():
            if isinstance(v, (dict, list)):
                r = _deep_find(v, keys, depth + 1)
                if r is not None:
                    return r
    elif isinstance(obj, list):
        for item in obj[:5]:
            r = _deep_find(item, keys, depth + 1)
            if r is not None:
                return r
    return None


# ─────────────────────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────────────────────

async def main() -> None:
    print("━" * 60)
    print("  CAT Scraper — локальный тест  (4 площадки, 1 товар)")
    print("━" * 60)
    print("\n  ⚙️  Перед запуском замени ID/URL в начале скрипта!")
    print("      WB_NM_ID, OZON_ITEM_ID, LENTA_ID, SAMOCAT_URL\n")

    t0 = time.monotonic()

    # WB и Ozon — параллельно (httpx)
    await asyncio.gather(test_wb(), test_ozon(), return_exceptions=True)

    # Лента — отдельно (может блокировать QRATOR)
    await test_lenta()

    # Самокат — последним (Playwright, тяжелее)
    await test_samocat()

    elapsed = time.monotonic() - t0
    print(f"\n{'━'*60}")
    print(f"  Готово за {elapsed:.1f}s")
    print(f"{'━'*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
