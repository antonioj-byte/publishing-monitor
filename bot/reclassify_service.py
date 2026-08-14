"""Full-database reclassification with tags."""

from __future__ import annotations

import logging
import time

from ai.classify import classify_pending, verify_anthropic_api
from bot.config import settings
from db.connection import get_connection, init_schema

logger = logging.getLogger(__name__)


def reset_all_for_reclassify() -> int:
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM articulos").fetchone()[0]
        conn.execute(
            """
            UPDATE articulos SET
                procesado = 0,
                resumen_generado = NULL,
                titular_traducido = NULL,
                relevance_score = NULL,
                tags = NULL
            """
        )
        conn.commit()
    return count


def count_tagged_processed() -> int:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT COUNT(*) FROM articulos
            WHERE procesado = 1
              AND tags IS NOT NULL
              AND tags != ''
              AND tags != '[]'
            """
        ).fetchone()[0]


def run_reclassify_all(
    *,
    batch_size: int = 20,
    delay: float = 0.25,
    reset: bool = True,
) -> dict[str, int]:
    """Reclassify all articles; returns totals."""
    init_schema()
    verify_anthropic_api()

    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM articulos").fetchone()[0]

    if total == 0:
        return {
            "total": 0,
            "classified": 0,
            "failed": 0,
            "batches": 0,
            "with_tags": 0,
            "no_tags": 0,
        }

    if reset:
        reset_all_for_reclassify()
        logger.info("Reset %d artículos para reclasificación", total)

    classified_total = 0
    failed_total = 0
    no_tags_total = 0
    batch_num = 0

    while True:
        batch_num += 1
        stats = classify_pending(limit=batch_size, require_tags=True)
        classified_total += stats["classified"]
        failed_total += stats["failed"]
        no_tags_total += stats.get("no_tags", 0)

        logger.info(
            "Reclassify lote %d: +%d, fallidos %d, pendientes %d",
            batch_num,
            stats["classified"],
            stats["failed"],
            stats["remaining"],
        )

        if stats["remaining"] == 0 or stats["classified"] == 0:
            break

        if settings.anthropic_api_key and delay > 0:
            time.sleep(delay)

    with_tags = count_tagged_processed()

    return {
        "total": total,
        "classified": classified_total,
        "failed": failed_total,
        "batches": batch_num,
        "with_tags": with_tags,
        "no_tags": no_tags_total,
    }
