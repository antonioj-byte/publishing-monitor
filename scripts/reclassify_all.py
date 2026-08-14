#!/usr/bin/env python3
"""Reclassify all articles with Anthropic (or offline fallback)."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import settings
from bot.reclassify_service import run_reclassify_all
from db.connection import get_connection, init_schema

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reclassify all articles in DB")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Articles per batch (default: 20)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.3,
        help="Seconds between API calls (default: 0.3)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )
    args = parser.parse_args()

    init_schema()

    if not settings.anthropic_api_key:
        logger.warning(
            "ANTHROPIC_API_KEY no configurada — se usará clasificación offline básica"
        )
    else:
        logger.info("Usando Anthropic API para reclasificación")

    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM articulos").fetchone()[0]

    if total == 0:
        print("No hay artículos. Ejecuta: python scripts/run_ingest_once.py")
        sys.exit(1)

    if not args.yes:
        print(f"Se resetearán y reclasificarán {total} artículos (con tags).")
        answer = input("¿Continuar? [y/N] ").strip().lower()
        if answer not in ("y", "yes", "s", "si", "sí"):
            print("Cancelado.")
            sys.exit(0)

    stats = run_reclassify_all(
        batch_size=args.batch_size,
        delay=args.delay,
        reset=True,
    )
    print(
        f"\nListo: {stats['with_tags']} con tags, {stats['classified']} reclasificados, "
        f"{stats['failed']} fallidos de {stats['total']} totales"
    )


if __name__ == "__main__":
    main()
