#!/usr/bin/env python3
"""Mark broken RSS medios as scraping in the database."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.connection import get_connection
from scripts.load_medios import SCRAPE_FALLBACK_NAMES as SCRAPE_FALLBACK


def main() -> None:
    with get_connection() as conn:
        for name in SCRAPE_FALLBACK:
            row = conn.execute(
                "SELECT id, url_site, url_scraping FROM medios WHERE nombre = ?", (name,)
            ).fetchone()
            if not row:
                continue
            scrape_url = row["url_scraping"] or row["url_site"]
            conn.execute(
                """
                UPDATE medios SET metodo = 'scraping', url_scraping = ?
                WHERE id = ?
                """,
                (scrape_url, row["id"]),
            )
        conn.commit()
        counts = conn.execute(
            "SELECT metodo, COUNT(*) FROM medios WHERE activo=1 GROUP BY metodo"
        ).fetchall()
    print("Updated scrape fallbacks:", len(SCRAPE_FALLBACK))
    print("Methods:", dict(counts))


if __name__ == "__main__":
    main()
