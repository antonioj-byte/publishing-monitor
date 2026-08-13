"""Orchestrates ingestion from all active medios."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from db.connection import get_connection
from db.models import Medio
from ingest.rss import ParsedArticle, parse_feed
from ingest.scraper import scrape_section

logger = logging.getLogger(__name__)


@dataclass
class IngestStats:
    inserted: int = 0
    skipped: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)


def _row_to_medio(row) -> Medio:
    return Medio(
        id=row["id"],
        nombre=row["nombre"],
        url_site=row["url_site"],
        url_rss=row["url_rss"],
        url_scraping=row["url_scraping"],
        metodo=row["metodo"],
        categoria_default=row["categoria_default"],
        idioma=row["idioma"],
        region=row["region"],
        activo=bool(row["activo"]),
    )


def fetch_articles(medio: Medio) -> list[ParsedArticle]:
    if medio.metodo == "rss" and medio.url_rss:
        return parse_feed(medio.url_rss)
    scrape_url = medio.url_scraping or medio.url_site
    return scrape_section(scrape_url)


def save_article(medio: Medio, article: ParsedArticle, stats: IngestStats) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO articulos (
                    medio_id, url, titulo_original, fecha_publicacion,
                    fecha_ingesta, categoria, idioma, resumen_raw,
                    hash_contenido, procesado, enviado
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
                """,
                (
                    medio.id,
                    article.url,
                    article.title,
                    article.published_at,
                    now,
                    medio.categoria_default,
                    medio.idioma,
                    article.summary,
                    article.hash_contenido,
                ),
            )
            conn.commit()
            stats.inserted += 1
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                stats.skipped += 1
            else:
                raise


def ingest_all() -> IngestStats:
    stats = IngestStats()

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM medios WHERE activo = 1 ORDER BY nombre"
        ).fetchall()

    for row in rows:
        medio = _row_to_medio(row)
        try:
            articles = fetch_articles(medio)
            logger.info("%s: fetched %d articles", medio.nombre, len(articles))
            for article in articles:
                save_article(medio, article, stats)
        except Exception as exc:
            logger.exception("Failed ingesting %s", medio.nombre)
            stats.errors.append({"medio": medio.nombre, "error": str(exc)})

    return stats


def ingest_medio_by_id(medio_id: int) -> IngestStats:
    stats = IngestStats()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM medios WHERE id = ?", (medio_id,)).fetchone()
    if not row:
        raise ValueError(f"Medio {medio_id} not found")
    medio = _row_to_medio(row)
    articles = fetch_articles(medio)
    for article in articles:
        save_article(medio, article, stats)
    return stats
