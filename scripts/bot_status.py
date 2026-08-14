#!/usr/bin/env python3
"""Show whether the Telegram bot process and polling look healthy."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import settings
from bot.heartbeat import HEARTBEAT_PATH, read_heartbeat


def main() -> None:
    print("=== Estado del bot Telegram ===\n")

    token = settings.telegram_bot_token.strip()
    chat_id = settings.telegram_chat_id.strip()
    print(f"TELEGRAM_CHAT_ID configurado: {chat_id or 'NO'}")
    print(f"Base de datos: {settings.database_path}")
    print(f"Heartbeat: {HEARTBEAT_PATH}")
    print()

    if token:
        try:
            url = f"https://api.telegram.org/bot{token}/getMe"
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
            if data.get("ok"):
                user = data["result"]
                print(f"Token Telegram: OK (@{user.get('username', '?')})")
            else:
                print(f"Token Telegram: FAIL {data}")
        except Exception as exc:
            print(f"Token Telegram: FAIL {exc}")

        try:
            url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
            with urllib.request.urlopen(url, timeout=10) as response:
                webhook = json.loads(response.read().decode("utf-8")).get("result", {})
            if webhook.get("url"):
                print(f"Webhook activo: SÍ ({webhook['url']}) — bloquea polling")
            else:
                print("Webhook activo: no")
        except Exception as exc:
            print(f"Webhook info: error {exc}")
    else:
        print("Token Telegram: NO configurado")

    hb = read_heartbeat()
    if hb:
        age = time.time() - float(hb.get("epoch", 0))
        print(
            f"Heartbeat: {hb.get('status')} pid={hb.get('pid')} "
            f"hace {age:.0f}s ({hb.get('updated_at')})"
        )
        if age > 180:
            print("⚠️  Heartbeat antiguo — el bot probablemente está colgado o parado")
    else:
        print("Heartbeat: no encontrado — el bot no está corriendo o no arrancó")

    if sys.platform == "darwin":
        uid = subprocess.check_output(["id", "-u"], text=True).strip()
        result = subprocess.run(
            ["launchctl", "print", f"gui/{uid}/com.editorial-bot"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "state =" in line or "pid =" in line or "last exit" in line:
                    print(line.strip())
        else:
            print("LaunchAgent com.editorial-bot: no cargado")
            print("  Instala con: ./deploy/install-launchd.sh")

    print("\nComandos útiles:")
    print("  ./deploy/reset-and-launch-mac.sh --no-pull")
    print("  tail -f data/bot.log")
    print("  python3 scripts/watchdog_bot.py")


if __name__ == "__main__":
    main()
