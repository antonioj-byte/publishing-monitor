#!/usr/bin/env python3
"""Mark broken RSS medios as scraping in the database."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.connection import get_connection

# Medios where RSS failed during ingest validation
SCRAPE_FALLBACK = [
    "Livres Hebdo",
    "El País Uruguay Cultura",
    "El Universal Cultura",
    "Esprit",
    "Financial Times Books",
    "Focus Kultur",
    "Folha de S.Paulo Ilustrada",
    "Gatopardo",
    "Granta",
    "L'Espresso Cultura",
    "La Nouvelle Revue Française",
    "La Presse Arts",
    "La Stampa Cultura",
    "La Tercera Cultura",
    "Le Débat",
    "Le Point Culture",
    "Le Soir Culture",
    "Le Temps Culture",
    "Lettre International",
    "Newsweek",
    "Nuovi Argomenti",
    "Panorama Cultura",
    "Revista de Occidente",
    "Sinn und Form",
    "The Believer",
    "The Globe and Mail Books",
    "Anfibia",
    "El Malpensante",
    "Il Mulino",
    "Jot Down",
    "La Maleta de Portbou",
    "Les Temps Modernes",
    "Letras Libres",
    "Merkur",
    "MicroMega",
    "Nexos",
    "The Threepenny Review",
    "XXI",
]


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
