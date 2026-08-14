#!/usr/bin/env python3
"""Restart the bot if heartbeat or Telegram API checks fail."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import settings
from bot.heartbeat import read_heartbeat

MAX_HEARTBEAT_AGE_SEC = 180
LABEL = "com.editorial-bot"


def _log(msg: str) -> None:
    print(msg, flush=True)


def _telegram_get_me() -> tuple[bool, str]:
    token = settings.telegram_bot_token.strip()
    if not token:
        return False, "TELEGRAM_BOT_TOKEN vacío"
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        if data.get("ok"):
            username = data.get("result", {}).get("username", "?")
            return True, f"@{username}"
        return False, str(data)[:120]
    except urllib.error.URLError as exc:
        return False, str(exc)[:120]


def _restart_mac() -> None:
    uid = subprocess.check_output(["id", "-u"], text=True).strip()
    target = f"gui/{uid}/{LABEL}"
    subprocess.run(
        ["launchctl", "kickstart", "-k", target],
        check=False,
    )


def _systemd_usable() -> bool:
    if sys.platform == "darwin":
        return False
    for sock in ("/run/systemd/private", "/var/run/systemd/private"):
        if Path(sock).exists():
            break
    else:
        return False
    try:
        subprocess.run(
            ["systemctl", "is-system-running", "--quiet"],
            check=False,
            capture_output=True,
        )
        return True
    except OSError:
        return False


def _restart_linux() -> None:
    if not _systemd_usable():
        _log("[watchdog] systemd no disponible — no se puede reiniciar automáticamente")
        _log("[watchdog] Arranca manualmente: python3 -m bot.main")
        return
    subprocess.run(["systemctl", "restart", "editorial-bot"], check=False)


def main() -> None:
    now = time.time()
    hb = read_heartbeat()
    token_ok, token_detail = _telegram_get_me()

    if not token_ok:
        _log(f"[watchdog] Token Telegram inválido: {token_detail}")
        sys.exit(1)

    if hb is None:
        _log("[watchdog] Sin heartbeat — reiniciando bot")
        if sys.platform == "darwin":
            _restart_mac()
        else:
            _restart_linux()
        sys.exit(2)

    age = now - float(hb.get("epoch", 0))
    _log(
        f"[watchdog] heartbeat age={age:.0f}s status={hb.get('status')} "
        f"pid={hb.get('pid')} telegram={token_detail}"
    )

    if age > MAX_HEARTBEAT_AGE_SEC or hb.get("status") != "running":
        _log("[watchdog] Heartbeat obsoleto — reiniciando bot")
        if sys.platform == "darwin":
            _restart_mac()
        else:
            _restart_linux()
        sys.exit(2)

    _log("[watchdog] OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
