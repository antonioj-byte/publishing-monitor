#!/usr/bin/env python3
"""Show counts at each stage of the editorial pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import settings
from bot.report_parser import parse_command_args
from db.connection import get_connection, init_schema
from db.models import ReportFilter
from medios_tiers import TIER1_ALL
from reports.generator import (
    _count_country_candidates,
    _count_tag_candidates,
    _fetch_articles,
    _resolve_window,
)
from reports.prioritize import limit_batch_for_prioritization, prioritize_articles


def _diagnose_tags(report_filter: ReportFilter) -> None:
    since, include_sent, mode = _resolve_window("informe_pais", report_filter)
    use_pub_date = mode in ("informe_pais", "informe_hoy")
    strict_publication = False
    with_tag, in_window, missing_tags, pending = _count_tag_candidates(
        report_filter,
        since,
        date_by_publication=use_pub_date,
        strict_publication=strict_publication,
    )
    tag_label = ", ".join(report_filter.tag_labels or report_filter.tags or [])

    print(f"=== Informe tag: {tag_label} ({report_filter.days} días) ===\n")
    print(f"Ventana desde:         {since.isoformat()}")
    print(f"Filtro fecha:          {'publicación (fallback ingesta)' if use_pub_date else 'ingesta'}")
    print(f"Con tag en ventana:    {with_tag}")
    print(f"Clasificados ventana:  {in_window}")
    print(f"Sin tags (procesados): {missing_tags}")
    print(f"Pendientes clasificar: {pending}")
    print()

    articles = _fetch_articles(
        since,
        include_sent=include_sent,
        report_filter=report_filter,
        date_by_publication=use_pub_date,
    )
    batch, total = limit_batch_for_prioritization(articles)
    result = prioritize_articles(batch)

    print("Etapas del informe por tag:")
    print(f"  1. SQL (score>={settings.min_relevance_score}, tag, ventana): {with_tag}")
    print(f"  2. Tras filtro editorial:                    {len(articles)}")
    print(f"  3. Batch priorización (max {settings.prioritize_max_batch}):     {len(batch)}")
    print(f"  4. Eventos sobre umbral ({settings.prioritize_score_threshold}):      {result.events_above_threshold}")
    print(f"  5. Artículos en informe priorizado:           {len(result.articles)}")
    print()

    if missing_tags:
        print("⚠️  Hay artículos clasificados sin tags. Ejecuta:")
        print("    python3 scripts/backfill_tags.py --yes")
        print("    python3 scripts/classify_pending.py")
        print("    o /reclasificar en Telegram")
    elif pending:
        print("⚠️  Hay artículos sin clasificar. Ejecuta:")
        print("    python3 scripts/classify_pending.py")
    elif in_window and not with_tag:
        print("⚠️  Hay artículos en ventana pero ninguno tiene este tag.")
    elif with_tag and not articles:
        print("⚠️  Hay artículos con tag pero el filtro editorial los descartó todos.")
    elif with_tag and not result.articles:
        print("⚠️  Ningún evento supera el umbral de priorización. Prueba más días.")


def _diagnose_country(report_filter: ReportFilter) -> None:
    since, include_sent, mode = _resolve_window("informe_pais", report_filter)
    use_pub_date = mode in ("informe_pais", "informe_hoy")
    in_window, pending, total_geo = _count_country_candidates(
        report_filter, since, date_by_publication=use_pub_date
    )

    print(f"=== Informe país: {report_filter.location_label} ({report_filter.days} días) ===\n")
    print(f"Ventana desde:         {since.isoformat()}")
    print(f"Filtro fecha:          {'publicación (fallback ingesta)' if use_pub_date else 'ingesta'}")
    print(f"Artículos del país:    {total_geo}")
    print(f"  clasificados en ventana: {in_window}")
    print(f"  pendientes clasificar:   {pending}")
    print()

    articles = _fetch_articles(
        since,
        include_sent=include_sent,
        report_filter=report_filter,
        date_by_publication=use_pub_date,
    )
    batch, total = limit_batch_for_prioritization(articles)
    result = prioritize_articles(batch)

    print("Etapas del informe país:")
    print(f"  1. SQL (score>={settings.min_relevance_score}, ventana):  {in_window}")
    print(f"  2. Tras filtro editorial:                    {len(articles)}")
    print(f"  3. Batch priorización (max {settings.prioritize_max_batch}):     {len(batch)}")
    print(f"  4. Eventos sobre umbral ({settings.prioritize_score_threshold}):      {result.events_above_threshold}")
    print(f"  5. Artículos en informe priorizado:           {len(result.articles)}")
    print()

    if total_geo == 0:
        print("⚠️  No hay artículos ingeridos de ese país. Ejecuta:")
        print("    python3 scripts/run_ingest_once.py")
    elif pending:
        print("⚠️  Hay artículos sin clasificar. Ejecuta:")
        print("    python3 scripts/classify_pending.py")
    elif in_window and not articles:
        print("⚠️  Hay artículos en ventana pero el filtro editorial los descartó todos.")
    elif in_window and not result.articles:
        print("⚠️  Ningún evento supera el umbral de priorización. Prueba más días.")
    elif not in_window:
        print("⚠️  Nada publicado/ingerido en la ventana. Prueba:")
        print(f"    /informe 7 {report_filter.location_label.lower()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose editorial pipeline stages")
    parser.add_argument(
        "args",
        nargs="*",
        help="Optional country filter, e.g. 1 estados unidos",
    )
    cli = parser.parse_args()

    init_schema()

    if cli.args:
        parsed = parse_command_args(cli.args)
        if not parsed:
            parser.error("Provide days and country/tag, e.g.: python3 scripts/diagnose_pipeline.py 7 ficcion")
        report_filter = ReportFilter(
            days=parsed.days,
            pais=parsed.pais,
            region=parsed.region,
            location_label=parsed.location_label,
            tags=parsed.tags or None,
            tag_labels=parsed.tag_labels or None,
        )
        if parsed.tags and not parsed.pais and not parsed.region:
            _diagnose_tags(report_filter)
        else:
            _diagnose_country(report_filter)
        return

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
        with_tags = conn.execute(
            """
            SELECT COUNT(*) FROM articulos
            WHERE procesado = 1
              AND tags IS NOT NULL AND tags != '' AND tags != '[]'
            """
        ).fetchone()[0]
        missing_tags = conn.execute(
            """
            SELECT COUNT(*) FROM articulos
            WHERE procesado = 1
              AND (tags IS NULL OR tags = '' OR tags = '[]')
            """
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
    print(f"  con tags editoriales:  {with_tags}")
    print(f"  sin tags (procesados): {missing_tags}")
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

    if missing_tags:
        print("⚠️  Hay artículos clasificados sin tags editoriales. Ejecuta:")
        print("    python3 scripts/backfill_tags.py --yes")
        print("    python3 scripts/classify_pending.py")
        print("    o /reclasificar en Telegram")
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
