"""Graceful bot restart from Telegram or other in-process triggers."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from enum import Enum

from telegram.ext import Application

from bot.heartbeat import write_heartbeat

logger = logging.getLogger(__name__)

LABEL = "com.editorial-bot"
SERVICE_NAME = "editorial-bot"


class RestartMethod(str, Enum):
    SYSTEMD = "systemd"
    LAUNCHD = "launchd"
    EXEC = "exec"


def detect_restart_method() -> RestartMethod:
    """Pick the safest restart strategy for the current runtime."""
    if _systemd_service_active():
        return RestartMethod.SYSTEMD
    if sys.platform == "darwin" and _launchd_job_loaded():
        return RestartMethod.LAUNCHD
    return RestartMethod.EXEC


def _systemd_usable() -> bool:
    if sys.platform == "darwin":
        return False
    for sock in ("/run/systemd/private", "/var/run/systemd/private"):
        if os.path.exists(sock):
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


def _systemd_service_active() -> bool:
    if not _systemd_usable():
        return False
    try:
        result = subprocess.run(
            ["systemctl", "is-active", SERVICE_NAME],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and result.stdout.strip() == "active"
    except OSError:
        return False


def _launchd_job_loaded() -> bool:
    try:
        uid = subprocess.check_output(["id", "-u"], text=True).strip()
        target = f"gui/{uid}/{LABEL}"
        result = subprocess.run(
            ["launchctl", "print", target],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except OSError:
        return False


def restart_method_hint(method: RestartMethod) -> str:
    if method == RestartMethod.SYSTEMD:
        return f"systemd ({SERVICE_NAME})"
    if method == RestartMethod.LAUNCHD:
        return f"launchd ({LABEL})"
    return "reinicio del proceso"


async def _graceful_shutdown(application: Application) -> None:
    write_heartbeat(status="restarting")
    scheduler = application.bot_data.get("scheduler")
    if scheduler is not None:
        scheduler.shutdown(wait=False)

    if application.updater.running:
        await application.updater.stop()
    if application.running:
        await application.stop()


def _restart_via_systemd() -> None:
    subprocess.Popen(
        ["systemctl", "restart", SERVICE_NAME],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _restart_via_launchd() -> None:
    uid = subprocess.check_output(["id", "-u"], text=True).strip()
    target = f"gui/{uid}/{LABEL}"
    subprocess.Popen(
        ["launchctl", "kickstart", "-k", target],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _restart_via_exec() -> None:
    os.execv(sys.executable, [sys.executable, "-m", "bot.main"])


async def restart_bot(application: Application, *, delay_seconds: float = 2.0) -> RestartMethod:
    """Stop polling cleanly and restart the bot process."""
    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)

    method = detect_restart_method()
    logger.info("Restart requested via %s", method.value)
    await _graceful_shutdown(application)

    if method == RestartMethod.SYSTEMD:
        _restart_via_systemd()
        os._exit(0)
    if method == RestartMethod.LAUNCHD:
        _restart_via_launchd()
        os._exit(0)

    _restart_via_exec()
