"""Heuristic tag refinement after model classification."""

from __future__ import annotations

import re

from reports.tags import validate_tags

_FICTION = re.compile(
    r"\b("
    r"novela|novelas|novel\b|novels|ficcion|ficción|relato|relatos|cuento|cuentos|"
    r"autoficcion|autoficción|roman\b|romans|fiction|short story|"
    r"escritora|escritor|autora|autor"
    r")\b",
    re.IGNORECASE,
)
_NON_FICTION = re.compile(
    r"\b("
    r"memoria|memorias|biograf|crónica|cronica|reportaje|divulgacion|divulgación|"
    r"ensayo|ensayos|non-fiction|no ficcion|no ficción|sachbuch|"
    r"testimonio|historia oral"
    r")\b",
    re.IGNORECASE,
)
_ESSAY = re.compile(
    r"\b(ensayo|ensayos|reflexion|reflexión|crónica|cronica|filosof)\b",
    re.IGNORECASE,
)
_INDUSTRY = re.compile(
    r"\b(merger|adquisicion|adquisición|sello|imprint|"
    r"rights|derechos|traduccion|traducción|feria del libro|book fair|premio|prize|"
    r"planeta|booker|nobel|book publisher|publishing house|publishing group|"
    r"industria editorial|book trade)\b",
    re.IGNORECASE,
)
_POETRY = re.compile(r"\b(poesia|poesía|poema|poetry|poet)\b", re.IGNORECASE)
_COMIC = re.compile(r"\b(comic|cómic|graphic novel|novela grafica|novela gráfica)\b", re.IGNORECASE)
_LIJ = re.compile(
    r"\b(infantil|juvenil|young adult|ya\b|children'?s book|lij)\b",
    re.IGNORECASE,
)


def _text_blob(*parts: str | None) -> str:
    return " ".join(p for p in parts if p)


def refine_tags(
    *,
    titulo: str,
    resumen: str | None,
    resumen_generado: str | None,
    tags: list[str],
) -> list[str]:
    """Fix common model mistakes using title/summary signals."""
    blob = _text_blob(titulo, resumen, resumen_generado)
    refined = list(tags)

    if "no_ficcion" in refined and _FICTION.search(blob) and not _NON_FICTION.search(blob):
        refined = [t for t in refined if t != "no_ficcion"]
        if "ficcion" not in refined:
            refined.insert(0, "ficcion")

    if "no_ficcion" in refined and _ESSAY.search(blob):
        refined = [t for t in refined if t != "no_ficcion"]
        if "ensayo_literario" not in refined:
            refined.insert(0, "ensayo_literario")
        if _FICTION.search(blob) and "ficcion" not in refined:
            refined.append("ficcion")

    if not refined or refined == ["mundo_editorial"]:
        if _POETRY.search(blob):
            refined = ["poesia", *refined]
        elif _COMIC.search(blob):
            refined = ["comic", *refined]
        elif _LIJ.search(blob):
            refined = ["lij", *refined]
        elif _ESSAY.search(blob) and not _FICTION.search(blob):
            refined = ["ensayo_literario", *refined]
        elif _FICTION.search(blob):
            refined = ["ficcion", *refined]
        elif _INDUSTRY.search(blob):
            refined = ["mundo_editorial", *refined]

    if "ficcion" in refined and "no_ficcion" in refined:
        if _NON_FICTION.search(blob) and not _FICTION.search(blob):
            refined = [t for t in refined if t != "ficcion"]
        else:
            refined = [t for t in refined if t != "no_ficcion"]

    deduped: list[str] = []
    for tag in refined:
        if tag not in deduped:
            deduped.append(tag)

    return validate_tags(deduped)[:3]
