# ADR-007: Playwright + Scrapy для скрапинга

**Дата:** 2026-03-01  
**Статус:** Accepted  
**Авторы:** CAT Team

---

## Контекст

CAT собирает данные с 110+ платформ. Платформы делятся на два типа:
1. **JS-heavy SPA** (Wildberries, Ozon, Самокат) — контент загружается через JavaScript
2. **HTML/JSON API** (Лента, мелкие магазины) — доступны через HTTP без JS

Дополнительно: все крупные маркетплейсы имеют anti-bot защиту (Qrator, wbaas, Cloudflare).

## Рассматриваемые варианты

| Инструмент | JS Support | Скорость | Anti-bot bypass | Сложность |
|-----------|-----------|----------|-----------------|-----------|
| requests + BeautifulSoup | ❌ | Высокая | ❌ | Низкая |
| Scrapy | ❌ (без Splash) | Высокая | Частично | Средняя |
| Selenium | ✅ | Низкая | Частично | Средняя |
| **Playwright (выбран)** | ✅ | Средняя | Лучший | Средняя |
| **Scrapy + Playwright (выбран)** | ✅ (через middleware) | Высокая | Хороший | Средняя |

## Решение

**Двухрежимный подход:**

- **Playwright** (`mcr.microsoft.com/playwright/python` Docker image) — для JS-heavy платформ (WB, Ozon, Samocat). Chromium headless, имитация браузерного поведения, решение JS-challenges.
- **Scrapy** — для платформ с открытым JSON API или простым HTML. Высокая пропускная способность.

```python
class BaseScraper:
    rate_limit: float = 1.0  # req/sec — обязательно соблюдать
    use_playwright: bool = False  # переопределяется в подклассах

    async def collect(self, sku: SKU) -> ScrapedData:
        if self.use_playwright:
            return await self._collect_playwright(sku)
        return await self._collect_scrapy(sku)
```

**Proxy rotation:** FineProxy (RU datacenter IPs) + ротация User-Agent. Российские резидентские прокси нужны для WB (блокирует датацентровые IP через wbaas).

## Последствия

- **Положительные:** один фреймворк для всех типов платформ, реалистичное поведение браузера обходит большинство anti-bot систем
- **Отрицательные:** Playwright требует `--ipc=host` в Docker и Chromium (~500MB в образе); скорость ниже чем pure HTTP
- **Известная проблема (2026-04-06):** WB wbaas требует решения JS-challenge — curl и простые HTTP-запросы возвращают 498 даже с Russian IP. Только Playwright решает challenge.
