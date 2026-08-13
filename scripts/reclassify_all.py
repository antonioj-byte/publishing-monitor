#!/usr/bin/env python3
"""Reclassify all articles with Anthropic (or offline fallback)."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.classify import classify_pending
from bot.config import settings
from db.connection import get_connection, init_schema

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)


def reset_all() -> int:
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM articulos").fetchone()[0]
        conn.execute(
            """
            UPDATE articulos SET
                procesado = 0,
                resumen_generado = NULL,
                titular_traducido = NULL,
                relevance_score = NULL
            """
        )
        conn.commit()
    return count


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
        print(f"Se resetearán y reclasificarán {total} artículos.")
        answer = input("¿Continuar? [y/N] ").strip().lower()
        if answer not in ("y", "yes", "s", "si", "sí"):
            print("Cancelado.")
            sys.exit(0)

    reset = reset_all()
    logger.info("Reset %d artículos", reset)

    classified_total = 0
    failed_total = 0
    batch_num = 0

    while True:
        batch_num += 1
        stats = classify_pending(limit=args.batch_size)
        classified_total += stats["classified"]
        failed_total += stats["failed"]

        logger.info(
            "Lote %d: +%d clasificados, %d fallidos, %d pendientes",
            batch_num,
            stats["classified"],
            stats["failed"],
            stats["remaining"],
        )

        if stats["remaining"] == 0 or stats["classified"] == 0:
            break

        if settings.anthropic_api_key and args.delay > 0:
            time.sleep(args.delay)

    print(
        f"\nListo: {classified_total} reclasificados, {failed_total} fallidos "
        f"de {total} totales"
    )


if __name__ == "__main__":
    main()
