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

from ai.classify import active_model, active_provider, verify_classify_api
from bot.config import settings
from bot.heartbeat import HEARTBEAT_PATH, read_heartbeat


def _bot_process_running() -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-f", r"python.*bot\.main"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except OSError:
        return False


def _print_start_hint() -> None:
    print("\n→ Para arrancar el bot:")
    if sys.platform == "darwin":
        print("  ./deploy/install-launchd.sh          # instala y deja activo en segundo plano")
        print("  ./deploy/reset-and-launch-mac.sh     # actualiza y reinicia")
    else:
        print("  ./deploy/start-bot.sh                # arranque manual (carga .env)")
        print("  ./deploy/install-systemd.sh          # Linux con systemd")


def main() -> None:
    print("=== Estado del bot Telegram ===\n")

    token = settings.telegram_bot_token.strip()
    chat_id = settings.telegram_chat_id.strip()
    print(f"Sistema: {sys.platform} ({'macOS' if sys.platform == 'darwin' else 'no macOS'})")
    print(f"TELEGRAM_CHAT_ID configurado: {chat_id or 'NO'}")
    print(f"Base de datos: {settings.database_path}")
    print(f"Heartbeat: {HEARTBEAT_PATH}")
    print(f"Proceso bot.main: {'sí' if _bot_process_running() else 'no'}")
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

    provider = active_provider()
    print(f"Clasificación: {provider} ({active_model()})")

    if settings.has_classify_api():
        try:
            verify_classify_api()
            key_label = "GOOGLE_API_KEY" if provider == "gemini" else "ANTHROPIC_API_KEY"
            print(f"{key_label}: OK (traducción y resúmenes en castellano)")
        except Exception as exc:
            err = str(exc)
            if provider == "gemini":
                print(f"GOOGLE_API_KEY: error ({err[:80]})")
            elif "401" in err:
                print("ANTHROPIC_API_KEY: INVÁLIDA — renueva en console.anthropic.com")
            else:
                print(f"ANTHROPIC_API_KEY: error ({err[:60]})")
    else:
        key_name = "GOOGLE_API_KEY" if provider == "gemini" else "ANTHROPIC_API_KEY"
        print(f"{key_name}: NO configurada — resúmenes sin traducir")

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
        _print_start_hint()

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
    elif sys.platform != "darwin" and not hb:
        print(
            "\nNota: si quieres el bot en tu Mac, ejecuta estos comandos "
            "en Terminal.app (no en Cursor cloud)."
        )

    print("\nComandos útiles:")
    if sys.platform == "darwin":
        print("  ./deploy/reset-and-launch-mac.sh --no-pull")
    print("  tail -f data/bot.log")
    print("  python3 scripts/watchdog_bot.py")


if __name__ == "__main__":
    main()
