#!/usr/bin/env python3
"""Fetch Telegram chat ID from recent bot messages."""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import settings, PROJECT_ROOT


def tg_api(token: str, method: str, params: dict | None = None) -> dict:
    base = f"https://api.telegram.org/bot{token}/{method}"
    if params:
        query = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in params.items())
        url = f"{base}?{query}"
    else:
        url = base
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    token = (settings.telegram_bot_token or "").strip()
    if not token:
        print("Error: TELEGRAM_BOT_TOKEN vacío en .env")
        print(f"Archivo esperado: {PROJECT_ROOT / '.env'}")
        print("\nAñade una línea como:")
        print("TELEGRAM_BOT_TOKEN=123456789:ABC...")
        sys.exit(1)

    print(f"Leyendo .env desde: {PROJECT_ROOT / '.env'}")

    try:
        me = tg_api(token, "getMe")
    except urllib.error.HTTPError as exc:
        print(f"\nToken inválido o revocado (HTTP {exc.code}).")
        print("Genera uno nuevo en @BotFather → /mybots → tu bot → API Token")
        sys.exit(1)

    if not me.get("ok"):
        print("Error getMe:", me)
        sys.exit(1)

    bot = me["result"]
    username = bot.get("username", "?")
    print(f"Bot OK: @{username}\n")

    # Webhook activo impide ver mensajes con getUpdates
    try:
        wh = tg_api(token, "getWebhookInfo")
        if wh.get("result", {}).get("url"):
            print("Webhook activo detectado — eliminando para poder leer mensajes…")
            tg_api(token, "deleteWebhook")
    except urllib.error.HTTPError:
        pass

    try:
        data = tg_api(token, "getUpdates", {"limit": 20})
    except urllib.error.HTTPError as exc:
        print(f"Error HTTP getUpdates: {exc}")
        sys.exit(1)

    if not data.get("ok"):
        print("Respuesta inesperada:", data)
        sys.exit(1)

    updates = data.get("result", [])
    if not updates:
        print("No hay mensajes en el historial del bot.\n")
        print("Haz EXACTAMENTE esto:")
        print(f"  1. Abre Telegram (móvil o desktop)")
        print(f"  2. Busca @{username}")
        print("  3. Pulsa START o escribe: /start")
        print("  4. Espera 2 segundos y vuelve a ejecutar:")
        print("     python3 scripts/get_telegram_chat_id.py")
        print("\nSi el bot no aparece, comprueba el username en @BotFather → /mybots")
        sys.exit(1)

    seen: set[int] = set()
    print("Chats encontrados:\n")
    for upd in reversed(updates):
        msg = upd.get("message") or upd.get("edited_message") or upd.get("channel_post")
        if not msg:
            continue
        chat = msg["chat"]
        chat_id = chat["id"]
        if chat_id in seen:
            continue
        seen.add(chat_id)
        name = (
            chat.get("username")
            or chat.get("first_name")
            or chat.get("title")
            or "?"
        )
        kind = chat.get("type", "private")
        print(f"  TELEGRAM_CHAT_ID={chat_id}  ({name}, {kind})")

    print("\nCopia esa línea en tu .env y guarda.")
    print("Luego: python3 scripts/test_telegram.py")


if __name__ == "__main__":
    main()
