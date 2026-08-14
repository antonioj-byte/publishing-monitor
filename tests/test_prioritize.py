"""Tests for editorial prioritization (scoring logic, no embedding model required)."""

from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import settings
from reports.prioritize import (
    _order_articles_within_event,
    _pick_representative_title,
    _recency_score,
    _repetition_score,
    _tier_score,
    limit_batch_for_prioritization,
    prioritize_articles,
    score_event_cluster,
)


class PrioritizeScoringTests(unittest.TestCase):
    def test_repetition_capped(self) -> None:
        self.assertEqual(_repetition_score(1), 0.1)
        self.assertEqual(_repetition_score(10), 1.0)
        self.assertEqual(_repetition_score(20), 1.0)

    def test_recency_fresh_event(self) -> None:
        now = datetime(2026, 8, 13, 12, 0, tzinfo=ZoneInfo("Europe/Madrid"))
        recent = now - timedelta(hours=6)
        self.assertEqual(_recency_score(recent, now), 1.0)

    def test_recency_old_event(self) -> None:
        now = datetime(2026, 8, 13, 12, 0, tzinfo=ZoneInfo("Europe/Madrid"))
        old = now - timedelta(days=5)
        self.assertLess(_recency_score(old, now), 0.2)

    def test_recency_scales_with_report_window(self) -> None:
        now = datetime(2026, 8, 13, 12, 0, tzinfo=ZoneInfo("Europe/Madrid"))
        five_days_old = now - timedelta(days=5)
        daily = _recency_score(five_days_old, now)
        weekly = _recency_score(five_days_old, now, window_days=7)
        self.assertLess(daily, 0.2)
        self.assertGreater(weekly, daily)

    def test_tier1_beats_tier2_repetition(self) -> None:
        medios_t1 = [{"nombre": "The Guardian Books", "tier": 1}]
        medios_t2 = [{"nombre": "Medio nicho", "tier": 2}] * 8
        self.assertGreater(
            _tier_score(1, medios_t1),
            _tier_score(8, medios_t2),
        )

    def test_tier2_high_repetition_medium_score(self) -> None:
        medios = [{"nombre": f"Medio {i}", "tier": 2} for i in range(5)]
        score = _tier_score(5, medios)
        self.assertGreaterEqual(score, 0.5)
        self.assertLess(score, 1.0)

    def test_same_medio_requires_higher_similarity(self) -> None:
        from reports.prioritize import _merge_threshold

        a = {"medio_nombre": "NYT Books"}
        b = {"medio_nombre": "NYT Books"}
        c = {"medio_nombre": "The Guardian Books"}
        self.assertGreater(
            _merge_threshold(a, b, 0.72),
            _merge_threshold(a, c, 0.72),
        )

    def test_generic_roundup_requires_higher_cross_media_threshold(self) -> None:
        from reports.prioritize import _is_generic_roundup, _merge_threshold

        generic = {
            "medio_nombre": "NYT Books",
            "titulo_original": "The Best Books of 2026 So Far",
        }
        other = {
            "medio_nombre": "The Guardian Books",
            "titulo_original": "Publishing merger announced",
        }
        self.assertTrue(_is_generic_roundup(generic))
        self.assertFalse(_is_generic_roundup(other))
        self.assertGreater(
            _merge_threshold(generic, other, 0.72),
            0.72,
        )

    def test_event_explanation_includes_axes(self) -> None:
        now = datetime(2026, 8, 13, 12, 0, tzinfo=ZoneInfo("Europe/Madrid"))
        articles = [
            {
                "id": 1,
                "titulo_original": "Big publishing merger announced",
                "titular_traducido": "Anunciada gran fusión editorial",
                "resumen_generado": "Dos grandes grupos se unen.",
                "medio_nombre": "The Guardian Books",
                "medio_tier": 1,
                "relevance_score": 5,
                "categoria": "noticias",
                "fecha_publicacion": (now - timedelta(hours=3)).isoformat(),
            },
            {
                "id": 2,
                "titulo_original": "Publishing giants merge",
                "titular_traducido": "Gigantes editoriales se fusionan",
                "resumen_generado": "La operación cambia el mercado.",
                "medio_nombre": "NYT Books",
                "medio_tier": 1,
                "relevance_score": 4,
                "categoria": "noticias",
                "fecha_publicacion": (now - timedelta(hours=5)).isoformat(),
            },
        ]
        event = score_event_cluster(articles, event_id=0, now=now)
        self.assertIn("Tier 1", event.score.explanation)
        self.assertGreater(event.score.total, 0.5)
        self.assertEqual(event.score.distinct_sources, 2)

    def test_article_order_prefers_relevance_then_tier1(self) -> None:
        articles = [
            {
                "id": 1,
                "titulo_original": "Tier 2",
                "medio_tier": 2,
                "relevance_score": 4,
            },
            {
                "id": 2,
                "titulo_original": "Tier 1",
                "medio_tier": 1,
                "relevance_score": 4,
            },
            {
                "id": 3,
                "titulo_original": "Destacado",
                "medio_tier": 2,
                "relevance_score": 5,
            },
        ]
        ordered = _order_articles_within_event(articles)
        self.assertEqual([article["id"] for article in ordered], [3, 2, 1])
        self.assertEqual(_pick_representative_title(articles), "Destacado")

    def test_capped_batch_uses_score_not_tier(self) -> None:
        from unittest.mock import patch

        articles = [
            {
                "id": 1,
                "medio_tier": 2,
                "relevance_score": 4,
                "fecha_ingesta": "2026-08-13T10:00:00+00:00",
            },
            {
                "id": 2,
                "medio_tier": 1,
                "relevance_score": 3,
                "fecha_ingesta": "2026-08-13T10:00:00+00:00",
            },
        ]
        limited_settings = replace(settings, prioritize_max_batch=1)
        with patch("reports.prioritize.settings", limited_settings):
            batch, total = limit_batch_for_prioritization(articles)
        self.assertEqual(total, 2)
        self.assertEqual(batch[0]["id"], 1)

    def test_catalog_mode_includes_singleton_events(self) -> None:
        now = datetime(2026, 8, 13, 12, 0, tzinfo=ZoneInfo("Europe/Madrid"))
        articles = [
            {
                "id": 1,
                "titulo_original": "Arthur C Clarke award winner announced",
                "titular_traducido": "Premio Arthur C Clarke",
                "resumen_generado": "Una novela climática gana el premio.",
                "medio_nombre": "The Bookseller",
                "medio_tier": 1,
                "relevance_score": 4,
                "categoria": "noticias",
                "fecha_publicacion": (now - timedelta(days=5)).isoformat(),
            },
            {
                "id": 2,
                "titulo_original": "Rebecca Perry Lorca interview poetry",
                "titular_traducido": "Rebecca Perry sobre Lorca",
                "resumen_generado": "Entrevista sobre poesía y Lorca.",
                "medio_nombre": "The Guardian Books",
                "medio_tier": 1,
                "relevance_score": 4,
                "categoria": "noticias",
                "fecha_publicacion": (now - timedelta(days=6)).isoformat(),
            },
        ]
        daily = prioritize_articles(articles)
        catalog = prioritize_articles(articles, recency_window_days=7)
        self.assertLess(daily.events_above_threshold, len(articles))
        self.assertEqual(catalog.events_above_threshold, len(articles))


if __name__ == "__main__":
    unittest.main()
