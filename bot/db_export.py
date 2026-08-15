"""Safe SQLite database export for download."""

from __future__ import annotations

import sqlite3
import tempfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from bot.config import settings


def export_database_bytes() -> tuple[BytesIO, str]:
    """Return a consistent snapshot of the editorial database as bytes."""
    source = Path(settings.database_path)
    if not source.is_file():
        raise FileNotFoundError(
            f"No se encontró la base de datos en {source}. "
            "Comprueba DATABASE_PATH y el volumen en Railway."
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    filename = f"editorial-{stamp}.db"

    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        snapshot_path = tmp.name
        with sqlite3.connect(source) as src, sqlite3.connect(snapshot_path) as dst:
            src.backup(dst)

        payload = BytesIO(Path(snapshot_path).read_bytes())
        payload.name = filename
        return payload, filename
