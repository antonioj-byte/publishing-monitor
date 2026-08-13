#!/usr/bin/env python3
"""Validate ingestion and deduplication."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.connection import get_connection, init_schema
from ingest.runner import ingest_all


def main() -> None:
    init_schema()

    print("=== Pass 1 ===")
    stats1 = ingest_all()
    print(f"inserted={stats1.inserted}, skipped={stats1.skipped}, errors={len(stats1.errors)}")

    print("\n=== Pass 2 (dedup check) ===")
    stats2 = ingest_all()
    print(f"inserted={stats2.inserted}, skipped={stats2.skipped}, errors={len(stats2.errors)}")

    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM articulos").fetchone()[0]
        medios_with = conn.execute(
            "SELECT COUNT(DISTINCT medio_id) FROM articulos"
        ).fetchone()[0]

    print(f"\nTotal articles in DB: {total}")
    print(f"Medios with articles: {medios_with}")

    # Allow tiny inserts on pass 2 (feeds updating live or scraper drift)
    dedup_ok = stats2.inserted == 0 or (
        stats2.skipped > 0 and stats2.inserted / max(stats2.skipped, 1) < 0.01
    )

    if not dedup_ok:
        print("FAIL: Second pass inserted too many new articles")
        sys.exit(1)

    print("OK: Deduplication validated")

    if medios_with < 15:
        print(f"WARNING: Only {medios_with} medios have articles (target >= 15)")
        sys.exit(1)

    print(f"OK: Coverage target met ({medios_with} medios with articles)")


if __name__ == "__main__":
    main()
