"""Retranslate non-Spanish articles that were classified without translation."""

from __future__ import annotations

import json
import logging
import time

from ai.classify import classify_article, verify_classify_api
from ai.translation import is_likely_untranslated
from bot.config import settings
from db.connection import get_connection, init_schema
from medios_tiers import get_tier

logger = logging.getLogger(__name__)


def find_untranslated_ids(
    *,
    limit: int | None = None,
    article_ids: list[int] | None = None,
) -> list[int]:
    init_schema()
    id_filter = ""
    params: list[object] = []
    if article_ids:
        placeholders = ",".join("?" * len(article_ids))
        id_filter = f" AND a.id IN ({placeholders})"
        params.extend(article_ids)

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT a.id, a.idioma, a.titulo_original, a.titular_traducido,
                   a.resumen_generado, a.resumen_raw
            FROM articulos a
            WHERE a.procesado = 1 AND a.idioma != 'es'{id_filter}
            ORDER BY a.fecha_ingesta DESC
            """,
            params,
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


def retranslate_ids(article_ids: list[int], *, delay_seconds: float = 0.25) -> dict[str, int]:
    """Re-run LLM classification for specific articles (preserves tags when possible)."""
    stats = {"attempted": 0, "fixed": 0, "failed": 0, "still_untranslated": 0}
    if not article_ids:
        return stats

    verify_classify_api()

    with get_connection() as conn:
        placeholders = ",".join("?" * len(article_ids))
        rows = conn.execute(
            f"""
            SELECT a.id, a.titulo_original, a.resumen_raw, a.categoria, a.idioma,
                   a.fecha_publicacion, a.tags, m.nombre AS medio_nombre,
                   m.categoria_default
            FROM articulos a
            JOIN medios m ON m.id = a.medio_id
            WHERE a.id IN ({placeholders})
            """,
            article_ids,
        ).fetchall()

    for i, row in enumerate(rows):
        if i > 0 and delay_seconds > 0:
            time.sleep(delay_seconds)
        stats["attempted"] += 1
        try:
            result = classify_article(
                titulo=row["titulo_original"],
                resumen=row["resumen_raw"],
                medio=row["medio_nombre"],
                categoria_default=row["categoria_default"],
                idioma=row["idioma"],
                medio_tier=get_tier(row["medio_nombre"], row["categoria_default"]),
                fecha_publicacion=row["fecha_publicacion"],
                allow_offline=False,
            )
            tags_json = row["tags"]
            if result.tags:
                tags_json = json.dumps(result.tags)
            with get_connection() as conn:
                conn.execute(
                    """
                    UPDATE articulos SET
                        categoria = ?,
                        relevance_score = ?,
                        resumen_generado = ?,
                        titular_traducido = ?,
                        tags = ?,
                        procesado = 1
                    WHERE id = ?
                    """,
                    (
                        result.categoria,
                        result.relevance_score,
                        result.resumen_generado,
                        result.titular_traducido,
                        tags_json,
                        row["id"],
                    ),
                )
                conn.commit()
            if is_likely_untranslated(
                idioma=row["idioma"],
                titulo_original=row["titulo_original"],
                titular_traducido=result.titular_traducido,
                resumen_generado=result.resumen_generado,
                resumen_raw=row["resumen_raw"],
            ):
                stats["still_untranslated"] += 1
            else:
                stats["fixed"] += 1
        except Exception:
            logger.exception("Retranslate failed for article %s", row["id"])
            stats["failed"] += 1

    return stats


def run_retranslate(*, limit: int = 30) -> dict[str, int]:
    """Find untranslated articles and reclassify them with the LLM API."""
    if not settings.has_classify_api():
        return {"attempted": 0, "fixed": 0, "failed": 0, "still_untranslated": 0, "no_api": 1}

    ids = find_untranslated_ids(limit=limit)
    if not ids:
        return {"attempted": 0, "fixed": 0, "failed": 0, "still_untranslated": 0}

    stats = retranslate_ids(ids)
    logger.info("Retranslate batch: %s", stats)
    return stats


def retranslate_before_report(*, limit: int = 15) -> dict[str, int]:
    """Best-effort retranslation before building a report (non-blocking on failure)."""
    if not settings.has_classify_api():
        return {"skipped": 1}
    try:
        return run_retranslate(limit=limit)
    except Exception:
        logger.exception("Auto-retranslate before report failed")
        return {"failed": 1}
