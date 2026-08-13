"""Tests for editorial prioritization (scoring logic, no embedding model required)."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reports.prioritize import (
    _recency_score,
    _repetition_score,
    _tier_score,
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


if __name__ == "__main__":
    unittest.main()
