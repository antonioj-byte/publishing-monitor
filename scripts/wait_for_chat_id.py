#!/usr/bin/env python3
"""Wait for you to message the bot, then print your chat ID."""

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import settings, PROJECT_ROOT


def tg(token: str, method: str, **params) -> dict:
    base = f"https://api.telegram.org/bot{token}/{method}"
    if params:
        q = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in params.items())
        url = f"{base}?{q}"
    else:
        url = base
    with urllib.request.urlopen(url, timeout=20) as resp:
        return json.loads(resp.read().decode())


def extract_chats(updates: list) -> list[tuple[int, str, str]]:
    found: list[tuple[int, str, str]] = []
    seen: set[int] = set()
    for upd in updates:
        msg = upd.get("message") or upd.get("edited_message")
        if not msg:
            continue
        chat = msg["chat"]
        cid = chat["id"]
        if cid in seen:
            continue
        seen.add(cid)
        name = chat.get("first_name") or chat.get("username") or chat.get("title") or "?"
        kind = chat.get("type", "?")
        found.append((cid, name, kind))
    return found


def main() -> None:
    token = (settings.telegram_bot_token or "").strip()
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN vacío.")
        print(f"   Edita y guarda: {PROJECT_ROOT / '.env'}")
        sys.exit(1)

    try:
        me = tg(token, "getMe")
    except urllib.error.HTTPError as e:
        print(f"❌ Token rechazado por Telegram (HTTP {e.code}).")
        print("   Genera uno nuevo en @BotFather → /mybots → API Token")
        sys.exit(1)

    bot = me["result"]
    username = bot.get("username", "?")
    print(f"✅ Bot conectado: @{username}\n")

    tg(token, "deleteWebhook")

    # Mensajes previos
    data = tg(token, "getUpdates", limit=50)
    chats = extract_chats(data.get("result", []))
    if chats:
        print("Chats encontrados en el historial:\n")
        for cid, name, kind in chats:
            print(f"  TELEGRAM_CHAT_ID={cid}   ({name}, {kind})")
        print("\nCopia el ID en .env → python3 scripts/test_telegram.py")
        return

    print("No hay mensajes todavía.\n")
    print("👉 AHORA MISMO, en el móvil o Telegram desktop:")
    print(f"   1. Busca @{username}")
    print("   2. Pulsa START (o escribe /start)")
    print("   3. No cierres este terminal — espero 90 segundos…\n")

    offset = 0
    deadline = time.time() + 90
    while time.time() < deadline:
        remaining = int(deadline - time.time())
        print(f"\r   Esperando… {remaining}s ", end="", flush=True)
        try:
            data = tg(token, "getUpdates", timeout=30, offset=offset)
        except urllib.error.HTTPError:
            time.sleep(2)
            continue
        for upd in data.get("result", []):
            offset = max(offset, upd["update_id"] + 1)
        chats = extract_chats(data.get("result", []))
        if chats:
            print("\n\n✅ ¡Recibido!\n")
            for cid, name, kind in chats:
                print(f"  TELEGRAM_CHAT_ID={cid}   ({name}, {kind})")
            print("\nPega esa línea en .env y guarda.")
            return
        time.sleep(2)

    print("\n\n❌ Tiempo agotado. No llegó ningún mensaje.")
    print(f"\nComprueba que escribiste a @{username} (no a otro bot).")
    print("Luego vuelve a ejecutar: python3 scripts/wait_for_chat_id.py")


if __name__ == "__main__":
    main()
