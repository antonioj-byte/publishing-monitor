"""Lightweight liveness marker for external watchdogs."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from bot.config import settings

HEARTBEAT_PATH = Path(settings.database_path).parent / "heartbeat.json"


def write_heartbeat(*, status: str = "running", detail: str | None = None) -> None:
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "epoch": time.time(),
        "pid": __import__("os").getpid(),
    }
    if detail:
        payload["detail"] = detail
    HEARTBEAT_PATH.write_text(json.dumps(payload), encoding="utf-8")


def read_heartbeat() -> dict | None:
    if not HEARTBEAT_PATH.exists():
        return None
    try:
        return json.loads(HEARTBEAT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
