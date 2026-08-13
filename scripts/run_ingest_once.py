#!/usr/bin/env python3
"""Run a single ingestion pass."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.connection import init_schema
from ingest.runner import ingest_all

logging.basicConfig(level=logging.INFO)


def main() -> None:
    init_schema()
    stats = ingest_all()
    print(f"Ingest complete: inserted={stats.inserted}, skipped={stats.skipped}, errors={len(stats.errors)}")
    for err in stats.errors:
        print(f"  ERROR {err['medio']}: {err['error']}")


if __name__ == "__main__":
    main()
