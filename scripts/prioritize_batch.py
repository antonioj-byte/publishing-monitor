#!/usr/bin/env python3
"""Run editorial prioritization on the current article batch."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import settings
from db.connection import get_connection, init_schema
from reports.generator import _fetch_articles
from reports.prioritize import prioritize_articles


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prioritize editorial events from classified articles"
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=24,
        help="Look back window in hours (default: 24)",
    )
    parser.add_argument(
        "--include-sent",
        action="store_true",
        help="Include articles already sent in a previous informe",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of human-readable text",
    )
    args = parser.parse_args()

    init_schema()
    since = datetime.now(ZoneInfo(settings.timezone)) - timedelta(hours=args.hours)
    articles = _fetch_articles(since, include_sent=args.include_sent)

    if not articles:
        print(f"No articles found in the last {args.hours}h.")
        return

    result = prioritize_articles(articles)

    if args.json:
        import json

        payload = {
            "total_input": result.total_input,
            "total_events": result.total_events,
            "events_above_threshold": result.events_above_threshold,
            "threshold": settings.prioritize_score_threshold,
            "events": [
                {
                    "event_id": e.event_id,
                    "title": e.representative_title,
                    "score": e.score.total,
                    "explanation": e.score.explanation,
                    "sources": e.medios,
                    "article_ids": [a["id"] for a in e.articles],
                }
                for e in result.events
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(
        f"Priorización editorial — {result.total_input} artículos → "
        f"{result.total_events} eventos → {result.events_above_threshold} "
        f"sobre umbral ({settings.prioritize_score_threshold:.2f})\n"
    )
    print(
        f"Pesos: repetición={settings.prioritize_weight_repetition} · "
        f"actualidad={settings.prioritize_weight_recency} · "
        f"tier={settings.prioritize_weight_tier}\n"
    )

    for rank, event in enumerate(result.events, start=1):
        medios = ", ".join(
            f"{m['nombre']} (T{m['tier']})" for m in event.medios
        )
        print(f"#{rank} [{event.score.total:.2f}] {event.representative_title}")
        print(f"   Medios: {medios}")
        print(f"   {event.score.explanation}")
        print()


if __name__ == "__main__":
    main()
