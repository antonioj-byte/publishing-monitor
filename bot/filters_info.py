"""Combined filter reference for Telegram (/tags and /paises)."""

from __future__ import annotations

from reports.paises import list_available_locations
from reports.tags import list_available_tags


def _trim_examples(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        if line.strip().lower().startswith("ejemplos:"):
            break
        out.append(line)
    while out and out[-1] == "":
        out.pop()
    return out


def list_available_filters() -> str:
    """Tags editoriales + países/regiones + medios en un solo mensaje informativo."""
    tags_block = list_available_tags()
    locations_block = list_available_locations()

    tags_body = _trim_examples(tags_block.splitlines())
    loc_body = _trim_examples(locations_block.splitlines())

    lines = [
        "📋 Filtros disponibles para /informe",
        "",
        *tags_body,
        "",
        "—" * 20,
        "",
        *loc_body,
        "",
        "—" * 20,
        "",
        "📰 Medios: escribe el nombre en /informe (lista completa: /medios)",
        "",
        "Ejemplos:",
        "  /informe — informe diario (desde último cierre)",
        "  /informe 7 ficcion",
        "  /informe 7 alemania",
        "  /informe 7 les inrocks",
        "  /informe 7 les inrocks ficcion",
        "  «informe últimos 7 días ficción en alemania»",
    ]
    return "\n".join(lines)
