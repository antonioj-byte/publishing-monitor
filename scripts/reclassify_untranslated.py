#!/usr/bin/env python3
"""Reclassify articles that were never translated to Spanish."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.classify import classify_pending
from ai.translation import is_likely_untranslated
from bot.config import settings
from db.connection import get_connection, init_schema

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)


def find_untranslated_ids(limit: int | None = None) -> list[int]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT a.id, a.idioma, a.titulo_original, a.titular_traducido,
                   a.resumen_generado, a.resumen_raw
            FROM articulos a
            WHERE a.procesado = 1 AND a.idioma != 'es'
            ORDER BY a.fecha_ingesta DESC
            """
        ).fetchall()

    ids: list[int] = []
    for row in rows:
        if is_likely_untranslated(
            idioma=row["idioma"],
            titulo_original=row["titulo_original"],
            titular_traducido=row["titular_traducido"],
            resumen_generado=row["resumen_generado"],
            resumen_raw=row["resumen_raw"],
        ):
            ids.append(row["id"])
            if limit and len(ids) >= limit:
                break
    return ids


def reset_ids(article_ids: list[int]) -> int:
    if not article_ids:
        return 0
    placeholders = ",".join("?" * len(article_ids))
    with get_connection() as conn:
        conn.execute(
            f"""
            UPDATE articulos SET
                procesado = 0,
                resumen_generado = NULL,
                titular_traducido = NULL
            WHERE id IN ({placeholders})
            """,
            article_ids,
        )
        conn.commit()
    return len(article_ids)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reclassify non-Spanish articles with Anthropic translation"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max articles to reset (default: all untranslated)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation",
    )
    args = parser.parse_args()

    init_schema()

    if not settings.anthropic_api_key:
        print(
            "ANTHROPIC_API_KEY requerida para traducir al castellano.\n"
            "Configúrala en .env y vuelve a ejecutar."
        )
        sys.exit(1)

    ids = find_untranslated_ids(limit=args.limit)
    if not ids:
        print("No hay artículos pendientes de traducción.")
        return

    if not args.yes:
        print(f"Se retraducirán {len(ids)} artículos al castellano.")
        answer = input("¿Continuar? [y/N] ").strip().lower()
        if answer not in ("y", "yes", "s", "si", "sí"):
            print("Cancelado.")
            return

    reset = reset_ids(ids)
    logger.info("Reset %d artículos para retraducción", reset)

    classified = 0
    while True:
        stats = classify_pending(limit=min(20, len(ids) - classified))
        classified += stats["classified"]
        if stats["remaining"] == 0 or stats["classified"] == 0:
            break

    print(f"\nListo: {classified} artículos retraducidos de {reset} detectados.")


if __name__ == "__main__":
    main()
