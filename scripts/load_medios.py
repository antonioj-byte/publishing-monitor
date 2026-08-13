#!/usr/bin/env python3
"""Load medios.csv into the medios table."""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import MEDIOS_CSV
from db.connection import get_connection, init_schema
from medios_tiers import get_tier
from reports.paises import get_pais_for_medio

# Medios known to need scraping instead of broken/generic RSS
# Medios whose primary RSS is broken; scraping used as fallback.
# Paywalled medios (FT, WSJ, Times, WaPo, Globe, Granta) use dedicated RSS
# alternatives in medios.csv — see ingest/paywall_alternatives.py
SCRAPE_FALLBACK_NAMES = {
    "Livres Hebdo", "El País Uruguay Cultura", "El Universal Cultura", "Esprit",
    "Focus Kultur", "Folha de S.Paulo Ilustrada", "Gatopardo",
    "L'Espresso Cultura", "La Nouvelle Revue Française", "La Presse Arts",
    "La Stampa Cultura", "La Tercera Cultura", "Le Débat", "Le Point Culture",
    "Le Soir Culture", "Le Temps Culture", "Lettre International", "Newsweek",
    "Nuovi Argomenti", "Panorama Cultura", "Revista de Occidente", "Sinn und Form",
    "The Believer", "Anfibia", "El Malpensante",
    "Il Mulino", "Jot Down", "La Maleta de Portbou", "Les Temps Modernes",
    "Letras Libres", "Merkur", "MicroMega", "Nexos", "The Threepenny Review", "XXI",
}


def apply_scrape_fallbacks(conn) -> int:
    updated = 0
    for name in SCRAPE_FALLBACK_NAMES:
        row = conn.execute(
            "SELECT id, url_site, url_scraping FROM medios WHERE nombre = ?", (name,)
        ).fetchone()
        if not row:
            continue
        scrape_url = row["url_scraping"] or row["url_site"]
        conn.execute(
            "UPDATE medios SET metodo = 'scraping', url_scraping = ? WHERE id = ?",
            (scrape_url, row["id"]),
        )
        updated += 1
    return updated


def load_medios(csv_path: Path | None = None) -> dict[str, int]:
    path = csv_path or MEDIOS_CSV
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")

    init_schema()
    stats = {"inserted": 0, "updated": 0, "skipped": 0}

    with get_connection() as conn:
        with path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                nombre = row["nombre"].strip()
                url_rss = row.get("url_rss", "").strip() or None
                url_scraping = row.get("url_scraping", "").strip() or None
                metodo = row["metodo"].strip()
                activo = row.get("activo", "true").strip().lower() in ("true", "1", "yes")
                categoria_default = row["categoria_default"].strip()
                tier = get_tier(nombre, categoria_default)
                pais_raw = row.get("pais", "").strip()
                pais = pais_raw if pais_raw else get_pais_for_medio(nombre)

                if metodo == "rss" and not url_rss:
                    metodo = "scraping"
                    url_scraping = url_scraping or row["url_site"].strip()

                existing = conn.execute(
                    "SELECT id FROM medios WHERE nombre = ?", (nombre,)
                ).fetchone()

                values = (
                    row["url_site"].strip(),
                    url_rss,
                    url_scraping,
                    metodo,
                    categoria_default,
                    row["idioma"].strip(),
                    row["region"].strip(),
                    pais,
                    tier,
                    1 if activo else 0,
                )

                if existing:
                    conn.execute(
                        """
                        UPDATE medios SET
                            url_site = ?, url_rss = ?, url_scraping = ?,
                            metodo = ?, categoria_default = ?, idioma = ?,
                            region = ?, pais = ?, tier = ?, activo = ?
                        WHERE nombre = ?
                        """,
                        (*values, nombre),
                    )
                    stats["updated"] += 1
                else:
                    conn.execute(
                        """
                        INSERT INTO medios (
                            nombre, url_site, url_rss, url_scraping, metodo,
                            categoria_default, idioma, region, pais, tier, activo
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (nombre, *values),
                    )
                    stats["inserted"] += 1

        conn.commit()

    with get_connection() as conn:
        fallbacks = apply_scrape_fallbacks(conn)
        conn.commit()
    stats["scrape_fallbacks"] = fallbacks

    return stats


def print_summary() -> None:
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM medios WHERE activo = 1").fetchone()[0]
        by_cat = conn.execute(
            """
            SELECT categoria_default, COUNT(*) FROM medios
            WHERE activo = 1 GROUP BY categoria_default
            """
        ).fetchall()
        by_metodo = conn.execute(
            """
            SELECT metodo, COUNT(*) FROM medios
            WHERE activo = 1 GROUP BY metodo
            """
        ).fetchall()

    print(f"Active medios: {total}")
    print("By category:", dict(by_cat))
    print("By method:", dict(by_metodo))


def main() -> None:
    stats = load_medios()
    print(f"Loaded medios: {stats}")
    print_summary()


if __name__ == "__main__":
    main()
