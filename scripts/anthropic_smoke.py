import asyncio
import os

import anthropic


async def main() -> None:
    client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    try:
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=16,
            messages=[{"role": "user", "content": "ping"}],
        )
        print("OK", bool(resp.content))
    except Exception as exc:  # noqa: BLE001
        print("ERR", exc)


if __name__ == "__main__":
    asyncio.run(main())
