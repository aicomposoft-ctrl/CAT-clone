"""
Тест прокси FineProxy.
Использование:
  1. Получить список прокси из кабинета FineProxy (кнопка TXT)
  2. Запустить: python3 test_proxy.py

  Или передать URL списка как аргумент:
  python3 test_proxy.py "https://fineproxy.org/api/...txt"

  Или задать вручную в MANUAL_PROXIES ниже.
"""
import asyncio
import sys
import httpx

LOGIN = 'SuperVIPNXW4MFF'
PASS  = 'XyEu004D'

# ── Вставьте прокси вручную если API не работает ────────────────────────────
# Формат: "ip:port" (без логина — passwordless при whitelist IP)
# или "ip:port:login:pass" для авторизации
MANUAL_PROXIES: list[str] = [
    # '188.x.x.x:8085',
    # '188.x.x.x:8085',
]
# ────────────────────────────────────────────────────────────────────────────

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'ru-RU,ru;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.9',
}

TEST_TARGETS = [
    ('IP check (ipify)',   'https://api.ipify.org',     False),
    ('WB main',            'https://www.wildberries.ru', False),
    ('WB card API',        'https://card.wb.ru/cards/v2/detail?nm=205069072&curr=rub&dest=-1257786', False),
    ('Ozon',               'https://www.ozon.ru',        False),
    ('Samocat',            'https://samokat.ru',         False),
    ('Lenta',              'https://lenta.com',          False),
]


def build_proxy_url(proxy_str: str) -> str:
    parts = proxy_str.strip().split(':')
    if len(parts) == 2:
        # Passwordless: ip:port
        return f'http://{parts[0]}:{parts[1]}'
    elif len(parts) == 4:
        # With auth: ip:port:login:pass
        return f'http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}'
    else:
        return f'http://{proxy_str}'


async def fetch_proxy_list(url: str) -> list[str]:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
        r = await c.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        lines = [ln.strip() for ln in r.text.splitlines() if ln.strip() and not ln.startswith('{')]
        return lines


async def test_proxy(proxy_str: str) -> dict:
    proxy_url = build_proxy_url(proxy_str)
    results = {}
    print(f'\n{"="*50}')
    print(f'Proxy: {proxy_str}')
    print(f'{"="*50}')

    for name, url, _ in TEST_TARGETS:
        try:
            async with httpx.AsyncClient(
                proxy=proxy_url,
                headers=HEADERS,
                timeout=httpx.Timeout(12.0),
                follow_redirects=True,
            ) as client:
                r = await client.get(url)
                extra = f' (exit_ip={r.text.strip()[:20]})' if name.startswith('IP') else ''
                print(f'  [{r.status_code:3d}] {name}{extra}')
                results[name] = r.status_code
        except Exception as e:
            short_err = str(e)[:60]
            print(f'  [ERR] {name}: {type(e).__name__}: {short_err}')
            results[name] = 0
    return results


async def main():
    proxies: list[str] = []

    # 1. From command-line URL
    if len(sys.argv) > 1:
        print(f'Fetching proxy list from: {sys.argv[1][:80]}...')
        proxies = await fetch_proxy_list(sys.argv[1])
        print(f'Got {len(proxies)} proxies')

    # 2. From API (auto)
    if not proxies:
        api_url = f'https://fineproxy.org/api/getproxy/?action=getproxy&login={LOGIN}&password={PASS}&type=http&format=txt'
        print('Trying auto API fetch...')
        proxies = await fetch_proxy_list(api_url)
        if proxies:
            print(f'Got {len(proxies)} proxies from API')

    # 3. From manual list
    if not proxies and MANUAL_PROXIES:
        proxies = MANUAL_PROXIES
        print(f'Using {len(proxies)} manually configured proxies')

    if not proxies:
        print('\n⚠️  No proxies available.')
        print('Options:')
        print('  A) Run: python3 test_proxy.py "<TXT_URL_FROM_FINEPROXY_DASHBOARD>"')
        print('  B) Edit MANUAL_PROXIES in this file')
        print('  C) Paste proxy IPs:port in the chat')
        return

    # Test first 3 proxies
    summary = []
    for proxy in proxies[:3]:
        res = await test_proxy(proxy)
        ok = sum(1 for v in res.values() if 200 <= v < 400)
        total = len(res)
        summary.append((proxy, ok, total))

    print(f'\n{"="*50}')
    print('SUMMARY')
    print(f'{"="*50}')
    for proxy, ok, total in summary:
        icon = '✅' if ok >= total * 0.5 else '⚠️' if ok > 0 else '❌'
        print(f'  {icon} {proxy}: {ok}/{total} targets passed')


if __name__ == '__main__':
    asyncio.run(main())
