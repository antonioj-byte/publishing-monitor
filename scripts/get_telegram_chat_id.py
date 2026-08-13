#!/usr/bin/env python3
"""Fetch Telegram chat ID from recent bot messages."""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import settings


def main() -> None:
    token = settings.telegram_bot_token
    if not token:
        print("Error: TELEGRAM_BOT_TOKEN no está en .env")
        print("1. Crea el bot con @BotFather")
        print("2. Añade TELEGRAM_BOT_TOKEN=... en .env")
        sys.exit(1)

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        print(f"Error HTTP de Telegram: {exc}")
        sys.exit(1)

    if not data.get("ok"):
        print("Respuesta inesperada:", data)
        sys.exit(1)

    updates = data.get("result", [])
    if not updates:
        print("No hay mensajes todavía.")
        print("Envía /start a tu bot en Telegram y vuelve a ejecutar este script.")
        sys.exit(1)

    seen: set[int] = set()
    print("Chats encontrados:\n")
    for upd in reversed(updates):
        msg = upd.get("message") or upd.get("edited_message")
        if not msg:
            continue
        chat = msg["chat"]
        chat_id = chat["id"]
        if chat_id in seen:
            continue
        seen.add(chat_id)
        name = chat.get("username") or chat.get("first_name") or chat.get("title") or "?"
        print(f"  TELEGRAM_CHAT_ID={chat_id}  ({name})")

    print("\nCopia el ID que quieras usar en tu archivo .env")


if __name__ == "__main__":
    main()
