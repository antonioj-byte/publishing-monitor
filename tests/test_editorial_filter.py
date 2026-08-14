"""Tests for editorial scope filtering."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.editorial_filter import apply_keyword_scope_filter, is_editorial_scope


class EditorialFilterTests(unittest.TestCase):
    def test_keeps_book_review(self) -> None:
        self.assertTrue(
            is_editorial_scope(
                titulo="New novel explores memory and exile",
                resumen="The author discusses her latest book and the publishing process.",
            )
        )

    def test_rejects_music_album(self) -> None:
        self.assertFalse(
            is_editorial_scope(
                titulo="Taylor Swift announces new album and world tour",
                resumen="The pop star revealed concert dates across Europe.",
            )
        )

    def test_rejects_film_without_book_angle(self) -> None:
        self.assertFalse(
            is_editorial_scope(
                titulo="Oscar nominations announced for best film",
                resumen="The academy revealed this year's cinema shortlist.",
            )
        )

    def test_keeps_film_book_adaptation(self) -> None:
        self.assertTrue(
            is_editorial_scope(
                titulo="Streaming adaptation of prize-winning novel arrives",
                resumen="The bestseller by the author finally reaches the screen.",
            )
        )

    def test_rejects_concert_in_spanish(self) -> None:
        self.assertFalse(
            is_editorial_scope(
                titulo="Concierto de la Orquesta Nacional en el Auditorio",
                resumen="La gira musical continúa por las principales ciudades.",
            )
        )

    def test_keeps_editorial_industry_news(self) -> None:
        self.assertTrue(
            is_editorial_scope(
                titulo="Major publisher reports strong book sales",
                resumen="The publishing group saw growth in fiction and translation rights.",
            )
        )


    def test_keeps_german_literary_headline(self) -> None:
        self.assertTrue(
            is_editorial_scope(
                titulo="Neuer Roman der Autorin erscheint im Herbst",
                resumen="Der Verlag kündigt die Buchpremiere auf der Frankfurter Messe an.",
            )
        )

    def test_trusts_llm_classified_articles_in_reports(self) -> None:
        classified = {
            "titulo_original": "Stadtrat beschließt neue Kulturpolitik",
            "titular_traducido": "El ayuntamiento aprueba cultura",
            "resumen_raw": "Debatte über Subventionen",
            "resumen_generado": "Política cultural local",
            "relevance_score": 4,
        }
        unclassified = {
            "titulo_original": "Rockkonzert in Berlin",
            "titular_traducido": None,
            "resumen_raw": "Die Tournee geht weiter",
            "resumen_generado": "Musik und Konzerte",
            "relevance_score": 2,
        }
        kept = apply_keyword_scope_filter([classified, unclassified])
        self.assertEqual([item["relevance_score"] for item in kept], [4])


if __name__ == "__main__":
    unittest.main()
