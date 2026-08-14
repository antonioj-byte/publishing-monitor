#!/usr/bin/env python3
"""Verify classification, editorial filter and prioritization are active."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.editorial_filter import filter_editorial_scope, is_editorial_scope
from bot.config import settings
from db.connection import get_connection, init_schema
from reports.generator import _fetch_articles, _resolve_window
from reports.pipeline import build_editorial_report
from reports.prioritize import limit_batch_for_prioritization, prioritize_articles


def _fetch_classified_window(since) -> list[dict]:
    since_iso = since.astimezone(__import__("zoneinfo").ZoneInfo("UTC")).isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT a.id, a.titulo_original, a.titular_traducido,
                   a.resumen_raw, a.resumen_generado, a.relevance_score,
                   a.categoria, m.nombre AS medio_nombre, m.tier AS medio_tier
            FROM articulos a
            JOIN medios m ON m.id = a.medio_id
            WHERE a.procesado = 1
              AND a.relevance_score >= ?
              AND a.fecha_ingesta >= ?
            ORDER BY a.relevance_score DESC, a.fecha_ingesta DESC
            LIMIT 500
            """,
            (settings.min_relevance_score, since_iso),
        ).fetchall()
    return [dict(row) for row in rows]


def main() -> None:
    init_schema()
    since, _, mode = _resolve_window("informe", None)

    print("=== Verificación agentes editoriales ===\n")
    print(f"Ventana ({mode}): {since.isoformat()}")
    print(f"ANTHROPIC_API_KEY: {'sí' if settings.anthropic_api_key else 'NO (modo offline)'}")
    print()

    with get_connection() as conn:
        stats = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN procesado = 0 THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN procesado = 1 THEN 1 ELSE 0 END) AS classified,
                SUM(CASE WHEN procesado = 1 AND relevance_score >= ? THEN 1 ELSE 0 END) AS relevant,
                SUM(CASE WHEN procesado = 1 AND relevance_score <= 2 THEN 1 ELSE 0 END) AS low_score
            FROM articulos
            """,
            (settings.min_relevance_score,),
        ).fetchone()

    print("Base de datos:")
    print(f"  artículos totales:     {stats['total']}")
    print(f"  pendientes clasificar: {stats['pending']}")
    print(f"  clasificados:          {stats['classified']}")
    print(f"  score >= {settings.min_relevance_score}:           {stats['relevant']}")
    print(f"  score <= 2 (descartados):  {stats['low_score']}")
    print()

    if stats["total"] == 0:
        print("⚠️  BD vacía. Ejecuta: python3 scripts/run_ingest_once.py")
        sys.exit(1)

    if stats["pending"]:
        print("⚠️  Hay artículos sin clasificar. Ejecuta:")
        print("    python3 scripts/classify_pending.py")
        print()

    raw = _fetch_classified_window(since)
    kept = filter_editorial_scope(raw)
    rejected = [
        article
        for article in raw
        if not is_editorial_scope(
            titulo=article.get("titulo_original", ""),
            titular_traducido=article.get("titular_traducido"),
            resumen=article.get("resumen_raw"),
            resumen_generado=article.get("resumen_generado"),
        )
    ]

    print("Agente 1 — Clasificación + filtro editorial:")
    print(f"  candidatos SQL (ventana):  {len(raw)}")
    print(f"  tras filtro editorial:     {len(kept)}")
    print(f"  descartados por filtro:    {len(rejected)}")
    print()

    if rejected[:3]:
        print("  Ejemplos descartados por filtro keyword (score>=3):")
        for article in rejected[:3]:
            title = article.get("titular_traducido") or article.get("titulo_original", "")
            print(f"    · [{article.get('relevance_score')}] {title[:90]}")
        print()

    with get_connection() as conn:
        low_rows = conn.execute(
            """
            SELECT titulo_original, relevance_score
            FROM articulos
            WHERE procesado = 1 AND relevance_score <= 2
            ORDER BY fecha_ingesta DESC
            LIMIT 3
            """
        ).fetchall()
    if low_rows:
        print("  Ejemplos descartados en clasificación (score <= 2):")
        for row in low_rows:
            print(f"    · [{row['relevance_score']}] {row['titulo_original'][:90]}")
        print()

    batch, _ = limit_batch_for_prioritization(kept)
    result = prioritize_articles(batch)

    print("Agente 2 — Priorización semántica:")
    print(f"  batch embeddings:          {len(batch)}")
    print(f"  eventos agrupados:         {result.total_events}")
    print(f"  eventos sobre umbral:      {result.events_above_threshold}")
    print(f"  artículos priorizados:     {len(result.articles)}")
    print()

    report = build_editorial_report(mode="informe", classify_before_report=False)
    print("Informe unificado (sin reclasificar):")
    print(f"  artículos mostrados:       {len(report.article_ids)}")
    print(f"  total en informe:          {report.total_matched}")
    print()

    ok_filter = (
        stats["low_score"] > 0
        or len(rejected) > 0
        or (len(raw) > 0 and len(kept) > 0)
    )
    ok_prioritize = len(result.articles) > 0 or len(kept) == 0
    ok_report = len(report.article_ids) > 0 or stats["total"] == 0

    if stats["low_score"] > 0 or len(rejected) > 0:
        print("✅ Filtrado editorial activo (clasificación y/o filtro keyword)")
    elif len(raw) == 0:
        print("⚠️  Sin candidatos en ventana — prueba tras ingest o amplía periodo")
    else:
        print("⚠️  No se detectaron descartes; revisa si la ingesta es solo editorial")

    if ok_prioritize and result.events_above_threshold > 0:
        print("✅ Priorización semántica activa")
    elif len(kept) == 0:
        print("⚠️  Priorización omitida (sin artículos tras filtro)")
    else:
        print("⚠️  Priorización sin eventos sobre umbral")

    if ok_report and report.article_ids:
        print("✅ Generador de informe operativo")
    elif stats["total"] == 0:
        print("⚠️  Informe vacío (BD sin datos)")
    else:
        print("⚠️  Informe vacío — revisa ventana, clasificación o umbrales")

    sys.exit(0 if (ok_filter and ok_report) else 1)


if __name__ == "__main__":
    main()
