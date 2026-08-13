#!/usr/bin/env python3
"""Show counts at each stage of the editorial pipeline."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.editorial_filter import filter_editorial_scope
from bot.config import settings
from db.connection import get_connection, init_schema
from medios_tiers import TIER1_ALL, get_tier
from reports.generator import _fetch_articles, _resolve_window
from reports.prioritize import limit_batch_for_prioritization, prioritize_articles


def main() -> None:
    init_schema()
    since, _, mode = _resolve_window("informe", None)

    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM articulos").fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(*) FROM articulos WHERE procesado = 0"
        ).fetchone()[0]
        classified = conn.execute(
            "SELECT COUNT(*) FROM articulos WHERE procesado = 1"
        ).fetchone()[0]
        relevant = conn.execute(
            "SELECT COUNT(*) FROM articulos WHERE procesado = 1 AND relevance_score >= ?",
            (settings.min_relevance_score,),
        ).fetchone()[0]
        db_t1 = conn.execute(
            "SELECT COUNT(*) FROM medios WHERE tier = 1"
        ).fetchone()[0]

    print("=== Diagnóstico pipeline editorial ===\n")
    print(f"Ventana informe ({mode}): desde {since.isoformat()}")
    print(f"Artículos totales:     {total}")
    print(f"  pendientes clasificar: {pending}")
    print(f"  clasificados:          {classified}")
    print(f"  score >= {settings.min_relevance_score}:           {relevant}")
    print(f"Medios Tier 1 en BD:   {db_t1} (canon: {len(TIER1_ALL)})")
    print(f"ANTHROPIC_API_KEY:     {'sí' if settings.anthropic_api_key else 'NO — clasificación offline'}")
    print()

    # Raw SQL window fetch (sin filtros)
    since_iso = since.astimezone(__import__("zoneinfo").ZoneInfo("UTC")).isoformat()
    with get_connection() as conn:
        raw = conn.execute(
            """
            SELECT COUNT(*) FROM articulos a
            WHERE a.procesado = 1 AND a.relevance_score >= ?
              AND a.fecha_ingesta >= ? AND a.enviado = 0
            """,
            (settings.min_relevance_score, since_iso),
        ).fetchone()[0]

    articles = _fetch_articles(since, include_sent=False)
    batch, total = limit_batch_for_prioritization(articles)
    result = prioritize_articles(batch)

    print("Etapas del informe:")
    print(f"  1. SQL (score>={settings.min_relevance_score}, ventana):  {raw}")
    print(f"  2. Tras filtro editorial + tier canon:        {len(articles)}")
    print(f"  3. Batch priorización (max {settings.prioritize_max_batch}):     {len(batch)}")
    print(f"  4. Eventos sobre umbral ({settings.prioritize_score_threshold}):      {result.events_above_threshold}")
    print(f"  5. Artículos en informe priorizado:           {len(result.articles)}")
    print()

    if pending:
        print("⚠️  Hay artículos sin clasificar. Ejecuta:")
        print("    python3 scripts/classify_pending.py")
        print("    o ./deploy/reset-and-launch-mac.sh --reclassify")
    if not settings.anthropic_api_key:
        print("⚠️  Sin API Anthropic el agente de clasificación usa modo offline (score 3 genérico).")
    if db_t1 != len(TIER1_ALL):
        print("⚠️  Tiers desincronizados. Ejecuta: python3 scripts/sync_tiers.py")


if __name__ == "__main__":
    main()
