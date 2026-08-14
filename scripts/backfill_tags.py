#!/usr/bin/env python3
"""Mark articles without tags for reclassification."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.connection import get_connection, init_schema


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset articles missing editorial tags")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation")
    args = parser.parse_args()

    init_schema()
    with get_connection() as conn:
        count = conn.execute(
            """
            SELECT COUNT(*) FROM articulos
            WHERE procesado = 1
              AND (tags IS NULL OR tags = '' OR tags = '[]')
            """
        ).fetchone()[0]

    if count == 0:
        print("Todos los artículos procesados ya tienen tags.")
        return

    if not args.yes:
        answer = input(f"¿Retag {count} artículos? [y/N] ").strip().lower()
        if answer not in ("y", "yes", "s", "si", "sí"):
            print("Cancelado.")
            return

    with get_connection() as conn:
        n = conn.execute(
            """
            UPDATE articulos SET procesado = 0
            WHERE procesado = 1
              AND (tags IS NULL OR tags = '' OR tags = '[]')
            """
        ).rowcount
        conn.commit()

    print(f"Marcados {n} artículos para reclasificar con tags.")
    print("Ejecuta: python3 scripts/classify_pending.py")


if __name__ == "__main__":
    main()
