import asyncio
import os
import re
import sys

from playwright.async_api import async_playwright

URLS = {
    "ozon": "https://www.ozon.ru/product/146804973/",
    "wb": "https://www.wildberries.ru/catalog/844578103/detail.aspx",
    "lenta": "https://lenta.com/product/380973/",
    "samokat": "https://samokat.ru/product/fruktovoe-pyure-agusha-yabloko-i-banan-so-vkusom-pechenya-s-6-mesyatsev-90-g",
}


def _resolve_target(raw: str) -> str:
    value = (raw or "").strip()
    if value in URLS:
        return URLS[value]
    if value.startswith("http://") or value.startswith("https://"):
        return value
    raise SystemExit(f"Unknown target: {value}. Allowed aliases: {', '.join(URLS)} or full URL.")


def _proxy_from_env() -> dict | None:
    url = os.environ.get("SCRAPER_PROXY_URL", "").strip()
    if not url:
        return None
    proxy: dict = {"server": url}
    user = os.environ.get("SCRAPER_PROXY_USER", "").strip()
    password = os.environ.get("SCRAPER_PROXY_PASS", "").strip()
    if user:
        proxy["username"] = user
    if password:
        proxy["password"] = password
    return proxy


async def main(target: str) -> None:
    url = _resolve_target(target)
    proxy = _proxy_from_env()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = await browser.new_context(
            locale="ru-RU",
            proxy=proxy,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            extra_http_headers={"Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8"},
        )
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(3500)

        print("URL:", url)
        print("TITLE:", await page.title())
        print("PAGE_URL:", page.url)
        body = (await page.inner_text("body"))[:1000].replace("\n", " ")
        print("BODY:", body)

        selectors = [
            "h1",
            "meta[property='og:title']",
            "meta[property='og:description']",
            "meta[property='og:image']",
            "meta[itemprop='price']",
            "[itemprop='price']",
        ]
        for sel in selectors:
            try:
                val = await page.eval_on_selector(
                    sel, "el => el.content || el.getAttribute('content') || el.textContent"
                )
            except Exception:
                val = None
            if val:
                print(f"SEL {sel}: {str(val)[:220]}")

        html = await page.content()
        patterns = [
            r'"price"\s*:\s*"?\d+',
            r'"finalPrice"\s*:\s*"?\d+',
            r'"amount"\s*:\s*"?\d+',
            r'\d[\d\s]{1,10}(?:[.,]\d{1,2})?\s*(?:₽|руб)',
        ]
        for pat in patterns:
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                print(f"HTML {pat}: {m.group(0)[:220]}")

        await ctx.close()
        await browser.close()


if __name__ == "__main__":
    target = (sys.argv[1] if len(sys.argv) > 1 else "ozon")
    asyncio.run(main(target))
