"""Tests for markdown report export."""

from __future__ import annotations

import unittest

from db.models import ReportFilter
from reports.markdown_export import (
    build_markdown_report,
    format_article_markdown,
    markdown_filename,
)


class MarkdownExportTests(unittest.TestCase):
    def test_format_article_includes_required_fields(self) -> None:
        block = format_article_markdown(
            {
                "titular_traducido": "Premio literario anunciado",
                "resumen_generado": "Un autor gana un premio importante.",
                "url": "https://example.com/noticia",
                "fecha_publicacion": "2026-08-14T10:00:00+00:00",
                "tags": '["ficcion", "ferias_premios"]',
                "pais": "gb",
                "medio_nombre": "The Bookseller",
            }
        )
        self.assertIn("## Premio literario anunciado", block)
        self.assertIn("**Resumen:** Un autor gana un premio importante.", block)
        self.assertIn("https://example.com/noticia", block)
        self.assertIn("**Fecha:**", block)
        self.assertIn("**Tema:** Ficción", block)
        self.assertIn("**Tema:**", block)
        self.assertIn("Ferias y premios", block)
        self.assertIn("**Área geográfica:** Reino Unido", block)
        self.assertIn("**Medio:** The Bookseller", block)

    def test_build_markdown_report_header_and_count(self) -> None:
        text = build_markdown_report(
            [
                {
                    "titular_traducido": "Noticia uno",
                    "resumen_generado": "Resumen uno.",
                    "url": "https://example.com/1",
                    "fecha_publicacion": "2026-08-14T10:00:00+00:00",
                    "tags": '["ficcion"]',
                    "pais": "de",
                }
            ],
            mode="informe_pais",
            report_filter=ReportFilter(
                days=7,
                tags=["ficcion"],
                tag_labels=["Ficción"],
            ),
        )
        self.assertIn("# Informe — Ficción · últimos 7 días", text)
        self.assertIn("Artículos: 1", text)
        self.assertIn("## Noticia uno", text)

    def test_markdown_filename_slug(self) -> None:
        name = markdown_filename(
            mode="informe_pais",
            report_filter=ReportFilter(days=7, tags=["ficcion"], pais="de"),
        )
        self.assertTrue(name.endswith(".md"))
        self.assertIn("ficcion", name)
        self.assertIn("de", name)


if __name__ == "__main__":
    unittest.main()
