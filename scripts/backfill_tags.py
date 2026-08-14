#!/usr/bin/env python3
"""Mark articles without tags for reclassification."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.reclassify_service import run_backfill_tags

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Retag articles missing editorial tags")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--delay", type=float, default=0.3)
    args = parser.parse_args()

    if not args.yes:
        answer = input("¿Retag artículos sin tags? [y/N] ").strip().lower()
        if answer not in ("y", "yes", "s", "si", "sí"):
            print("Cancelado.")
            return

    stats = run_backfill_tags(batch_size=args.batch_size, delay=args.delay)
    print(
        f"\nListo: {stats['with_tags']} con tags, {stats['classified']} procesados, "
        f"{stats['failed']} fallidos (en cola: {stats.get('queued', 0)})"
    )


if __name__ == "__main__":
    main()
