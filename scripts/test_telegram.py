#!/usr/bin/env python3
"""Verify Telegram bot token and send a test message."""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import settings


def api(method: str, payload: dict | None = None) -> dict:
    token = settings.telegram_bot_token
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN no configurado en .env")

    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    me = api("getMe")
    if not me.get("ok"):
        print("Error getMe:", me)
        sys.exit(1)

    bot = me["result"]
    print(f"Bot OK: @{bot.get('username')} ({bot.get('first_name')})")

    chat_id = settings.telegram_chat_id
    if not chat_id:
        print("\nTELEGRAM_CHAT_ID vacío.")
        print("Envía /start al bot y ejecuta: python3 scripts/get_telegram_chat_id.py")
        sys.exit(1)

    msg = api(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": "✅ Bot editorial conectado. Prueba /informe o /informe_hoy.",
        },
    )
    if msg.get("ok"):
        print(f"Mensaje de prueba enviado al chat {chat_id}")
    else:
        print("Error sendMessage:", msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
