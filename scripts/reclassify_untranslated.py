#!/usr/bin/env python3
"""Reclassify articles that were never translated to Spanish."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import settings
from bot.retranslate_service import find_untranslated_ids, run_retranslate


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Retranslate non-Spanish articles via the classify API"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max articles to retranslate (default: all detected)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation",
    )
    args = parser.parse_args()

    if not settings.has_classify_api():
        print(
            "Configura GOOGLE_API_KEY o ANTHROPIC_API_KEY para traducir al castellano."
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

    stats = run_retranslate(limit=len(ids))
    print(
        f"\nListo: {stats.get('fixed', 0)} corregidos, "
        f"{stats.get('still_untranslated', 0)} siguen sin castellano, "
        f"{stats.get('failed', 0)} fallidos."
    )


if __name__ == "__main__":
    main()
