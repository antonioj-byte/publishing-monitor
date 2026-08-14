#!/usr/bin/env python3
"""Delete the SQLite database and recreate an empty schema."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import settings
from db.connection import init_schema


def main() -> None:
    db_path = Path(settings.database_path)
    if db_path.exists():
        db_path.unlink()
        print(f"Eliminada: {db_path}")
    else:
        print(f"No existía: {db_path}")

    init_schema()
    print("Esquema recreado (BD vacía).")
    print("Siguiente: python3 scripts/load_medios.py && python3 scripts/run_ingest_once.py")


if __name__ == "__main__":
    main()
