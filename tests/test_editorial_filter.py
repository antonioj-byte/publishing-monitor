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

    def test_rejects_general_business_even_with_editorial_in_summary(self) -> None:
        self.assertFalse(
            is_editorial_scope(
                titulo="Stripe, Advent in Talks to Buy PayPal - WSJ",
                resumen_generado=(
                    "Operación financiera entre empresas de pagos digitales, "
                    "sin relación con libros, literatura o el sector editorial."
                ),
            )
        )

    def test_rejects_ai_marketing_piece(self) -> None:
        self.assertFalse(
            is_editorial_scope(
                titulo="As AI Rewrites Search for Marketers, Reddit Fights to Stay the Same",
                resumen_generado=(
                    "Analiza cómo la búsqueda impulsada por IA transforma el marketing digital."
                ),
            )
        )

    def test_rejects_job_seeker_resume_advice(self) -> None:
        self.assertFalse(
            is_editorial_scope(
                titulo="Job Seekers Are Racing to AI-Proof Their Résumés",
                resumen="Consejos de empleo y selección de personal con IA.",
            )
        )

    def test_trusts_llm_classified_articles_in_reports(self) -> None:
        classified = {
            "titulo_original": "Neuer Roman der Autorin erscheint im Herbst",
            "titular_traducido": "La nueva novela de la autora llega en otoño",
            "resumen_raw": "Der Verlag kündigt die Buchpremiere an",
            "resumen_generado": "El sello anuncia la publicación de la novela en Frankfurt.",
            "relevance_score": 4,
        }
        unclassified = {
            "titulo_original": "Rockkonzert in Berlin",
            "titular_traducido": None,
            "resumen_raw": "Die Tournee geht weiter",
            "resumen_generado": "Musik und Konzerte",
            "relevance_score": 2,
        }
        misclassified = {
            "titulo_original": "Stripe in Talks to Buy PayPal",
            "titular_traducido": "Stripe negocia comprar PayPal",
            "resumen_raw": "Payment deal",
            "resumen_generado": "Acuerdo entre fintechs, sin ángulo editorial.",
            "relevance_score": 4,
        }
        kept = apply_keyword_scope_filter([classified, unclassified, misclassified])
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["titulo_original"], classified["titulo_original"])


if __name__ == "__main__":
    unittest.main()
