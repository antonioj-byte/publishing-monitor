"""Tests for heuristic tag refinement."""

from __future__ import annotations

import unittest

from ai.tag_rules import refine_tags


class TagRefinementTests(unittest.TestCase):
    def test_novel_interview_not_non_fiction(self) -> None:
        tags = refine_tags(
            titulo="Nina Lykke on her new novel",
            resumen="Interview with the Norwegian novelist about her latest book.",
            resumen_generado="Entrevista con la novelista noruega sobre su nueva novela.",
            tags=["no_ficcion"],
        )
        self.assertIn("ficcion", tags)
        self.assertNotIn("no_ficcion", tags)

    def test_speculative_essay_not_non_fiction(self) -> None:
        tags = refine_tags(
            titulo="Barcelona, 2131",
            resumen="Speculative essay on AI and the future of Barcelona.",
            resumen_generado="Ensayo especulativo sobre IA y Barcelona en 2131.",
            tags=["no_ficcion"],
        )
        self.assertIn("ensayo_literario", tags)
        self.assertNotIn("no_ficcion", tags)

    def test_memoir_stays_non_fiction(self) -> None:
        tags = refine_tags(
            titulo="Memoria de un editor",
            resumen="Biografía y memoria de un director editorial.",
            resumen_generado="Memoria de un editor sobre su carrera.",
            tags=["no_ficcion"],
        )
        self.assertIn("no_ficcion", tags)


if __name__ == "__main__":
    unittest.main()
