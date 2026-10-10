"""Run the Telegram bot from your own computer by long polling (no public URL or webhook needed).

    python scripts/run_telegram.py

Needs TELEGRAM_BOT_TOKEN in .env / local.env. Uses the same repository (local or Supabase) and the same advisor as the API.
Stop with Ctrl+C. If you later deploy the API publicly, switch to the webhook (see greenghar/bot/telegram.py)."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from greenghar.api.deps import get_advisor, get_repo  # noqa: E402
from greenghar.bot.telegram import TelegramBot  # noqa: E402


def main() -> int:
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not tok:
        print("TELEGRAM_BOT_TOKEN is not set (.env / local.env).")
        return 1
    api = f"https://api.telegram.org/bot{tok}"
    me = httpx.get(f"{api}/getMe", timeout=15).json()
    if not me.get("ok"):
        print("Telegram rejected the token:", me.get("description"))
        return 1
    print(f"Bot @{me['result']['username']} is running (polling). Ctrl+C to stop.")
    httpx.post(f"{api}/deleteWebhook", json={"drop_pending_updates": False}, timeout=15)  # polling and webhooks are exclusive
    bot = TelegramBot(get_repo(), get_advisor())
    offset = 0
    while True:
        try:
            r = httpx.get(f"{api}/getUpdates", params={"timeout": 30, "offset": offset}, timeout=45).json()
            for u in r.get("result", []):
                offset = u["update_id"] + 1
                try:
                    bot.handle(u)
                except Exception as e:  # one bad update must not stop the bot
                    print("update failed:", repr(e))
        except KeyboardInterrupt:
            return 0
        except httpx.HTTPError as e:
            print("network:", e)
            time.sleep(3)


if __name__ == "__main__":
    sys.exit(main())
