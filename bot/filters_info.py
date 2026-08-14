"""Combined filter reference for Telegram (/tags and /paises)."""

from __future__ import annotations

from reports.paises import list_available_locations
from reports.tags import list_available_tags


def list_available_filters() -> str:
    """Tags editoriales + países/regiones en un solo mensaje informativo."""
    tags_block = list_available_tags()
    locations_block = list_available_locations()

    # Strip duplicate example sections from each block; add one unified block.
    tags_lines = tags_block.splitlines()
    loc_lines = locations_block.splitlines()

    def _trim_examples(lines: list[str]) -> list[str]:
        out: list[str] = []
        for line in lines:
            if line.strip().lower().startswith("ejemplos:"):
                break
            out.append(line)
        while out and out[-1] == "":
            out.pop()
        return out

    tags_body = _trim_examples(tags_lines)
    loc_body = _trim_examples(loc_lines)

    lines = [
        "📋 Filtros disponibles para /informe",
        "",
        *tags_body,
        "",
        "—" * 20,
        "",
        *loc_body,
        "",
        "Ejemplos:",
        "  /informe — informe diario (desde último cierre)",
        "  /informe 7 ficcion",
        "  /informe 7 alemania",
        "  /informe 14 alemania poesia",
        "  «informe últimos 7 días ficción en alemania»",
    ]
    return "\n".join(lines)
